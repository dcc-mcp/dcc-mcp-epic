# dcc-mcp-epic

Local-first, typed Epic Games Launcher / Fab / Unreal project adapter for
DCC-MCP. It follows the LiquiGen adapter pattern: exact runtime binding,
versioned commands, read-before-write policy, resumable operation results, and
no generic UI automation fallback.

## Current 0.1 boundary

- Installed UE inventory: available, read-only, from Epic `.item` manifests.
- UE installation integrity checks: available, read-only, verifies the editor binary.
- UE 5.5 project verification: available, read-only.
- UE install/update: plan-only; returns `human_required` until a supported
  native Launcher bridge is verified.
- Fab search/download/export: capability probe and policy planning only. The
  adapter never automates login, CAPTCHA, 2FA, purchase, or license acceptance.
- Local Fab library index: available, read-only, when Epic's `listings_v1.db`
  exists.
- Multi-source Fab inventory: available, read-only, merges explicitly selected
  indexes and can discover `listings_v1.db` below caller-approved roots.
- Fab download status: available, read-only, re-reads ownership, path and
  cache evidence after a user-owned download hook.
- Cached Fab import: available for already-owned/downloaded Unreal Content;
  dry-run, explicit confirmation, VaultCache-root enforcement, no-overwrite
  behavior, and per-file provenance hashes are built in. FBX/GLTF/OBJ/USD
  source downloads with textures are also preserved for Unreal's importer.
- Generic CUA fallback: disabled.
- Self-owned hook bridge: supported through the fixed `epic.hook.v1` manifest
  contract, with dry-run and explicit confirmation as defaults.
- Typed Fab download request: policy-checks a free, owned asset and dispatches
  a fixed payload to a declared user-owned hook; completion still needs fresh
  library/project evidence.
- Runtime selection: `runtime-doctor` prefers a verified DCC-MCP sidecar when a
  compatible Python/MCP environment exists and otherwise selects the shared
  PyOxidizer bundle. Unreal's embedded Python is never reused.

## Local build and tests

```powershell
uv sync --extra dev
uv run pytest
uv run ruff check .
uv build
```

## Test the new interface against this machine

```powershell
uv run dcc-mcp-epic-cli capabilities
uv run dcc-mcp-epic-cli runtime-doctor
uv run dcc-mcp-epic-cli engines
uv run dcc-mcp-epic-cli project-verify P:\game-test\ue-arpg\RiftKidsARPG.uproject
uv run dcc-mcp-epic-cli engine-verify
uv run dcc-mcp-epic-cli fab-library
uv run dcc-mcp-epic-cli fab-library-sources `
  --search-root C:\ProgramData\Epic `
  --search-root C:\Users\hallong\Downloads\Video `
  --search-root F:\UE\EpicGamesLauncher
uv run dcc-mcp-epic-cli fab-download-status <asset-id> `
  --database F:\UE\EpicGamesLauncher\VaultCache\FabLibrary\listings_v1.db `
  --cache-root F:\UE\EpicGamesLauncher\VaultCache
uv run dcc-mcp-epic-cli fab-asset-inspect b8ff3ab4-0e81-4335-bbf0-fea15f6fcdfc
uv run dcc-mcp-epic-cli fab-download-request <asset-id> P:\game-test\ue-arpg `
  --allowed-root P:\game-test\ue-arpg --hook-manifest C:\path\hook.json `
  --owned
uv run dcc-mcp-epic-cli fab-import-all-cached P:\game-test\ue-arpg `
  --allowed-root P:\game-test\ue-arpg `
  --database C:\ProgramData\Epic\EpicGamesLauncher\VaultCache\FabLibrary\listings_v1.db `
  --database F:\UE\EpicGamesLauncher\VaultCache\FabLibrary\listings_v1.db `
  --cache-root C:\ProgramData\Epic\EpicGamesLauncher\VaultCache `
  --cache-root F:\UE\EpicGamesLauncher\VaultCache
uv run dcc-mcp-epic-cli fab-project-inventory P:\game-test\ue-arpg `
  --allowed-root P:\game-test\ue-arpg
uv run dcc-mcp-epic-cli fab-launcher-probe --editor-pid <UnrealEditorPID>
uv run dcc-mcp-epic-cli fab-launcher-status-probe --launcher-pid <EpicLauncherPID>
uv run dcc-mcp-epic-cli engine-update-plan 5.5
uv run python scripts/probe_mcp.py
```

Start the MCP stdio server with:

```powershell
uv run dcc-mcp-epic
```

When the shared DCC-MCP server is installed, expose the same adapter through
its HTTP/gateway bridge without installing another gateway process:

```powershell
dcc-mcp-server translate --stdio "uv run dcc-mcp-epic" --app-type epic `
  --host 127.0.0.1 --port 0 --gateway-port 0 --no-register
```

The adapter is not affiliated with or endorsed by Epic Games. Epic Launcher,
Fab, UE, and associated content remain subject to their own terms and licenses.
