--[[
	Plays the KeyframeSequences parsed from the exported .rbxmx with
	KnifeAnimator (mock Roblox API) and compares the Motor6D transforms with
	the Blender source.  Data: KFS_DATA (path to kfs_data.luau).
]]
local Mock = __load_file("roblox/tests/mock_roblox.luau")()
local SRC = SRC_DIR or "roblox/src/KnifeSystem"
local KS = Instance.new("Folder")
Mock.module(SRC .. "/KnifeAnimator.lua", "KnifeAnimator", KS)
local Animator = require(KS.KnifeAnimator)
local data = __load_file(KFS_DATA)()

local POS_TOL, ROT_TOL = 0.02, 0.02 -- studs / rotation-matrix element (~1.1 deg)
local failures = 0

local function buildPose(t, parent)
	local p = Instance.new("Pose")
	p.Name = t.Name
	p.CFrame = CFrame.new(table.unpack(t.CFrame))
	p.Weight = t.Weight
	p.Parent = parent
	for _, c in ipairs(t.Children) do
		buildPose(c, p)
	end
end

for _, clip in ipairs(data.clips) do
	local kfs = Instance.new("KeyframeSequence")
	kfs.Name = clip.Name
	kfs.Loop = clip.Loop
	local nMarkers = 0
	for _, k in ipairs(clip.Keyframes) do
		local kf = Instance.new("Keyframe")
		kf.Time = k.Time
		kf.Parent = kfs
		for _, p in ipairs(k.Poses) do
			buildPose(p, kf)
		end
		for _, m in ipairs(k.Markers) do
			local mk = Instance.new("KeyframeMarker")
			mk.Name = m.Name
			mk.Value = m.Value
			mk.Parent = kf
			nMarkers += 1
		end
	end
	local compiled = Animator.Compile(kfs)
	local ref = data.refs[clip.Name]
	if not ref then
		print("skip (no reference) " .. clip.Name)
		continue
	end
	if nMarkers ~= #ref.markers then
		failures += 1
		print(("FAIL %s: %d markers in rbxmx, %d in source"):format(clip.Name, nMarkers, #ref.markers))
	end
	local maxP, maxR = 0, 0
	for _, s in ipairs(ref.samples) do
		for joint, l in pairs(s.T) do
			local j = compiled.Joints[joint]
			if not j then
				failures += 1
				print(("FAIL %s: joint %s missing"):format(clip.Name, joint))
				continue
			end
			local got = Animator.Sample(j, s.t)
			local exp = CFrame.new(table.unpack(l))
			local dp = (got.Position - exp.Position).Magnitude
			local dr = 0
			for i = 1, 9 do
				dr = math.max(dr, math.abs(got.r[i] - exp.r[i]))
			end
			maxP, maxR = math.max(maxP, dp), math.max(maxR, dr)
			if dp > POS_TOL or dr > ROT_TOL then
				failures += 1
				print(("FAIL %s t=%.3f %s: dp=%.4f dr=%.4f"):format(clip.Name, s.t, joint, dp, dr))
			end
		end
	end
	print(("%-20s %3d keyframes, length %.2f s, max err pos %.4f rot %.4f, markers %d"):format(
		clip.Name, #clip.Keyframes, compiled.Length, maxP, maxR, nMarkers))
end
if failures > 0 then
	error(failures .. " KFS check(s) failed")
end
print("ALL KFS TESTS PASSED")
