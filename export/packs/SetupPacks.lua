--[[
	SetupPacks - run ONCE in Roblox Studio (paste into the Command Bar, press Enter)

	Before running:
	  1. Insert export/packs/PackSystem.rbxmx into ReplicatedStorage (KnifeSystem must be there too).
	  2. Import every FBX from export/packs/meshes with the 3D Importer (Lava_AR, Lava_Deagle,
	     Lava_Karambit, Lava_Stand, Ice_Sniper, Ice_Revolver, Ice_Butterfly, Ice_Stand).
	What it does:
	  * builds ReplicatedStorage.PackSystem.Models.<Item> for the guns (PrimaryPart "Handle" at the grip)
	  * builds the knife skins into ReplicatedStorage.KnifeSystem.Knives (Karambit_Lava, Butterfly_Ice)
	    -> use them with KnifeViewmodel.new("Karambit", "Lava") / KnifeViewmodel.new("Butterfly", "Ice")
	  * builds Workspace.PackStands with both stands, the pack weapons displayed on them,
	    the pack titles and all effects; moves PackStandsRuntime into ServerScriptService.
	Move the stands where you want them afterwards (PivotTo / drag).
]]
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")
local ServerScriptService = game:GetService("ServerScriptService")

local PackSystem = assert(ReplicatedStorage:FindFirstChild("PackSystem"), "Insert PackSystem.rbxmx into ReplicatedStorage first")
local KnifeSystem = ReplicatedStorage:FindFirstChild("KnifeSystem")
local PackData = require(PackSystem.PackData)
local PackBuilder = require(PackSystem.PackBuilder)

local function findMesh(name)
	local best
	for _, d in ipairs(Workspace:GetDescendants()) do
		if d:IsA("MeshPart") and not d:IsDescendantOf(PackSystem) and not (Workspace:FindFirstChild("PackStands") and d:IsDescendantOf(Workspace.PackStands)) then
			if d.Name == name then
				return d
			elseif not best and d.Name:sub(1, #name) == name and d.Name:sub(#name + 1):match("^%.%d+$") then
				best = d
			end
		end
	end
	return best
end

local models = PackSystem:FindFirstChild("Models") or Instance.new("Folder")
models.Name = "Models"
models.Parent = PackSystem

local built = {}
for name, d in pairs(PackData.Items) do
	local m
	if d.Kind == "knife_skin" then
		if KnifeSystem then
			m = PackBuilder.BuildKnifeSkin(name, findMesh, require(KnifeSystem.KnifeBuilder))
			local old = KnifeSystem.Knives:FindFirstChild(m.Name)
			if old then old:Destroy() end
			m.Parent = KnifeSystem.Knives
		else
			warn("[SetupPacks] KnifeSystem missing - skipping knife skin " .. name)
		end
	else
		m = PackBuilder.BuildItem(name, findMesh)
		if d.Kind == "weapon" then
			local old = models:FindFirstChild(name)
			if old then old:Destroy() end
			m.Parent = models
		end
	end
	built[name] = m
	print("[SetupPacks] built " .. name)
end

-- stands -----------------------------------------------------------------------
local stands = Workspace:FindFirstChild("PackStands")
if stands then stands:Destroy() end
stands = Instance.new("Folder")
stands.Name = "PackStands"
stands.Parent = Workspace

local TITLE = { Lava_Stand = { "LAVA PACK", Color3.fromRGB(255, 140, 40) }, Ice_Stand = { "ICE PACK", Color3.fromRGB(140, 220, 255) } }
local x = 0
for name, d in pairs(PackData.Items) do
	if d.Kind == "stand" and built[name] then
		local stand = built[name]
		for _, p in ipairs(stand:GetDescendants()) do
			if p:IsA("BasePart") then
				p.Anchored = true
				p.CanCollide = true
			end
		end
		stand:PivotTo(CFrame.new(x, 0.05, -30))
		x += 16
		stand.Parent = stands
		local plate = stand:FindFirstChild(name .. "_SignPlate")
		if plate and TITLE[name] then
			local gui = Instance.new("SurfaceGui")
			gui.Face = Enum.NormalId.Front
			gui.LightInfluence = 0
			gui.Brightness = 2
			gui.PixelsPerStud = 60
			local t = Instance.new("TextLabel")
			t.Size = UDim2.fromScale(1, 1)
			t.BackgroundTransparency = 1
			t.Text = TITLE[name][1]
			t.TextScaled = true
			t.Font = Enum.Font.GothamBlack
			t.TextColor3 = TITLE[name][2]
			t.TextStrokeTransparency = 0.2
			t.Parent = gui
			gui.Parent = plate
		end
		for _, at in ipairs(stand:GetDescendants()) do
			if at:IsA("Attachment") and at:GetAttribute("MountItem") then
				local item = at:GetAttribute("MountItem")
				local src = built[item]
				if src then
					local disp = src:Clone()
					disp.Name = "Display_" .. item
					for _, p in ipairs(disp:GetDescendants()) do
						if p:IsA("BasePart") then p.Anchored = true end
					end
					local baseCF = at.WorldCFrame
					disp:SetAttribute("DisplayBase", baseCF)
					disp:PivotTo(baseCF)
					disp.Parent = stand
				end
			end
		end
	end
end

local rt = PackSystem:FindFirstChild("PackStandsRuntime")
if rt then
	local old = ServerScriptService:FindFirstChild("PackStandsRuntime")
	if old then old:Destroy() end
	rt:Clone().Parent = ServerScriptService
end
print("[SetupPacks] done - Play to see the stands animate")
