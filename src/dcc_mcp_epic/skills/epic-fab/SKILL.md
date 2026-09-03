---
name: epic-fab
description: >-
  Typed Epic Fab workflow for local library discovery, free-asset ownership and
  download synchronization, project import inventory, and dcc-cua readiness.
  Use when an agent needs Fab assets for the UE project. Do not use it to bypass
  Epic login, CAPTCHA, 2FA, purchase, or license confirmation; use the official
  provider boundary and dcc-cua only as a bounded fallback.
license: MIT
compatibility: "Python 3.7+; dcc-mcp-core 0.17+; dcc-mcp-epic 0.2+"
allowed-tools: [Bash, Read, Write, Edit]
metadata:
  dcc-mcp:
    dcc: epic
    layer: domain
    stage: source
    version: "0.1.0"
    depends: ["dcc-cua"]
    tags: [epic, fab, asset-import, read-only, destructive]
    search-hint: >-
      Epic Games Launcher Fab free assets My Library download owned cache
      Unreal Engine project import dcc-cua preflight exact PID HWND
    search-aliases: [Epic Fab, Fab library, free Fab assets, Unreal assets]
    tools: tools.yaml
---

# Epic Fab

Use this skill for the typed Epic/Fab workflow. Start with `preflight_launcher`
when any UI fallback might be needed, then prefer local readback and the single
`free_assets_sync` provider job. The skill never edits Epic SQLite indexes and
never automates authentication, CAPTCHA, 2FA, purchase, or license acceptance.

`free_assets_sync` is confirmation-sensitive and may delegate account/download
work only to the explicitly configured official/native provider. A result is
not complete unless its `state` is `available` and the returned local evidence
has been re-read. When the provider is absent or dcc-cua is blocked, preserve
the typed state and follow `next_action`; do not retry another UI provider.

## Workflow

```text
preflight_launcher → library_sources/search_library
→ free_assets_sync (one bounded batch) → project_inventory
```

UE-native content should use `mode=library_download_and_project`; exchange
formats can use `library_and_download` followed by a typed import/export tool.
