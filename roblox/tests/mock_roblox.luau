--[[
	Minimal Roblox API mock for offline tests (run with a plain Luau VM).
	Implements just what KnifeAnimator / KnifeBuilder need: CFrame, Vector3,
	Vector2, Instance tree, Enum names, task, require(ModuleScript).
	Exposes: Mock.module(path, name, parent) and the globals.
]]

local Mock = {}

-- Vector3 ----------------------------------------------------------------------
local V3 = {}
V3.__index = function(v, k)
	if k == "Magnitude" then
		return math.sqrt(v.X * v.X + v.Y * v.Y + v.Z * v.Z)
	elseif k == "Unit" then
		local m = math.sqrt(v.X * v.X + v.Y * v.Y + v.Z * v.Z)
		return Vector3.new(v.X / m, v.Y / m, v.Z / m)
	end
	return rawget(V3, k)
end
local function v3(x, y, z)
	return setmetatable({ X = x or 0, Y = y or 0, Z = z or 0 }, V3)
end
V3.__add = function(a, b) return v3(a.X + b.X, a.Y + b.Y, a.Z + b.Z) end
V3.__sub = function(a, b) return v3(a.X - b.X, a.Y - b.Y, a.Z - b.Z) end
V3.__unm = function(a) return v3(-a.X, -a.Y, -a.Z) end
V3.__mul = function(a, b)
	if type(a) == "number" then return v3(a * b.X, a * b.Y, a * b.Z) end
	if type(b) == "number" then return v3(a.X * b, a.Y * b, a.Z * b) end
	return v3(a.X * b.X, a.Y * b.Y, a.Z * b.Z)
end
V3.__div = function(a, b)
	if type(b) == "number" then return v3(a.X / b, a.Y / b, a.Z / b) end
	return v3(a.X / b.X, a.Y / b.Y, a.Z / b.Z)
end
V3.__tostring = function(a) return string.format("%.4f, %.4f, %.4f", a.X, a.Y, a.Z) end
V3.__eq = function(a, b) return a.X == b.X and a.Y == b.Y and a.Z == b.Z end
Vector3 = { new = v3, zero = v3(0, 0, 0), one = v3(1, 1, 1) }

local V2 = {}
V2.__index = V2
local function v2(x, y) return setmetatable({ X = x or 0, Y = y or 0 }, V2) end
V2.__add = function(a, b) return v2(a.X + b.X, a.Y + b.Y) end
V2.__mul = function(a, b)
	if type(b) == "number" then return v2(a.X * b, a.Y * b) end
	return v2(a.X * b.X, a.Y * b.Y)
end
V2.__div = function(a, b) return v2(a.X / b, a.Y / b) end
function V2:Lerp(b, t) return v2(self.X + (b.X - self.X) * t, self.Y + (b.Y - self.Y) * t) end
Vector2 = { new = v2, zero = v2(0, 0) }

-- CFrame -------------------------------------------------------------------------
local CF = {}
local function cf(x, y, z, r)
	return setmetatable({ x = x, y = y, z = z, r = r }, CF)
end
CF.__index = function(c, k)
	if k == "Position" or k == "p" then return v3(c.x, c.y, c.z) end
	if k == "X" then return c.x end
	if k == "Y" then return c.y end
	if k == "Z" then return c.z end
	if k == "Rotation" then return cf(0, 0, 0, c.r) end
	if k == "LookVector" then return v3(-c.r[3], -c.r[6], -c.r[9]) end
	if k == "RightVector" then return v3(c.r[1], c.r[4], c.r[7]) end
	if k == "UpVector" then return v3(c.r[2], c.r[5], c.r[8]) end
	return rawget(CF, k)
end
local function mulR(a, b)
	local r = {}
	for i = 0, 2 do
		for j = 0, 2 do
			r[i * 3 + j + 1] = a[i * 3 + 1] * b[j + 1] + a[i * 3 + 2] * b[3 + j + 1] + a[i * 3 + 3] * b[6 + j + 1]
		end
	end
	return r
end
CF.__mul = function(a, b)
	if getmetatable(b) == V3 then
		local r = a.r
		return v3(r[1] * b.X + r[2] * b.Y + r[3] * b.Z + a.x, r[4] * b.X + r[5] * b.Y + r[6] * b.Z + a.y,
			r[7] * b.X + r[8] * b.Y + r[9] * b.Z + a.z)
	end
	local r = a.r
	return cf(r[1] * b.x + r[2] * b.y + r[3] * b.z + a.x, r[4] * b.x + r[5] * b.y + r[6] * b.z + a.y,
		r[7] * b.x + r[8] * b.y + r[9] * b.z + a.z, mulR(a.r, b.r))
end
CF.__add = function(a, b) return cf(a.x + b.X, a.y + b.Y, a.z + b.Z, a.r) end
CF.__tostring = function(c)
	return string.format("CF(%.4f %.4f %.4f | %.3f %.3f %.3f %.3f %.3f %.3f %.3f %.3f %.3f)", c.x, c.y, c.z, table.unpack(c.r))
end
function CF:Inverse()
	local r = self.r
	local t = { r[1], r[4], r[7], r[2], r[5], r[8], r[3], r[6], r[9] }
	return cf(-(t[1] * self.x + t[2] * self.y + t[3] * self.z), -(t[4] * self.x + t[5] * self.y + t[6] * self.z),
		-(t[7] * self.x + t[8] * self.y + t[9] * self.z), t)
end
function CF:ToObjectSpace(o) return self:Inverse() * o end
function CF:GetComponents()
	return self.x, self.y, self.z, table.unpack(self.r)
end
local function toQuat(r)
	local m00, m01, m02, m10, m11, m12, m20, m21, m22 = table.unpack(r)
	local tr = m00 + m11 + m22
	local w, x, y, z
	if tr > 0 then
		local s = math.sqrt(tr + 1) * 2
		w, x, y, z = 0.25 * s, (m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s
	elseif m00 > m11 and m00 > m22 then
		local s = math.sqrt(1 + m00 - m11 - m22) * 2
		w, x, y, z = (m21 - m12) / s, 0.25 * s, (m01 + m10) / s, (m02 + m20) / s
	elseif m11 > m22 then
		local s = math.sqrt(1 + m11 - m00 - m22) * 2
		w, x, y, z = (m02 - m20) / s, (m01 + m10) / s, 0.25 * s, (m12 + m21) / s
	else
		local s = math.sqrt(1 + m22 - m00 - m11) * 2
		w, x, y, z = (m10 - m01) / s, (m02 + m20) / s, (m12 + m21) / s, 0.25 * s
	end
	return w, x, y, z
end
local function fromQuat(w, x, y, z)
	return { 1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
		2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
		2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y) }
end
function CF:Lerp(b, t)
	local w1, x1, y1, z1 = toQuat(self.r)
	local w2, x2, y2, z2 = toQuat(b.r)
	local d = w1 * w2 + x1 * x2 + y1 * y2 + z1 * z2
	if d < 0 then
		w2, x2, y2, z2, d = -w2, -x2, -y2, -z2, -d
	end
	local s1, s2
	if d > 0.9995 then
		s1, s2 = 1 - t, t
	else
		local th = math.acos(d)
		s1, s2 = math.sin((1 - t) * th) / math.sin(th), math.sin(t * th) / math.sin(th)
	end
	local w, x, y, z = w1 * s1 + w2 * s2, x1 * s1 + x2 * s2, y1 * s1 + y2 * s2, z1 * s1 + z2 * s2
	local n = math.sqrt(w * w + x * x + y * y + z * z)
	return cf(self.x + (b.x - self.x) * t, self.y + (b.y - self.y) * t, self.z + (b.z - self.z) * t,
		fromQuat(w / n, x / n, y / n, z / n))
end
function CF:ToEulerAnglesYXZ()
	local r = self.r
	local x = math.asin(-math.clamp(r[6], -1, 1))
	local y = math.atan2(r[3], r[9])
	local z = math.atan2(r[4], r[5])
	return x, y, z
end
local I = { 1, 0, 0, 0, 1, 0, 0, 0, 1 }
local function rx(a) local c, s = math.cos(a), math.sin(a) return { 1, 0, 0, 0, c, -s, 0, s, c } end
local function ry(a) local c, s = math.cos(a), math.sin(a) return { c, 0, s, 0, 1, 0, -s, 0, c } end
local function rz(a) local c, s = math.cos(a), math.sin(a) return { c, -s, 0, s, c, 0, 0, 0, 1 } end
CFrame = {
	new = function(x, ...)
		local n = select("#", ...)
		if x == nil then return cf(0, 0, 0, table.clone(I)) end
		if type(x) == "table" then return cf(x.X, x.Y, x.Z, table.clone(I)) end
		if n == 2 then local y, z = ... return cf(x, y, z, table.clone(I)) end
		local y, z, r00, r01, r02, r10, r11, r12, r20, r21, r22 = ...
		return cf(x, y, z, { r00, r01, r02, r10, r11, r12, r20, r21, r22 })
	end,
	Angles = function(a, b, c) return cf(0, 0, 0, mulR(mulR(rx(a), ry(b)), rz(c))) end,
}
CFrame.identity = CFrame.new()
CFrame.fromEulerAnglesXYZ = CFrame.Angles
Mock.isCFrame = function(v) return getmetatable(v) == CF end

-- Enum -------------------------------------------------------------------------
Enum = setmetatable({}, {
	__index = function(_, enumName)
		return setmetatable({}, {
			__index = function(_, item) return { Name = item, EnumType = enumName, Value = 0 } end,
		})
	end,
})

Color3 = { fromRGB = function(r, g, b) return { R = r / 255, G = g / 255, B = b / 255 } end, new = function(r, g, b) return { R = r, G = g, B = b } end }

-- task ---------------------------------------------------------------------------
task = { spawn = function(f, ...) f(...) end, delay = function() end, wait = function() end }

-- Instance -----------------------------------------------------------------------
local PARENTS = {
	Part = "BasePart", MeshPart = "BasePart", BasePart = "PVInstance", PVInstance = "Instance",
	Model = "PVInstance", Motor6D = "JointInstance", Weld = "JointInstance", JointInstance = "Instance",
	KeyframeSequence = "AnimationClip", AnimationClip = "Instance",
}
local DEFAULTS = {
	BasePart = { CFrame = CFrame.identity, Size = Vector3.new(1, 1, 1), Transparency = 0, Anchored = false },
	JointInstance = { C0 = CFrame.identity, C1 = CFrame.identity },
	Motor6D = { Transform = CFrame.identity },
	Pose = { CFrame = CFrame.identity, Weight = 1, EasingStyle = { Name = "Linear" } },
	Keyframe = { Time = 0 },
	KeyframeSequence = { Loop = false },
	Attachment = { Position = Vector3.zero },
}

local Inst = {}
local function isA(cls, want)
	while cls do
		if cls == want then return true end
		cls = PARENTS[cls]
	end
	return want == "Instance"
end

local methods = {}
function methods:GetChildren() return table.clone(rawget(self, "_children")) end
function methods:GetDescendants()
	local out = {}
	local function rec(o)
		for _, c in ipairs(rawget(o, "_children")) do
			table.insert(out, c)
			rec(c)
		end
	end
	rec(self)
	return out
end
function methods:FindFirstChild(name, recursive)
	for _, c in ipairs(rawget(self, "_children")) do
		if c.Name == name then return c end
	end
	if recursive then
		for _, c in ipairs(rawget(self, "_children")) do
			local f = c:FindFirstChild(name, true)
			if f then return f end
		end
	end
	return nil
end
methods.WaitForChild = methods.FindFirstChild
function methods:FindFirstChildOfClass(cls)
	for _, c in ipairs(rawget(self, "_children")) do
		if c.ClassName == cls then return c end
	end
	return nil
end
function methods:IsA(cls) return isA(self.ClassName, cls) end
function methods:SetAttribute(k, v) rawget(self, "_attrs")[k] = v end
function methods:GetAttribute(k) return rawget(self, "_attrs")[k] end
function methods:IsDescendantOf(o)
	local p = self.Parent
	while p do
		if p == o then return true end
		p = p.Parent
	end
	return false
end
function methods:Destroy() self.Parent = nil end
function methods:PivotTo() end
function methods:GetFullName() return self.Name end
function methods:GetKeyframes()
	local out = {}
	for _, c in ipairs(rawget(self, "_children")) do
		if c.ClassName == "Keyframe" then table.insert(out, c) end
	end
	return out
end
function methods:Clone()
	local map = {}
	local function copy(o)
		local n = Instance.new(o.ClassName)
		map[o] = n
		for k, v in pairs(rawget(o, "_props")) do
			if k ~= "Parent" then rawget(n, "_props")[k] = v end
		end
		for k, v in pairs(rawget(o, "_attrs")) do rawget(n, "_attrs")[k] = v end
		for _, c in ipairs(rawget(o, "_children")) do
			copy(c).Parent = n
		end
		return n
	end
	local root = copy(self)
	-- remap references inside the cloned tree (Part0/Part1/PrimaryPart)
	for o, n in pairs(map) do
		for k, v in pairs(rawget(n, "_props")) do
			if type(v) == "table" and map[v] then rawget(n, "_props")[k] = map[v] end
		end
	end
	return root
end

Inst.__index = function(o, k)
	local m = methods[k]
	if m then return m end
	local props = rawget(o, "_props")
	if props[k] ~= nil then return props[k] end
	if k == "Parent" then return nil end
	local cls = rawget(o, "ClassName")
	while cls do
		local d = DEFAULTS[cls]
		if d and d[k] ~= nil then return d[k] end
		cls = PARENTS[cls]
	end
	-- child lookup like Roblox (instance.ChildName)
	for _, c in ipairs(rawget(o, "_children")) do
		if c.Name == k then return c end
	end
	return nil
end
Inst.__newindex = function(o, k, v)
	if k == "Parent" then
		local old = rawget(o, "_props").Parent
		if old then
			local ch = rawget(old, "_children")
			local i = table.find(ch, o)
			if i then table.remove(ch, i) end
		end
		rawget(o, "_props").Parent = v
		if v then table.insert(rawget(v, "_children"), o) end
		return
	end
	rawget(o, "_props")[k] = v
end
Inst.__tostring = function(o) return o.Name end

Instance = {
	new = function(cls)
		local o = setmetatable({ ClassName = cls, _props = { Name = cls }, _children = {}, _attrs = {} }, Inst)
		return o
	end,
}
Mock.Instance = Instance

-- require(ModuleScript) ----------------------------------------------------------
local cache = {}
function Mock.module(path, name, parent)
	local m = Instance.new("ModuleScript")
	m.Name = name
	rawget(m, "_props").__path = path
	if parent then m.Parent = parent end
	return m
end
require = function(m)
	if cache[m] ~= nil then return cache[m] end
	local path = rawget(m, "_props").__path
	assert(path, "mock require: not a mock module")
	local fn = __load_file(path)
	local prev = script
	script = m
	local result = fn()
	script = prev
	cache[m] = result
	return result
end

game = { GetService = function(_, n) return Instance.new(n) end }
workspace = Instance.new("Workspace")

return Mock
