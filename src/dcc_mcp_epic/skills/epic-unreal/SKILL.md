---
name: epic-unreal
description: >-
  Typed Unreal Engine workflow for verifying a UE project, inspecting installed
  engine manifests, and producing a scoped launch plan. Use for UE 5.5 project
  checks and launch preparation; it never launches a process or falls back to
  generic UI automation.
license: MIT
compatibility: "Python 3.7+; dcc-mcp-core 0.17+; dcc-mcp-epic 0.2+"
allowed-tools: [Bash, Read, Write, Edit]
metadata:
  dcc-mcp:
    dcc: epic
    layer: domain
    stage: scene
    version: "0.1.0"
    tags: [epic, unreal, ue5, read-only]
    search-hint: >-
      Unreal Engine UE 5.5 project verification installed engine manifest
      launch plan RiftKidsARPG typed adapter
    search-aliases: [Epic Unreal, UE 5.5, Unreal project check]
    tools: tools.yaml
---

# Epic Unreal

Use this skill to establish authoritative local UE state before any launch or
editor operation. `verify_project` checks the `.uproject` association,
`list_installed_engines` reads Epic `.item` manifests, and `launch_plan` only
produces a read-only plan. Process launch and editor actions remain explicit
typed adapter operations with their own confirmation and readback contracts.

## Workflow

```text
verify_project → list_installed_engines → launch_plan
```

For the current prototype, use `expected_engine=5.5` and keep the project path
inside the caller-approved workspace root.
