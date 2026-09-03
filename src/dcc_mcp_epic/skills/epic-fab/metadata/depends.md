# Epic Fab skill dependencies

`epic-fab` depends on the core `dcc-cua` skill for the exact-window preflight
contract. The preflight is read-only and is only used to determine whether a
human-controlled visual fallback is available; this skill never instantiates
generic Computer Use or sends UI input itself.
