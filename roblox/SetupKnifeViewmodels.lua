--[[
	SetupKnifeViewmodels - run ONCE in Roblox Studio (paste into the Command Bar, press Enter)

	Before running:
	  1. Insert export/roblox/KnifeSystem.rbxmx into ReplicatedStorage
	     (right-click ReplicatedStorage > Insert from File...).
	  2. Import export/meshes/Butterfly.fbx and export/meshes/Karambit.fbx with
	     the 3D Importer (Home/Avatar > Import 3D) into the Workspace. Keep the
	     default settings; textures embedded in the FBX become SurfaceAppearances.

	What it does:
	  * finds the imported MeshParts by name (BF_..._Mesh, KR_..._Mesh...),
	  * builds ReplicatedStorage.KnifeSystem.Knives.Butterfly / .Karambit
	    (joint parts + Motor6Ds + welded meshes, correct sizes),
	  * builds Workspace.KnifeAnimRig_Butterfly / _Karambit: block R15 arm rigs
	    with an AnimationController, so you can open the KeyframeSequences in
	    the Animation Editor (and publish them if you prefer Animation ids).
	The imported models can be deleted afterwards.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local KnifeSystem = ReplicatedStorage:FindFirstChild("KnifeSystem")
assert(KnifeSystem, "Insert KnifeSystem.rbxmx into ReplicatedStorage first")
local KnifeBuilder = require(KnifeSystem.KnifeBuilder)

local function findMesh(name: string)
	local best = nil
	for _, root in ipairs({ Workspace, game:GetService("ServerStorage"), ReplicatedStorage }) do
		for _, d in ipairs(root:GetDescendants()) do
			if d:IsA("MeshPart") and not d:IsDescendantOf(KnifeSystem) then
				if d.Name == name then
					return d
				elseif not best and d.Name:sub(1, #name) == name and d.Name:sub(#name + 1):match("^%.%d+$") then
					best = d -- e.g. "BF_Blade_Mesh.001"
				end
			end
		end
	end
	return best
end

local knivesFolder = KnifeSystem:FindFirstChild("Knives")
if not knivesFolder then
	knivesFolder = Instance.new("Folder")
	knivesFolder.Name = "Knives"
	knivesFolder.Parent = KnifeSystem
end

for i, knife in ipairs({ "Butterfly", "Karambit" }) do
	local model = KnifeBuilder.BuildKnifeModel(knife, findMesh)
	local old = knivesFolder:FindFirstChild(knife)
	if old then
		old:Destroy()
	end
	model.Parent = knivesFolder

	local rigName = "KnifeAnimRig_" .. knife
	local oldRig = Workspace:FindFirstChild(rigName)
	if oldRig then
		oldRig:Destroy()
	end
	local rig = KnifeBuilder.BuildViewmodel(knife, model, nil, { EditorRig = true })
	rig.Name = rigName
	rig.Parent = Workspace
	rig:PivotTo(CFrame.new(i * 8, 12, 0))
	print(("[KnifeSetup] %s: %d parts, editor rig %s"):format(knife, #model:GetChildren(), rig:GetFullName()))
end
print("[KnifeSetup] done - play-test and press 1 / 2 (KnifeClientExample)")
