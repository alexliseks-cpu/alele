--!nonstrict
--[[
	PackBuilder - assembles the Limited Pack items from the imported MeshParts.
	  PackBuilder.BuildItem(name, lookup)  -> Model (weapons / stands; PrimaryPart "Handle" = grip / floor centre)
	  PackBuilder.BuildKnifeSkin(name, lookup) -> knife Model usable by KnifeSystem (Knives.<Knife>_<Skin>)
	lookup(meshName) -> MeshPart? from the 3D importer.
	Attachments named VFX_* carry attributes VFXPreset/VFXRate/VFXSize/VFXColor (SkinVFX reads them);
	stands get MOUNT_<Item> attachments.
]]
local PackData = require(script.Parent.PackData)

local PackBuilder = {}

local MATERIAL = {
	Neon = Enum.Material.Neon, Glass = Enum.Material.Glass, ForceField = Enum.Material.ForceField,
	Metal = Enum.Material.Metal, SmoothPlastic = Enum.Material.SmoothPlastic, Ice = Enum.Material.Ice,
	Basalt = Enum.Material.Basalt, CrackedLava = Enum.Material.CrackedLava, Slate = Enum.Material.Slate,
	Glacier = Enum.Material.Glacier, Snow = Enum.Material.Snow, Rock = Enum.Material.Rock,
}

local function flags(p: BasePart)
	p.Anchored = false
	p.CanCollide = false
	p.CanQuery = false
	p.CanTouch = false
	p.Massless = true
	p.CastShadow = p.Material ~= Enum.Material.Neon
end

local function makePart(item: string, d, lookup)
	local src = lookup(d.Name)
	if not src then
		warn("[PackBuilder] mesh not found: " .. d.Name)
		return nil
	end
	local mp = src:Clone()
	mp.Name = d.Name
	for _, c in ipairs(mp:GetChildren()) do
		if not c:IsA("SurfaceAppearance") then
			c:Destroy()
		end
	end
	mp.Size = d.Size
	mp.CFrame = CFrame.new(d.Center)
	mp.Material = MATERIAL[d.Material] or Enum.Material.SmoothPlastic
	mp.Color = d.Color
	mp.Transparency = d.Transparency
	if d.Pulse and d.Pulse > 0 then
		mp:SetAttribute("Pulse", d.Pulse)
	end
	if mp.Material == Enum.Material.Neon or mp.Material == Enum.Material.Glass or mp.Material == Enum.Material.ForceField then
		-- glow / refraction come from the material: a SurfaceAppearance would hide it
		local sa = mp:FindFirstChildOfClass("SurfaceAppearance")
		if sa then
			sa:Destroy()
		end
	elseif d.Textures and not mp:FindFirstChildOfClass("SurfaceAppearance") then
		local tex = PackData.Textures[d.Textures]
		if tex and tex.ColorMap ~= "" then
			pcall(function()
				local sa = Instance.new("SurfaceAppearance")
				sa.ColorMap, sa.NormalMap, sa.RoughnessMap, sa.MetalnessMap = tex.ColorMap, tex.NormalMap, tex.RoughnessMap, tex.MetalnessMap
				sa.Parent = mp
			end)
		end
	end
	flags(mp)
	return mp
end

local function weld(p0: BasePart, p1: BasePart)
	local w = Instance.new("Weld")
	w.Name = "PackWeld"
	w.Part0 = p0
	w.Part1 = p1
	w.C0 = p0.CFrame:Inverse() * p1.CFrame
	w.Parent = p1
end

local function vfxAttachment(a, parent: BasePart)
	local at = Instance.new("Attachment")
	at.Name = a.Name
	at.CFrame = parent.CFrame:Inverse() * CFrame.new(a.Position)
	at:SetAttribute("VFXPreset", a.Preset)
	at:SetAttribute("VFXRate", a.Rate)
	at:SetAttribute("VFXSize", a.Size)
	if a.Color then
		at:SetAttribute("VFXColor", a.Color)
	end
	at.Parent = parent
	return at
end

function PackBuilder.BuildItem(name: string, lookup: (string) -> MeshPart?): Model
	local d = PackData.Items[name]
	assert(d and d.Kind ~= "knife_skin", "not a weapon/stand item: " .. tostring(name))
	local model = Instance.new("Model")
	model.Name = name
	local handle = Instance.new("Part")
	handle.Name = "Handle"
	handle.Size = Vector3.new(0.2, 0.2, 0.2)
	handle.Transparency = 1
	handle.CFrame = CFrame.identity
	flags(handle)
	handle.Parent = model
	model.PrimaryPart = handle
	for _, pd in ipairs(d.Parts) do
		local mp = makePart(name, pd, lookup)
		if mp then
			mp.Parent = model
			weld(handle, mp)
		end
	end
	for _, a in ipairs(d.Attachments) do
		vfxAttachment(a, handle)
	end
	for _, m in ipairs(d.Mounts) do
		local at = Instance.new("Attachment")
		at.Name = m.Name
		at.CFrame = m.CFrame
		at:SetAttribute("MountItem", m.Item)
		at.Parent = handle
	end
	return model
end

-- knife skin: base knife rig (KnifeSystem) with skin meshes + overlays + VFX
function PackBuilder.BuildKnifeSkin(name: string, lookup: (string) -> MeshPart?, KnifeBuilder): Model
	local d = PackData.Items[name]
	assert(d and d.Kind == "knife_skin", "not a knife skin: " .. tostring(name))
	local byBase = {}
	for _, pd in ipairs(d.Parts) do
		if pd.Base then
			byBase[pd.Src] = pd
		end
	end
	local model = KnifeBuilder.BuildKnifeModel(d.Knife, function(baseName)
		local pd = byBase[baseName]
		return pd and lookup(pd.Name) or nil
	end)
	model.Name = d.Knife .. "_" .. name:match("^(%a+)_")
	-- skin materials on base parts
	for _, pd in ipairs(d.Parts) do
		if pd.Base then
			local mp = model:FindFirstChild(pd.Src)
			if mp then
				mp.Material = MATERIAL[pd.Material] or mp.Material
				mp.Color = pd.Color
				mp.Transparency = pd.Transparency
			end
		end
	end
	local joints = {}
	for _, p in ipairs(model:GetChildren()) do
		if p:IsA("BasePart") and p:GetAttribute("KnifeJointPart") then
			joints[p.Name] = p
		end
	end
	local root = model.PrimaryPart
	for _, pd in ipairs(d.Parts) do
		if not pd.Base then
			local mp = makePart(name, pd, lookup)
			if mp then
				mp.Parent = model
				weld(joints[pd.Bone or ""] or root, mp)
			end
		end
	end
	for _, a in ipairs(d.Attachments) do
		vfxAttachment(a, joints[a.Bone or ""] or root)
	end
	return model
end

return PackBuilder
