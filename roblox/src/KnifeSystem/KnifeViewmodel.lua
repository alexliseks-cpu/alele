--!nonstrict
--[[
	KnifeViewmodel - first-person knife controller (client).

	local KnifeViewmodel = require(ReplicatedStorage.KnifeSystem.KnifeViewmodel)
	local vm = KnifeViewmodel.new("Butterfly")   -- or "Karambit"
	vm:Equip()            -- draw, then idle loop
	vm:Attack()           -- light attack, alternates Attack1 / Attack2
	vm:HeavyAttack()
	vm:Inspect()          -- cancelled by attacks / unequip
	vm:Unequip()          -- or vm:Destroy()
	vm.Hit:Connect(function(kind, raycastResult) end)   -- "light" | "heavy" on the clip's Hit marker
	vm.Marker:Connect(function(clipName, markerName, value) end)
	vm.StateChanged:Connect(function(state) end)        -- "Drawing" | "Idle" | "Attacking" | "Heavy" | "Inspecting" | "Unequipped"

	Needs ReplicatedStorage.KnifeSystem.Knives.<Knife> (built by the setup
	script) and ReplicatedStorage.KnifeSystem.Animations.<Knife>.
]]

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local SoundService = game:GetService("SoundService")
local Workspace = game:GetService("Workspace")

local KnifeSystem = script.Parent
local Config = require(KnifeSystem.KnifeConfig)
local KnifeAnimator = require(KnifeSystem.KnifeAnimator)
local KnifeBuilder = require(KnifeSystem.KnifeBuilder)

local KnifeViewmodel = {}
KnifeViewmodel.__index = KnifeViewmodel

local RENDER_NAME = "KnifeViewmodelStep"
local instanceCount = 0

function KnifeViewmodel.new(knife: string)
	local self = setmetatable({}, KnifeViewmodel)
	self.Knife = knife
	self.Clips = Config.Clips[knife]
	assert(self.Clips, "no clips configured for " .. tostring(knife))
	self.State = "Unequipped"
	self.Hit = KnifeAnimator.Signal.new()
	self.Marker = KnifeAnimator.Signal.new()
	self.StateChanged = KnifeAnimator.Signal.new()
	self._nextAttack = 0
	self._attackIndex = 0
	self._sway = Vector2.zero
	self._bobTime = 0
	self._lastCamCF = nil
	self._lastShake = CFrame.identity
	instanceCount += 1
	self._renderName = RENDER_NAME .. instanceCount
	return self
end

function KnifeViewmodel:_setState(s: string)
	if self.State ~= s then
		self.State = s
		self.StateChanged:Fire(s)
	end
end

function KnifeViewmodel:_build()
	local template = KnifeSystem:WaitForChild("Knives"):WaitForChild(self.Knife)
	local character = Players.LocalPlayer.Character
	local model = KnifeBuilder.BuildViewmodel(self.Knife, template, character)
	model.Parent = Workspace.CurrentCamera
	self.Model = model
	self.Root = model.PrimaryPart
	self.Animator = KnifeAnimator.new(model)
	self.Animator:LoadFolder(KnifeSystem:WaitForChild("Animations"):WaitForChild(self.Knife))
	local cam = model:FindFirstChild("CameraBone", true)
	self._cameraMotor = nil
	for _, d in ipairs(model:GetDescendants()) do
		if d:IsA("Motor6D") and d.Part1 == cam then
			self._cameraMotor = d
		end
	end
	self._markerConn = self.Animator.MarkerReached:Connect(function(clip, name, value)
		self:_onMarker(clip, name, value)
	end)
	self._endedConn = self.Animator.Ended:Connect(function(clip)
		self:_onEnded(clip)
	end)
end

function KnifeViewmodel:_onMarker(clip: string, name: string, value: string)
	self.Marker:Fire(clip, name, value)
	if name == "Sound" then
		local id = Config.Sounds[value]
		if id and id ~= "" then
			local s = Instance.new("Sound")
			s.SoundId = id
			s.Volume = Config.SoundVolume
			SoundService:PlayLocalSound(s)
			task.delay(3, function()
				s:Destroy()
			end)
		end
	elseif name == "Hit" then
		local kind = if value ~= "" then value else "light"
		local cam = Workspace.CurrentCamera
		local params = RaycastParams.new()
		params.FilterType = Enum.RaycastFilterType.Exclude
		params.FilterDescendantsInstances = { self.Model, Players.LocalPlayer.Character }
		local range = Config.HitRange[kind] or 6
		local result = Workspace:Raycast(cam.CFrame.Position, cam.CFrame.LookVector * range, params)
		self.Hit:Fire(kind, result)
	end
end

function KnifeViewmodel:_onEnded(clip: string)
	local c = self.Clips
	if clip == c.Draw or clip == c.Attack1 or clip == c.Attack2 or clip == c.Heavy or clip == c.Inspect then
		if self.State ~= "Unequipped" then
			self:_setState("Idle")
		end
	end
end

local function firstPerson(cam: Camera): boolean
	local char = Players.LocalPlayer.Character
	local head = char and char:FindFirstChild("Head")
	if not head then
		return true
	end
	return (cam.CFrame.Position - head.Position).Magnitude < 1.5
end

function KnifeViewmodel:_step(dt: number)
	local cam = Workspace.CurrentCamera
	if not self.Model or not cam then
		return
	end
	self.Animator:Update(dt)

	-- camera shake: apply the CameraBone motion as an incremental rotation so
	-- the default camera scripts never accumulate it
	local shake = CFrame.identity
	if Config.CameraShake and self._cameraMotor then
		shake = self._cameraMotor.Transform.Rotation
	end
	local delta = self._lastShake:Inverse() * shake
	self._lastShake = shake
	cam.CFrame = cam.CFrame * delta
	local base = cam.CFrame * shake:Inverse()

	-- sway (lag behind camera rotation)
	local sway = CFrame.identity
	if Config.Sway.Enabled then
		local target = Vector2.zero
		if self._lastCamCF then
			local rel = self._lastCamCF:ToObjectSpace(base)
			local rx, ry = rel:ToEulerAnglesYXZ()
			local m = Config.Sway.MaxAngle
			target = Vector2.new(math.clamp(rx, -m, m), math.clamp(ry, -m, m)) * Config.Sway.Amount
				/ math.max(dt * 60, 0.25)
		end
		local a = 1 - math.exp(-Config.Sway.Smooth * dt)
		self._sway = self._sway:Lerp(target, a)
		sway = CFrame.Angles(-self._sway.X, -self._sway.Y, 0)
	end
	self._lastCamCF = base

	-- walk bob
	local bob = CFrame.identity
	if Config.Bob.Enabled then
		local char = Players.LocalPlayer.Character
		local hum = char and char:FindFirstChildOfClass("Humanoid")
		local root = char and char:FindFirstChild("HumanoidRootPart")
		local speed = if root then Vector3.new(root.AssemblyLinearVelocity.X, 0, root.AssemblyLinearVelocity.Z).Magnitude else 0
		if hum and hum.FloorMaterial == Enum.Material.Air then
			speed = 0
		end
		local k = math.clamp(speed / 16, 0, 1.5)
		self._bobTime += dt * Config.Bob.Frequency * math.max(k, 0.0001) * math.pi * 2
		local amp = Config.Bob.Amplitude * k
		bob = CFrame.new(math.sin(self._bobTime) * amp.X, -math.abs(math.cos(self._bobTime)) * amp.Y, 0)
	end

	self.Root.CFrame = base * Config.ViewmodelOffset * bob * sway
	local visible = (not Config.FirstPersonOnly) or firstPerson(cam)
	if visible ~= self._visible then
		self._visible = visible
		self.Model.Parent = if visible then cam else nil
	end
end

function KnifeViewmodel:Equip()
	if self.Model then
		self:Unequip()
	end
	self:_build()
	self._lastCamCF = nil
	self._lastShake = CFrame.identity
	self._visible = true
	RunService:BindToRenderStep(self._renderName, Enum.RenderPriority.Camera.Value + 1, function(dt)
		self:_step(dt)
	end)
	self.Animator:Play(self.Clips.Idle, { FadeTime = 0 })
	self.Animator:Play(self.Clips.Draw, { FadeTime = 0 })
	self._nextAttack = os.clock() + 0.35
	self:_setState("Drawing")
end

function KnifeViewmodel:Unequip()
	if not self.Model then
		return
	end
	RunService:UnbindFromRenderStep(self._renderName)
	-- undo any camera shake still applied
	local cam = Workspace.CurrentCamera
	if cam then
		cam.CFrame = cam.CFrame * self._lastShake:Inverse()
	end
	self._lastShake = CFrame.identity
	if self._markerConn then
		self._markerConn:Disconnect()
	end
	if self._endedConn then
		self._endedConn:Disconnect()
	end
	self.Animator:Destroy()
	self.Model:Destroy()
	self.Model = nil
	self:_setState("Unequipped")
end

function KnifeViewmodel:_action(clip: string, state: string)
	local keep = { [self.Clips.Idle] = true }
	self.Animator:StopAllExcept(keep, Config.FadeIn)
	self.Animator:Play(clip, { FadeTime = Config.FadeIn })
	self:_setState(state)
end

function KnifeViewmodel:Attack(): boolean
	if not self.Model or os.clock() < self._nextAttack then
		return false
	end
	self._attackIndex = (self._attackIndex % 2) + 1
	local clip = if self._attackIndex == 1 then self.Clips.Attack1 else self.Clips.Attack2
	self._nextAttack = os.clock() + Config.AttackCooldown
	self:_action(clip, "Attacking")
	return true
end

function KnifeViewmodel:HeavyAttack(): boolean
	if not self.Model or os.clock() < self._nextAttack then
		return false
	end
	self._nextAttack = os.clock() + Config.HeavyCooldown
	self:_action(self.Clips.Heavy, "Heavy")
	return true
end

function KnifeViewmodel:Inspect(): boolean
	if not self.Model or self.State ~= "Idle" then
		return false
	end
	self:_action(self.Clips.Inspect, "Inspecting")
	return true
end

function KnifeViewmodel:Destroy()
	self:Unequip()
end

return KnifeViewmodel
