extends SceneTree
## Headless perf probe: loads a scene, runs it for N seconds, prints one JSON line.
## Usage: godot --headless --path <project> --script <this file> -- <res://scene.tscn> [seconds] [warmup_frames]
## The first `warmup_frames` samples (default 10) are left out of frame_ms and the clock restarts
## after them, so a heavy start-up frame does not dominate a short window. The cost of the very
## first frame is reported separately as first_frame_ms. 0 = no warm-up: every sample after the
## first counts, the window starts at load.

var _scene_path := ""
var _seconds := 5.0
var _started := 0
var _frames := 0
var _work_ms := 0.0
var _load_ms := 0.0
var _stage := 0
var _warmup := 10
var _samples := 0
var _first_ms := 0.0
var _each: Array[float] = []


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		printerr("perf_smoke: scene path missing")
		quit(2)
		return
	_scene_path = args[0]
	if args.size() > 1:
		if not args[1].is_valid_float() or float(args[1]) <= 0.0:
			printerr("perf_smoke: bad seconds '%s'" % args[1])
			quit(2)
			return
		_seconds = float(args[1])
	if args.size() > 2:
		if not args[2].is_valid_int() or int(args[2]) < 0:
			printerr("perf_smoke: bad warmup_frames '%s' (integer >= 0)" % args[2])
			quit(2)
			return
		_warmup = int(args[2])
	var t0 := Time.get_ticks_usec()
	var packed: Resource = load(_scene_path)
	if not packed is PackedScene:
		printerr("perf_smoke: cannot load %s" % _scene_path)
		quit(2)
		return
	root.add_child((packed as PackedScene).instantiate())
	_load_ms = (Time.get_ticks_usec() - t0) / 1000.0
	_started = Time.get_ticks_msec()


func _process(_delta: float) -> bool:
	if _stage == 0:
		_stage = 1
		return false
	# TIME_PROCESS read here is the previous frame's cost, so sample 1 is frame 0 (the start-up spike).
	var ms := Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0
	_samples += 1
	if _samples == 1:
		_first_ms = ms
	if _samples <= _warmup:
		_started = Time.get_ticks_msec()
		return false
	_frames += 1
	_work_ms += ms
	_each.append(ms)
	if Time.get_ticks_msec() - _started < int(_seconds * 1000.0):
		return false
	_each.sort()
	var out := {
		"scene": _scene_path,
		"load_ms": snappedf(_load_ms, 0.1),
		"frame_ms": snappedf(_work_ms / maxf(_frames, 1), 0.001),
		"frame_median_ms": snappedf(_each[_each.size() / 2], 0.001),
		"first_frame_ms": snappedf(_first_ms, 0.1),
		"warmup_frames": _warmup,
		"nodes": int(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)),
		"mem_mb": snappedf(Performance.get_monitor(Performance.MEMORY_STATIC) / 1048576.0, 0.1),
		"frames": _frames,
	}
	print("PERF_SMOKE ", JSON.stringify(out))
	quit(0)
	return true
