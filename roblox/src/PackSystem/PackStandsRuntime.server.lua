--[[
	PackStandsRuntime (Script -> ServerScriptService): animates the stands in
	Workspace.PackStands - weapons slowly spin and bob above their mounts, all
	skin effects run (SkinVFX).
]]
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local PackSystem = ReplicatedStorage:WaitForChild("PackSystem")
local SkinVFX = require(PackSystem:WaitForChild("SkinVFX"))

local stands = Workspace:WaitForChild("PackStands")
local displays = {}

local function register(model)
	SkinVFX.Apply(model)
	for _, d in ipairs(model:GetDescendants()) do
		if d:IsA("Model") and d:GetAttribute("DisplayBase") then
			table.insert(displays, { model = d, base = d:GetAttribute("DisplayBase"), phase = math.random() * 6.28 })
			SkinVFX.Apply(d)
		end
	end
end

for _, s in ipairs(stands:GetChildren()) do
	register(s)
end
stands.ChildAdded:Connect(register)

RunService.Heartbeat:Connect(function()
	local t = os.clock()
	for _, d in ipairs(displays) do
		if d.model.Parent then
			local spin = CFrame.Angles(0, t * 0.6 + d.phase, 0)
			local bob = CFrame.new(0, math.sin(t * 1.4 + d.phase) * 0.15, 0)
			d.model:PivotTo(d.base * bob * spin)
		end
	end
end)
