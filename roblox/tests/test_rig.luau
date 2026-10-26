--[[
	Offline end-to-end rig test (plain Luau + mock_roblox.luau).
	usage: luaurun roblox/tests/test_rig.luau   (env KNIFE_TEST_DIR = dir with vectors.luau + RigData.lua)

	Builds both knife viewmodels with KnifeBuilder (fallback R15 block arms),
	applies the Motor6D.Transforms exported from Blender, walks the joint tree
	(Part1 = Part0 * C0 * Transform * C1:Inverse()) and checks every joint
	pivot against the pose Blender computed.  Then checks KnifeAnimator
	interpolation, markers and fading on a synthetic KeyframeSequence.
]]

local DIR = TEST_DIR or "."
local SRC = SRC_DIR or "roblox/src/KnifeSystem"
local Mock = __load_file("roblox/tests/mock_roblox.luau")()

local KS = Instance.new("Folder")
KS.Name = "KnifeSystem"
Mock.module(DIR .. "/RigData.lua", "RigData", KS)
Mock.module(SRC .. "/KnifeConfig.lua", "KnifeConfig", KS)
Mock.module(SRC .. "/KnifeAnimator.lua", "KnifeAnimator", KS)
Mock.module(SRC .. "/KnifeBuilder.lua", "KnifeBuilder", KS)

local RigData = require(KS.RigData)
local Builder = require(KS.KnifeBuilder)
local Animator = require(KS.KnifeAnimator)
local vectors = __load_file(DIR .. "/vectors.luau")()

local failures = 0
local function check(cond, msg)
	if not cond then
		failures += 1
		print("FAIL " .. msg)
	end
end

local function cfFromList(l)
	return CFrame.new(table.unpack(l))
end

local function rotErr(a, b)
	-- max abs difference of rotation matrices
	local m = 0
	for i = 1, 9 do
		m = math.max(m, math.abs(a.r[i] - b.r[i]))
	end
	return m
end

for knife, frames in pairs(vectors) do
	local template = Builder.BuildKnifeModel(knife, function()
		return nil
	end)
	local vm = Builder.BuildViewmodel(knife, template, nil, { EditorRig = true })
	-- collect motors
	local motors = {}
	local partsByName = {}
	for _, d in ipairs(vm:GetDescendants()) do
		if d:IsA("Motor6D") then
			motors[d.Part1.Name] = d
		end
		if d:IsA("BasePart") then
			partsByName[d.Name] = d
		end
	end
	check(partsByName.HumanoidRootPart ~= nil, knife .. ": no root")
	local maxPos, maxRot, n = 0, 0, 0
	for _, fr in ipairs(frames) do
		for name, m in pairs(motors) do
			local tl = fr.transforms[name]
			m.Transform = if tl then cfFromList(tl) else CFrame.identity
		end
		-- world CFrames of all parts
		local world = { HumanoidRootPart = CFrame.identity }
		local function solve(name)
			if world[name] then
				return world[name]
			end
			local m = motors[name]
			assert(m, "no motor for " .. name)
			local w = solve(m.Part0.Name) * m.C0 * m.Transform * m.C1:Inverse()
			world[name] = w
			return w
		end
		for name, expected in pairs(fr.world) do
			local part = partsByName[name]
			check(part ~= nil, knife .. ": missing part " .. name)
			if part then
				local w = solve(name) * Builder.PivotInPart(part, name)
				local e = cfFromList(expected)
				local dp = (w.Position - e.Position).Magnitude
				local dr = rotErr(w, e)
				maxPos = math.max(maxPos, dp)
				maxRot = math.max(maxRot, dr)
				n += 1
				if dp > 1e-3 or dr > 1e-3 then
					check(false, string.format("%s t=%.3f %s: pos err %.5f rot err %.5f\n  got %s\n  exp %s", knife, fr.t, name, dp, dr, tostring(w), tostring(e)))
				end
			end
		end
	end
	print(string.format("%s: %d joint checks, max pos err %.2e studs, max rot err %.2e", knife, n, maxPos, maxRot))
end

-- KnifeAnimator: interpolation / markers / fading ---------------------------
do
	local kfs = Instance.new("KeyframeSequence")
	kfs.Name = "Test_Clip"
	local times = { 0, 0.5, 1.0 }
	local xs = { 0, 1, 0 }
	for i, t in ipairs(times) do
		local kf = Instance.new("Keyframe")
		kf.Time = t
		kf.Parent = kfs
		local root = Instance.new("Pose")
		root.Name = "HumanoidRootPart"
		root.Weight = 0
		root.Parent = kf
		local p = Instance.new("Pose")
		p.Name = "RightHand"
		p.CFrame = CFrame.new(xs[i], 0, 0)
		p.Parent = root
		if i == 2 then
			local mk = Instance.new("KeyframeMarker")
			mk.Name = "Hit"
			mk.Value = "light"
			mk.Parent = kf
		end
	end
	local model = Instance.new("Model")
	local a = Instance.new("Part")
	a.Name = "RightLowerArm"
	a.Parent = model
	local b = Instance.new("Part")
	b.Name = "RightHand"
	b.Parent = model
	local m = Instance.new("Motor6D")
	m.Part0 = a
	m.Part1 = b
	m.Parent = a
	local anim = Animator.new(model)
	anim:Load(kfs)
	local hits, ended = 0, 0
	anim.MarkerReached:Connect(function(clip, name, value)
		if name == "Hit" and value == "light" then
			hits += 1
		end
	end)
	anim.Ended:Connect(function()
		ended += 1
	end)
	anim:Play("Test_Clip", { FadeTime = 0 })
	anim:Update(0.25)
	check(math.abs(m.Transform.X - 0.5) < 1e-6, "lerp at 0.25 s: " .. tostring(m.Transform.X))
	anim:Update(0.3)
	check(hits == 1, "marker fired once, got " .. hits)
	check(math.abs(m.Transform.X - 0.9) < 1e-6, "lerp at 0.55 s: " .. tostring(m.Transform.X))
	anim:Update(0.6)
	check(ended == 1, "ended fired")
	anim:Update(0.2) -- fade out (0.12 s) completes
	check(#anim.Tracks == 0, "track removed after fade, tracks=" .. #anim.Tracks)
	check(m.Transform.X == 0, "back to identity")
	-- looping + layering
	kfs.Loop = true
	anim:Load(kfs)
	anim:Play("Test_Clip", { FadeTime = 0 })
	anim:Update(1.25)
	check(math.abs(m.Transform.X - 0.5) < 1e-6, "loop wrap: " .. tostring(m.Transform.X))
	check(hits == 2, "marker fired again in the loop, got " .. hits)
	print("KnifeAnimator checks done")
end

if failures > 0 then
	error(failures .. " check(s) failed")
end
print("ALL RIG TESTS PASSED")
