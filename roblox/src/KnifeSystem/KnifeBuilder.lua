--!nonstrict
--[[
	KnifeBuilder - assembles the knife models and the knife viewmodels.

	Knife model (built once in Studio by SetupKnifeViewmodels, stored in
	ReplicatedStorage.KnifeSystem.Knives.<Knife>):
	  * one invisible "joint part" per knife bone (BF_HandleA, BF_Blade, ...)
	    placed at the bone pivot, joined by Motor6Ds named like the bone;
	  * the imported MeshParts ("<Bone>_Mesh...") welded to their joint part.

	Viewmodel (built at runtime from the local player's character):
	  HumanoidRootPart (anchored, = camera)
	    CameraBone                (invisible, camera shake channel)
	    LowerTorso -> UpperTorso  (invisible, fixed)
	      RightUpperArm -> RightLowerArm -> RightHand -> knife root ...
	      LeftUpperArm  -> LeftLowerArm  -> LeftHand
	  Arm parts are clones of the avatar's own R15 arms (colours + shirt via a
	  Humanoid + Shirt clone).  Joint frames = the avatar's RigAttachment
	  positions with part axes, so the clips fit any R15 body.  Motor6D names
	  follow R15 (RightShoulder, RightElbow, RightWrist, ...); Pose names in
	  the KeyframeSequences = part names.
]]

local RigData = require(script.Parent.RigData)
local Config = require(script.Parent.KnifeConfig)

local KnifeBuilder = {}

local BONE = {}
for _, b in ipairs(RigData.Bones) do
	BONE[b.Name] = b
end

local ARM_PARTS = {
	RightUpperArm = true,
	RightLowerArm = true,
	RightHand = true,
	LeftUpperArm = true,
	LeftLowerArm = true,
	LeftHand = true,
}
KnifeBuilder.ArmParts = ARM_PARTS

local function knifeOfBone(name: string): string?
	for knife, kd in pairs(RigData.Knives) do
		if table.find(kd.Bones, name) then
			return knife
		end
	end
	return nil
end

local function setFlags(p: BasePart, anchored: boolean)
	p.Anchored = anchored
	p.CanCollide = false
	p.CanQuery = false
	p.CanTouch = false
	p.CastShadow = false
	p.Massless = true
end

local function jointPart(name: string, cf: CFrame): Part
	local p = Instance.new("Part")
	p.Name = name
	p.Size = Vector3.new(0.05, 0.05, 0.05)
	p.Transparency = 1
	p.CFrame = cf
	setFlags(p, false)
	p:SetAttribute("KnifeJointPart", true)
	return p
end

local function capitalize(s: string): string
	return s:sub(1, 1):upper() .. s:sub(2)
end

-- part frame -> pivot of the joint where `part` is Part1
local function pivotInPart(part: BasePart, boneName: string): CFrame
	if part:GetAttribute("KnifeJointPart") then
		return CFrame.identity
	end
	local joint = BONE[boneName].Joint
	local att = part:FindFirstChild(joint .. "RigAttachment")
	if att and att:IsA("Attachment") then
		return CFrame.new(att.Position)
	end
	local defaults = RigData.R15[boneName]
	local pos = defaults and defaults[joint .. "RigAttachment"]
	return if pos then CFrame.new(pos) else CFrame.identity
end
KnifeBuilder.PivotInPart = pivotInPart

-- C0 of the joint `boneName` inside its parent part
local function jointC0(parentPart: BasePart, parentName: string, boneName: string): CFrame
	local b = BONE[boneName]
	if not parentPart:GetAttribute("KnifeJointPart") and ARM_PARTS[parentName] then
		local att = parentPart:FindFirstChild(b.Joint .. "RigAttachment")
		if att and att:IsA("Attachment") then
			return CFrame.new(att.Position)
		end
		local defaults = RigData.R15[parentName]
		local pos = defaults and defaults[b.Joint .. "RigAttachment"]
		if pos then
			return CFrame.new(pos)
		end
	end
	return pivotInPart(parentPart, parentName) * b.Offset
end
KnifeBuilder.JointC0 = jointC0

local function motor(name: string, p0: BasePart, p1: BasePart, c0: CFrame, c1: CFrame): Motor6D
	local m = Instance.new("Motor6D")
	m.Name = name
	m.Part0 = p0
	m.Part1 = p1
	m.C0 = c0
	m.C1 = c1
	m.Parent = p0
	return m
end

local function applyTextures(mp: MeshPart, knife: string, group: string)
	if mp:FindFirstChildOfClass("SurfaceAppearance") then
		return
	end
	local tex = RigData.Textures[knife .. "_" .. capitalize(group)]
	if not tex or tex.ColorMap == "" then
		return
	end
	local ok, err = pcall(function()
		local sa = Instance.new("SurfaceAppearance")
		sa.ColorMap = tex.ColorMap
		sa.NormalMap = tex.NormalMap
		sa.RoughnessMap = tex.RoughnessMap
		sa.MetalnessMap = tex.MetalnessMap
		sa.Parent = mp
	end)
	if not ok then
		warn("[KnifeBuilder] SurfaceAppearance needs Studio (command bar / plugin): " .. tostring(err))
	end
end

--[[ Build a knife model in knife MODEL space from imported MeshParts.
	meshLookup(name) -> MeshPart? (the importer's parts, any parent)
	Returns the Model; its PrimaryPart is the knife root joint part. ]]
function KnifeBuilder.BuildKnifeModel(knife: string, meshLookup: (string) -> MeshPart?): Model
	local kd = RigData.Knives[knife]
	assert(kd, "unknown knife " .. tostring(knife))
	local model = Instance.new("Model")
	model.Name = knife
	local parts = {}
	for _, bone in ipairs(kd.Bones) do
		local p = jointPart(bone, kd.Pivots[bone])
		p.Parent = model
		parts[bone] = p
	end
	for _, bone in ipairs(kd.Bones) do
		local parent = BONE[bone].Parent
		if parts[parent] then
			motor(BONE[bone].Joint, parts[parent], parts[bone], BONE[bone].Offset, CFrame.identity)
		end
	end
	model.PrimaryPart = parts[kd.Bones[1]]
	for _, m in ipairs(kd.Meshes) do
		local src = meshLookup(m.Name)
		if not src then
			warn("[KnifeBuilder] mesh not found: " .. m.Name)
			continue
		end
		local mp = src:Clone()
		mp.Name = m.Name
		for _, c in ipairs(mp:GetChildren()) do
			if not c:IsA("SurfaceAppearance") then
				c:Destroy()
			end
		end
		local s = mp.Size
		local r = Vector3.new(s.X / m.Size.X, s.Y / m.Size.Y, s.Z / m.Size.Z)
		if math.abs(r.X - r.Y) > 0.03 * r.X or math.abs(r.X - r.Z) > 0.03 * r.X then
			warn(string.format("[KnifeBuilder] %s: imported size %s does not match %s - check the importer's axis/scale settings", m.Name, tostring(s), tostring(m.Size)))
		end
		mp.Size = m.Size
		mp.CFrame = CFrame.new(m.Center)
		setFlags(mp, false)
		mp.Parent = model
		local w = Instance.new("Weld")
		w.Name = "KnifeWeld"
		w.Part0 = parts[m.Bone]
		w.Part1 = mp
		w.C0 = parts[m.Bone].CFrame:Inverse() * mp.CFrame
		w.C1 = CFrame.identity
		w.Parent = mp
		applyTextures(mp, knife, m.Group)
	end
	return model
end

local function cleanArmClone(src: BasePart): BasePart
	local p = src:Clone()
	for _, c in ipairs(p:GetChildren()) do
		if not (c:IsA("Attachment") and c.Name:match("RigAttachment$")) and not c:IsA("SurfaceAppearance")
			and not c:IsA("SpecialMesh") and not c:IsA("Decal") and not c:IsA("Texture") then
			c:Destroy()
		end
	end
	setFlags(p, false)
	p.LocalTransparencyModifier = 0
	p.Transparency = 0
	return p
end

local function fallbackArm(name: string): BasePart
	local sizes = RigData.R15.Sizes
	local size = if name:find("UpperArm") then sizes.UpperArm elseif name:find("LowerArm") then sizes.LowerArm else sizes.Hand
	local p = Instance.new("Part")
	p.Name = name
	p.Size = size
	p.Material = Enum.Material.SmoothPlastic
	p.Color = if name:find("Hand") then Config.FallbackSkinColor else Config.FallbackSleeveColor
	setFlags(p, false)
	for attName, pos in pairs(RigData.R15[name]) do
		local a = Instance.new("Attachment")
		a.Name = attName
		a.Position = pos
		a.Parent = p
	end
	return p
end

--[[ Build a viewmodel for `knife` using the knife model template and the
	character's R15 arms (fallback blocks when missing).
	opts.EditorRig = true -> anchored root + AnimationController/Animator for
	the Animation Editor, block arms. ]]
function KnifeBuilder.BuildViewmodel(knife: string, knifeTemplate: Model, character: Model?, opts: { EditorRig: boolean? }?): Model
	local o = opts or {}
	local vm = Instance.new("Model")
	vm.Name = "KnifeViewmodel_" .. knife
	local parts = {}

	local knifeModel = knifeTemplate:Clone()
	knifeModel.Name = "Knife"
	local knifeParts = {}
	for _, d in ipairs(knifeModel:GetDescendants()) do
		if d:IsA("BasePart") then
			knifeParts[d.Name] = d
		end
	end

	for _, b in ipairs(RigData.Bones) do
		local owner = knifeOfBone(b.Name)
		if owner and owner ~= knife then
			continue
		end
		local part
		if b.Parent == nil then
			part = jointPart(b.Name, CFrame.identity)
			part.Anchored = true
			part.Parent = vm
			vm.PrimaryPart = part
			parts[b.Name] = part
			continue
		elseif ARM_PARTS[b.Name] then
			local src = (not o.EditorRig) and character and character:FindFirstChild(b.Name)
			part = if src and src:IsA("BasePart") then cleanArmClone(src) else fallbackArm(b.Name)
			part.Parent = vm
		elseif owner then
			part = knifeParts[b.Name]
			assert(part, "knife model is missing joint part " .. b.Name)
		else
			part = jointPart(b.Name, CFrame.identity)
			part.Parent = vm
		end
		parts[b.Name] = part
		local parentPart = parts[b.Parent]
		local internalKnifeJoint = owner and knifeOfBone(b.Parent) == owner
		if not internalKnifeJoint then
			motor(b.Joint, parentPart, part, jointC0(parentPart, b.Parent, b.Name), pivotInPart(part, b.Name))
		end
	end
	knifeModel.Parent = vm

	-- appearance: shirt / body colours apply through a Humanoid in the model
	if character and not o.EditorRig then
		local hum = Instance.new("Humanoid")
		hum.EvaluateStateMachine = false
		hum.RequiresNeck = false
		hum.DisplayDistanceType = Enum.HumanoidDisplayDistanceType.None
		hum.HealthDisplayType = Enum.HumanoidHealthDisplayType.AlwaysOff
		hum.BreakJointsOnDeath = false
		hum.Parent = vm
		for _, cls in ipairs({ "Shirt", "BodyColors" }) do
			local c = character:FindFirstChildOfClass(cls)
			if c then
				c:Clone().Parent = vm
			end
		end
	end
	if o.EditorRig then
		local ac = Instance.new("AnimationController")
		Instance.new("Animator").Parent = ac
		ac.Parent = vm
	end
	-- pose everything at rest once
	vm:PivotTo(CFrame.identity)
	return vm
end

--[[ Third-person / world model: the knife (open) welded to a character's
	RightHand with the same grip as the first-person idle pose.
	local world = KnifeBuilder.AttachToCharacter("Butterfly", knifeTemplate, character) ]]
function KnifeBuilder.AttachToCharacter(knife: string, knifeTemplate: Model, character: Model): Model?
	local hand = character:FindFirstChild("RightHand")
	if not (hand and hand:IsA("BasePart")) then
		warn("[KnifeBuilder] AttachToCharacter needs an R15 RightHand")
		return nil
	end
	local kd = RigData.Knives[knife]
	local model = knifeTemplate:Clone()
	model.Name = knife .. "_World"
	local root = model.PrimaryPart
	local rootBone = kd.Bones[1]
	local c0 = pivotInPart(hand, "RightHand") * BONE[rootBone].Offset * kd.IdleGrip
	local w = Instance.new("Weld")
	w.Name = "KnifeGrip"
	w.Part0 = hand
	w.Part1 = root
	w.C0 = c0
	w.Parent = root
	model.Parent = character
	return model
end

return KnifeBuilder
