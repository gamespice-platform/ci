extends SceneTree
## The addon API levels an addons.lock pins, for package.sh --host-lock: one `pin<TAB>NAME=LEVEL` line each on stdout.
## Usage: godot --headless --path <project> --script <this file> -- <addons.lock> <repos root>...
## The reading is the project's own GameSpice Core (DotAddonApi.pinned_levels); a root fills only the addons the
## earlier roots could not read, as GameSpice Server Deploy's tools/pack.gd does. An addon no root reads is left out.


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty() or not FileAccess.file_exists(args[0]):
		printerr("lock_pins: no such lock: %s" % (args[0] if not args.is_empty() else "(none given)"))
		quit(2)
		return
	var levels := {}
	for i in range(1, args.size()):
		var root: String = args[i]
		if root.is_empty() or not DirAccess.dir_exists_absolute(root):
			continue
		var found: Dictionary = DotAddonApi.pinned_levels(args[0], root)
		for addon in found:
			if not levels.has(addon):
				levels[addon] = int(found[addon])
	var names: Array = levels.keys()
	names.sort()
	for addon in names:
		print("pin\t%s=%d" % [addon, int(levels[addon])])
	quit(0)
