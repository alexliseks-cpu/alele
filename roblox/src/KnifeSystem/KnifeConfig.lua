--[[
	KnifeConfig - tweak here, no need to touch the other modules.
]]

return {
	-- viewmodel placement relative to the camera (the clips were authored with
	-- the HumanoidRootPart of the viewmodel exactly at the camera)
	ViewmodelOffset = CFrame.new(0, 0, 0),

	-- render the viewmodel only when the camera is in first person
	FirstPersonOnly = true,

	-- arms: the player's own avatar arms are cloned (R15). These colours are used
	-- only when the character has no R15 arms (R6, not loaded yet, editor rig).
	FallbackSleeveColor = Color3.fromRGB(27, 27, 30),
	FallbackSkinColor = Color3.fromRGB(204, 110, 44),

	-- timings
	AttackCooldown = 0.42, -- light attack (Attack1 / Attack2 alternate)
	HeavyCooldown = 0.95, -- heavy attack
	FadeIn = 0.06, -- crossfade into an action
	IdleFade = 0.15, -- action -> idle blend at the end of a clip

	-- procedural motion layered on top of the clips
	Sway = {
		Enabled = true,
		Amount = 0.55, -- how much the viewmodel lags behind camera rotation
		MaxAngle = math.rad(6),
		Smooth = 14,
	},
	Bob = {
		Enabled = true,
		Amplitude = Vector2.new(0.035, 0.028), -- studs (x, y) at walk speed 16
		Frequency = 1.1, -- cycles per second at walk speed 16
	},
	CameraShake = true, -- apply the clips' CameraBone motion to the camera

	-- melee hit test fired on the clips' "Hit" markers (see KnifeViewmodel.Hit)
	HitRange = { light = 6, heavy = 6.5 },

	-- optional sounds: marker value -> SoundId ("" = silent)
	Sounds = {
		deploy = "",
		flip = "",
		latch = "",
		spin = "",
		catch = "",
		swing = "",
		swing_heavy = "",
	},
	SoundVolume = 0.6,

	-- clip names inside ReplicatedStorage.KnifeSystem.Animations.<Knife>
	Clips = {
		Butterfly = {
			Idle = "Butterfly_Idle",
			Draw = "Butterfly_Draw",
			Inspect = "Butterfly_Inspect",
			Attack1 = "Butterfly_Attack1",
			Attack2 = "Butterfly_Attack2",
			Heavy = "Butterfly_Heavy",
		},
		Karambit = {
			Idle = "Karambit_Idle",
			Draw = "Karambit_Draw",
			Inspect = "Karambit_Inspect",
			Attack1 = "Karambit_Attack1",
			Attack2 = "Karambit_Attack2",
			Heavy = "Karambit_Heavy",
		},
	},
}
