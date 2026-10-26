--!nonstrict
--[[
	SkinVFX - effects for the Limited Pack skins (works on server and client).

	SkinVFX.Apply(model)   -- creates emitters/lights on every Attachment that has a
	                         "VFXPreset" attribute and starts the Neon glow pulse
	SkinVFX.Remove(model)
	Presets: Embers, Smoke, Fire, HeatGlow, Drip (lava); Frost, Snow, Sparkle, IceGlow (ice)
]]
local RunService = game:GetService("RunService")

local SkinVFX = {}

local TEX = {
	spark = "rbxasset://textures/particles/sparkles_main.dds",
	smoke = "rbxasset://textures/particles/smoke_main.dds",
	fire = "rbxasset://textures/particles/fire_main.dds",
	firespark = "rbxasset://textures/particles/fire_sparks_main.dds",
}

local function ns(...)
	local pts = { ... }
	local kps = {}
	for i = 1, #pts, 2 do
		table.insert(kps, NumberSequenceKeypoint.new(pts[i], pts[i + 1]))
	end
	return NumberSequence.new(kps)
end

local function cs(...)
	local pts = { ... }
	local kps = {}
	for i = 1, #pts, 2 do
		table.insert(kps, ColorSequenceKeypoint.new(pts[i], pts[i + 1]))
	end
	return ColorSequence.new(kps)
end

local ORANGE, YELLOW, RED = Color3.fromRGB(255, 120, 20), Color3.fromRGB(255, 220, 90), Color3.fromRGB(200, 30, 10)
local CYAN, WHITE, ICE = Color3.fromRGB(110, 210, 255), Color3.fromRGB(255, 255, 255), Color3.fromRGB(180, 235, 255)

-- emitter presets: properties + light
SkinVFX.Presets = {
	Embers = { Texture = TEX.spark, Color = cs(0, YELLOW, 0.4, ORANGE, 1, RED), LightEmission = 1, LightInfluence = 0,
		Size = ns(0, 0.12, 0.7, 0.08, 1, 0), Transparency = ns(0, 0, 0.8, 0.2, 1, 1), Lifetime = NumberRange.new(0.7, 1.6),
		Rate = 14, Speed = NumberRange.new(0.6, 2.2), SpreadAngle = Vector2.new(35, 35), Acceleration = Vector3.new(0, 2.5, 0),
		Drag = 1.2, RotSpeed = NumberRange.new(-90, 90) },
	Smoke = { Texture = TEX.smoke, Color = cs(0, Color3.fromRGB(70, 40, 30), 1, Color3.fromRGB(25, 25, 25)), LightEmission = 0,
		LightInfluence = 1, Size = ns(0, 0.25, 1, 1.2), Transparency = ns(0, 1, 0.2, 0.65, 1, 1), Lifetime = NumberRange.new(1.4, 2.4),
		Rate = 4, Speed = NumberRange.new(0.2, 0.6), SpreadAngle = Vector2.new(20, 20), Acceleration = Vector3.new(0, 1.2, 0),
		Rotation = NumberRange.new(0, 360), RotSpeed = NumberRange.new(-30, 30) },
	Fire = { Texture = TEX.fire, Color = cs(0, YELLOW, 0.5, ORANGE, 1, RED), LightEmission = 1, LightInfluence = 0,
		Size = ns(0, 0.35, 1, 0), Transparency = ns(0, 0.2, 1, 1), Lifetime = NumberRange.new(0.35, 0.6), Rate = 24,
		Speed = NumberRange.new(0.5, 1.5), SpreadAngle = Vector2.new(15, 15), Acceleration = Vector3.new(0, 3, 0),
		Rotation = NumberRange.new(0, 360), RotSpeed = NumberRange.new(-60, 60) },
	Drip = { Texture = TEX.spark, Color = cs(0, YELLOW, 1, ORANGE), LightEmission = 1, LightInfluence = 0,
		Size = ns(0, 0.07, 1, 0.04), Lifetime = NumberRange.new(0.6, 0.9), Rate = 3, Speed = NumberRange.new(0, 0),
		Acceleration = Vector3.new(0, -14, 0) },
	Frost = { Texture = TEX.smoke, Color = cs(0, ICE, 1, CYAN), LightEmission = 0.3, LightInfluence = 0.5,
		Size = ns(0, 0.2, 1, 1.0), Transparency = ns(0, 1, 0.25, 0.7, 1, 1), Lifetime = NumberRange.new(1.2, 2.2), Rate = 6,
		Speed = NumberRange.new(0.1, 0.4), SpreadAngle = Vector2.new(60, 60), Acceleration = Vector3.new(0, -0.4, 0),
		Rotation = NumberRange.new(0, 360), RotSpeed = NumberRange.new(-20, 20) },
	Snow = { Texture = TEX.spark, Color = cs(0, WHITE, 1, ICE), LightEmission = 0.6, LightInfluence = 0.3,
		Size = ns(0, 0.06, 1, 0.04), Transparency = ns(0, 0, 0.8, 0.1, 1, 1), Lifetime = NumberRange.new(2, 3.5), Rate = 10,
		Speed = NumberRange.new(0.2, 0.6), SpreadAngle = Vector2.new(180, 180), Acceleration = Vector3.new(0, -0.8, 0),
		Drag = 0.5, RotSpeed = NumberRange.new(-120, 120) },
	Sparkle = { Texture = TEX.spark, Color = cs(0, WHITE, 1, CYAN), LightEmission = 1, LightInfluence = 0,
		Size = ns(0, 0, 0.3, 0.22, 1, 0), Lifetime = NumberRange.new(0.4, 0.8), Rate = 7, Speed = NumberRange.new(0, 0.1),
		Rotation = NumberRange.new(0, 360), RotSpeed = NumberRange.new(-200, 200), SpreadAngle = Vector2.new(180, 180) },
}
SkinVFX.Lights = {
	HeatGlow = { Color = ORANGE, Brightness = 2.2, Range = 7, Flicker = 0.35 },
	IceGlow = { Color = CYAN, Brightness = 1.8, Range = 7, Flicker = 0.08 },
}

local active = {} -- model -> { neon = {{part, base, hz}}, lights = {{light, base, amt}} }
local conn

local function step(t)
	for model, st in pairs(active) do
		if not model.Parent then
			active[model] = nil
			continue
		end
		for _, n in ipairs(st.neon) do
			local k = 0.72 + 0.28 * math.sin(t * n.hz * math.pi * 2 + n.phase)
			n.part.Color = Color3.new(n.base.R * k, n.base.G * k, n.base.B * k)
		end
		for _, l in ipairs(st.lights) do
			local f = 1 - l.amt + l.amt * (0.5 + 0.5 * math.noise(t * 3, l.seed))
			l.light.Brightness = l.base * f
		end
	end
	if next(active) == nil and conn then
		conn:Disconnect()
		conn = nil
	end
end

function SkinVFX.Apply(model: Instance, opts: { Scale: number? }?)
	local scale = (opts and opts.Scale) or 1
	local st = { neon = {}, lights = {} }
	for _, d in ipairs(model:GetDescendants()) do
		if d:IsA("Attachment") and d:GetAttribute("VFXPreset") then
			local preset = d:GetAttribute("VFXPreset")
			local rate = d:GetAttribute("VFXRate") or 1
			local size = (d:GetAttribute("VFXSize") or 1) * scale
			local p = SkinVFX.Presets[preset]
			local l = SkinVFX.Lights[preset]
			if p then
				local e = Instance.new("ParticleEmitter")
				e.Name = "VFX_" .. preset
				for k, v in pairs(p) do
					e[k] = v
				end
				e.Rate = p.Rate * rate
				local kps = {}
				for _, kp in ipairs(p.Size.Keypoints) do
					table.insert(kps, NumberSequenceKeypoint.new(kp.Time, kp.Value * size))
				end
				e.Size = NumberSequence.new(kps)
				local c = d:GetAttribute("VFXColor")
				if typeof(c) == "Color3" then
					e.Color = ColorSequence.new(c)
				end
				e.Parent = d
			elseif l then
				local pl = Instance.new("PointLight")
				pl.Name = "VFX_" .. preset
				pl.Color = l.Color
				pl.Brightness = l.Brightness
				pl.Range = l.Range * size
				pl.Shadows = false
				pl.Parent = d
				table.insert(st.lights, { light = pl, base = l.Brightness, amt = l.Flicker, seed = math.random() * 100 })
			end
		elseif d:IsA("BasePart") and d.Material == Enum.Material.Neon then
			local hz = d:GetAttribute("Pulse") or 0
			if hz > 0 then
				table.insert(st.neon, { part = d, base = d.Color, hz = hz, phase = math.random() * 6.28 })
			end
		end
	end
	active[model] = st
	if not conn then
		conn = RunService.Heartbeat:Connect(function()
			step(os.clock())
		end)
	end
end

function SkinVFX.Remove(model: Instance)
	local st = active[model]
	if st then
		for _, n in ipairs(st.neon) do
			n.part.Color = n.base
		end
	end
	active[model] = nil
	for _, d in ipairs(model:GetDescendants()) do
		if (d:IsA("ParticleEmitter") or d:IsA("PointLight")) and d.Name:sub(1, 4) == "VFX_" then
			d:Destroy()
		end
	end
end

return SkinVFX
