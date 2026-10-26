--!nonstrict
--[[
	KnifeAnimator
	Plays KeyframeSequences directly on a rig's Motor6D.Transform - no
	publishing / animation ids needed (works in Studio and live games).

	local anim = KnifeAnimator.new(viewmodelModel)
	anim:Load(keyframeSequence)              -- or anim:LoadFolder(folder)
	local track = anim:Play("Butterfly_Draw", { FadeTime = 0, Speed = 1 })
	anim.MarkerReached:Connect(function(clipName, markerName, value) end)
	anim.Ended:Connect(function(clipName) end)
	RunService.RenderStepped:Connect(function(dt) anim:Update(dt) end)

	Layering: every Play() puts a track on top of the previous ones. A looped
	clip (e.g. the idle) stays underneath; actions fade in on top of it and
	fade out when they end. Joint result = base pose lerped towards each
	track in play order by the track's weight.
]]

local KnifeAnimator = {}
KnifeAnimator.__index = KnifeAnimator

-- tiny signal ---------------------------------------------------------------
local Signal = {}
Signal.__index = Signal

function Signal.new()
	return setmetatable({ _handlers = {} }, Signal)
end

function Signal:Connect(fn)
	local handlers = self._handlers
	table.insert(handlers, fn)
	return {
		Disconnect = function()
			local i = table.find(handlers, fn)
			if i then
				table.remove(handlers, i)
			end
		end,
	}
end

function Signal:Fire(...)
	for _, fn in ipairs(table.clone(self._handlers)) do
		task.spawn(fn, ...)
	end
end

KnifeAnimator.Signal = Signal

-- clip compilation ------------------------------------------------------------
export type Clip = {
	Name: string,
	Length: number,
	Looped: boolean,
	Joints: { [string]: { Times: { number }, CFrames: { CFrame }, Styles: { string } } },
	Markers: { { Time: number, Name: string, Value: string } },
}

local function compile(kfs: Instance): Clip
	local keyframes = {}
	for _, kf in ipairs(kfs:GetChildren()) do
		if kf:IsA("Keyframe") then
			table.insert(keyframes, kf)
		end
	end
	table.sort(keyframes, function(a, b)
		return (a :: Keyframe).Time < (b :: Keyframe).Time
	end)

	local joints = {}
	local markers = {}
	local function walk(pose: Instance, time: number)
		for _, sub in ipairs(pose:GetChildren()) do
			if sub:IsA("Pose") then
				if sub.Weight > 0 then
					local j = joints[sub.Name]
					if not j then
						j = { Times = {}, CFrames = {}, Styles = {} }
						joints[sub.Name] = j
					end
					table.insert(j.Times, time)
					table.insert(j.CFrames, sub.CFrame)
					table.insert(j.Styles, sub.EasingStyle.Name)
				end
				walk(sub, time)
			end
		end
	end
	local length = 0
	for _, kf in ipairs(keyframes) do
		local k = kf :: Keyframe
		length = math.max(length, k.Time)
		for _, child in ipairs(k:GetChildren()) do
			if child:IsA("Pose") then
				walk(child, k.Time) -- top level pose = HumanoidRootPart (not a joint)
			elseif child:IsA("KeyframeMarker") then
				table.insert(markers, { Time = k.Time, Name = child.Name, Value = child.Value })
			end
		end
	end
	table.sort(markers, function(a, b)
		return a.Time < b.Time
	end)
	return {
		Name = kfs.Name,
		Length = length,
		Looped = (kfs :: KeyframeSequence).Loop,
		Joints = joints,
		Markers = markers,
	}
end
KnifeAnimator.Compile = compile

local function sample(j, t: number): CFrame
	local times = j.Times
	local n = #times
	if n == 1 or t <= times[1] then
		return j.CFrames[1]
	end
	if t >= times[n] then
		return j.CFrames[n]
	end
	-- binary search: last index with times[i] <= t
	local lo, hi = 1, n
	while hi - lo > 1 do
		local mid = (lo + hi) // 2
		if times[mid] <= t then
			lo = mid
		else
			hi = mid
		end
	end
	local style = j.Styles[lo]
	if style == "Constant" then
		return j.CFrames[lo]
	end
	local a = (t - times[lo]) / (times[hi] - times[lo])
	if style == "Cubic" or style == "CubicV2" then
		a = a * a * (3 - 2 * a)
	end
	return j.CFrames[lo]:Lerp(j.CFrames[hi], a)
end
KnifeAnimator.Sample = sample

-- animator ------------------------------------------------------------------
export type Track = {
	Clip: Clip,
	Time: number,
	Speed: number,
	Weight: number,
	TargetWeight: number,
	FadeSpeed: number,
	Looped: boolean,
	Stopping: boolean,
	Finished: boolean,
}

function KnifeAnimator.new(model: Instance)
	local self = setmetatable({}, KnifeAnimator)
	self.Model = model
	self.Clips = {} :: { [string]: Clip }
	self.Tracks = {} :: { Track }
	self.Motors = {} :: { [string]: Motor6D }
	self.MarkerReached = Signal.new()
	self.Ended = Signal.new()
	self:RefreshMotors()
	return self
end

function KnifeAnimator:RefreshMotors()
	table.clear(self.Motors)
	for _, d in ipairs(self.Model:GetDescendants()) do
		if d:IsA("Motor6D") and d.Part1 then
			self.Motors[d.Part1.Name] = d
		end
	end
end

function KnifeAnimator:Load(kfs: Instance): Clip
	local clip = compile(kfs)
	self.Clips[clip.Name] = clip
	return clip
end

function KnifeAnimator:LoadFolder(folder: Instance)
	for _, d in ipairs(folder:GetDescendants()) do
		if d:IsA("KeyframeSequence") then
			self:Load(d)
		end
	end
end

function KnifeAnimator:IsPlaying(name: string): boolean
	for _, tr in ipairs(self.Tracks) do
		if tr.Clip.Name == name and not tr.Stopping then
			return true
		end
	end
	return false
end

-- opts: FadeTime (s, default 0.1), Speed (default 1), Looped (default clip.Looped), Weight (default 1)
function KnifeAnimator:Play(name: string, opts: { FadeTime: number?, Speed: number?, Looped: boolean?, Weight: number? }?): Track
	local clip = self.Clips[name]
	assert(clip, "KnifeAnimator: clip not loaded: " .. tostring(name))
	local o = opts or {}
	local fade = o.FadeTime or 0.1
	local tr: Track = {
		Clip = clip,
		Time = 0,
		Speed = o.Speed or 1,
		Weight = if fade <= 0 then (o.Weight or 1) else 0,
		TargetWeight = o.Weight or 1,
		FadeSpeed = if fade <= 0 then math.huge else 1 / fade,
		Looped = if o.Looped ~= nil then o.Looped else clip.Looped,
		Stopping = false,
		Finished = false,
	}
	-- the same clip restarts instead of stacking
	for _, other in ipairs(self.Tracks) do
		if other.Clip.Name == name then
			other.Stopping = true
			other.TargetWeight = 0
			other.FadeSpeed = math.huge
		end
	end
	table.insert(self.Tracks, tr)
	return tr
end

function KnifeAnimator:Stop(name: string?, fadeTime: number?)
	local fade = fadeTime or 0.1
	for _, tr in ipairs(self.Tracks) do
		if name == nil or tr.Clip.Name == name then
			tr.Stopping = true
			tr.TargetWeight = 0
			tr.FadeSpeed = if fade <= 0 then math.huge else 1 / fade
		end
	end
end

function KnifeAnimator:StopAllExcept(keep: { [string]: boolean }, fadeTime: number?)
	for _, tr in ipairs(self.Tracks) do
		if not keep[tr.Clip.Name] then
			tr.Stopping = true
			tr.TargetWeight = 0
			tr.FadeSpeed = if (fadeTime or 0.1) <= 0 then math.huge else 1 / (fadeTime or 0.1)
		end
	end
end

local function fireMarkers(self, tr: Track, t0: number, t1: number)
	for _, m in ipairs(tr.Clip.Markers) do
		if m.Time > t0 and m.Time <= t1 then
			self.MarkerReached:Fire(tr.Clip.Name, m.Name, m.Value)
		end
	end
end

function KnifeAnimator:Update(dt: number)
	-- advance
	for _, tr in ipairs(self.Tracks) do
		local len = tr.Clip.Length
		if not tr.Finished then
			local t0 = tr.Time
			local t1 = t0 + dt * tr.Speed
			if tr.Looped and len > 0 then
				if t1 >= len then
					fireMarkers(self, tr, t0, len)
					t1 = t1 % len
					fireMarkers(self, tr, -1, t1)
				else
					fireMarkers(self, tr, t0, t1)
				end
			else
				if t0 == 0 then
					fireMarkers(self, tr, -1, 0)
				end
				if t1 >= len then
					fireMarkers(self, tr, t0, len)
					t1 = len
					tr.Finished = true
					if not tr.Stopping then
						tr.Stopping = true
						tr.TargetWeight = 0
						tr.FadeSpeed = 1 / 0.12
					end
					self.Ended:Fire(tr.Clip.Name)
				else
					fireMarkers(self, tr, t0, t1)
				end
			end
			tr.Time = t1
		end
		-- weight fade
		if tr.Weight ~= tr.TargetWeight then
			local step = dt * tr.FadeSpeed
			if tr.Weight < tr.TargetWeight then
				tr.Weight = math.min(tr.TargetWeight, tr.Weight + step)
			else
				tr.Weight = math.max(tr.TargetWeight, tr.Weight - step)
			end
		end
	end
	-- drop dead tracks
	for i = #self.Tracks, 1, -1 do
		local tr = self.Tracks[i]
		if tr.Stopping and tr.Weight <= 0 then
			table.remove(self.Tracks, i)
		end
	end
	-- apply
	for jointName, motor in pairs(self.Motors) do
		local result = CFrame.identity
		local any = false
		for _, tr in ipairs(self.Tracks) do
			local j = tr.Clip.Joints[jointName]
			if j and tr.Weight > 0 then
				local cf = sample(j, tr.Time)
				if not any then
					result = if tr.Weight >= 1 then cf else CFrame.identity:Lerp(cf, tr.Weight)
					any = true
				elseif tr.Weight >= 1 then
					result = cf
				else
					result = result:Lerp(cf, tr.Weight)
				end
			end
		end
		motor.Transform = result
	end
end

function KnifeAnimator:Destroy()
	table.clear(self.Tracks)
	table.clear(self.Motors)
end

return KnifeAnimator
