# dcc-mcp-epic

Local-first, typed Epic Games Launcher / Fab / Unreal project adapter for
DCC-MCP. It follows the LiquiGen adapter pattern: exact runtime binding,
versioned commands, read-before-write policy, resumable operation results, and
no generic UI automation fallback.

## Current 0.2 boundary

- Installed UE inventory: available, read-only, from Epic `.item` manifests.
- UE installation integrity checks: available, read-only, verifies the editor binary.
- UE 5.5 project verification: available, read-only.
- UE install/update: plan-only; returns `human_required` until a supported
  native Launcher bridge is verified.
- Fab search: read-only local index search. Fab download/export are available
  only through a declared user-owned hook; the adapter never automates login,
  CAPTCHA, 2FA, purchase, or license acceptance.
- Local Fab library index: available, read-only, when Epic's `listings_v1.db`
  exists.
- Multi-source Fab inventory: available, read-only, merges explicitly selected
  indexes and can discover `listings_v1.db` below caller-approved roots.
- Fab Add to My Library: available through a declared user-owned hook for
  explicitly-free listings, with bounded batch support (up to 100 IDs), exact
  optional Launcher identity, and mandatory post-action ownership evidence.
- Fab library sync: available through a scoped user-owned hook keyed to the
  Launcher PID and approved cache/index roots; the adapter never edits Epic's
  databases directly.
- Fab asset detail: read-only listing metadata plus cache evidence for one
  asset, available through a typed hook.
- Fab download status: available, read-only, re-reads ownership, path and
  cache evidence after a user-owned download hook.
- Fab batch download status: bounded (up to 100 IDs), merges multiple local
  indexes and returns per-asset evidence through a typed hook.
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
- Local Fab search: read-only full-text/category/format filters across merged
  indexes, with owned/downloaded-only selectors.
- Typed engine requests: install, update, download, verify, and launch hooks
  expose scoped payloads while preserving read-before-write plans.
- Typed Fab/project requests: export, one-asset import, batch import, and
  project import hooks enforce explicit roots, formats, and confirmation.
- Typed UE-native Fab batch Add to Project: up to 100 free, owned IDs are
  dispatched to a hook that must execute one official Add to Project action
  per asset and return per-asset evidence.
- Bounded batch download request: up to 100 free, owned asset IDs can be sent
  to one user-owned hook, with per-asset verification required afterwards.
  UE-native content is rejected for this operation because Fab Launcher uses
  Add to Project instead; use `fab-add-to-project-request` or the bounded
  `fab-add-to-project-batch-request` for UE content.
- Hook contract introspection: `hook-contract` / `epic_hook_contract` returns
  the stable `epic.hook.v1` operation list, required fields, mutation flags,
  and confirmation defaults for self-owned integrations.
- Read-only hook requests: Launcher status, Fab search/library/source/detail
  reads, single/batch download status, project import inventory, and the Fab
  callback listener probe are available as typed `*_request` MCP tools and CLI
  commands. Each
  request includes the local evidence plan and reports no mutation.
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
uv run dcc-mcp-epic-cli hook-contract
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
uv run dcc-mcp-epic-cli fab-asset-detail-request <asset-id> `
  --hook-manifest C:\path\hook.json --search-root C:\ProgramData\Epic
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
uv run dcc-mcp-epic-cli engine-download-request 5.5 `
  --hook-manifest C:\path\hook.json --install-root F:\UE\UE_5.5 `
  --allowed-root F:\UE
uv run dcc-mcp-epic-cli fab-search Arrow `
  --search-root C:\ProgramData\Epic --owned-only --downloaded-only
uv run dcc-mcp-epic-cli fab-search-request Arrow `
  --hook-manifest C:\path\hook.json --search-root C:\ProgramData\Epic
uv run dcc-mcp-epic-cli fab-library-request `
  --hook-manifest C:\path\hook.json --database C:\path\listings_v1.db
uv run dcc-mcp-epic-cli fab-add-to-library-request <asset-id> `
  --hook-manifest C:\path\hook.json --free-listing `
  --launcher-pid <EpicLauncherPID> --launcher-hwnd <EpicLauncherHWND> `
  --launcher-executable C:\Program Files\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe
uv run dcc-mcp-epic-cli fab-add-to-library-batch-request `
  <asset-id-1> <asset-id-2> --hook-manifest C:\path\hook.json `
  --free-listing --launcher-pid <EpicLauncherPID> `
  --launcher-hwnd <EpicLauncherHWND> `
  --launcher-executable C:\Program Files\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe
uv run dcc-mcp-epic-cli fab-library-sync-request `
  --launcher-pid <EpicLauncherPID> --allowed-root F:\UE `
  --hook-manifest C:\path\hook.json `
  --database F:\UE\EpicGamesLauncher\VaultCache\FabLibrary\listings_v1.db `
  --cache-root F:\UE\EpicGamesLauncher\VaultCache
uv run dcc-mcp-epic-cli fab-download-status-request <asset-id> `
  --hook-manifest C:\path\hook.json --database C:\path\listings_v1.db
uv run dcc-mcp-epic-cli fab-download-status-batch-request `
  <asset-id-1> <asset-id-2> --hook-manifest C:\path\hook.json `
  --search-root C:\ProgramData\Epic --cache-root C:\ProgramData\Epic\EpicGamesLauncher\VaultCache
uv run dcc-mcp-epic-cli fab-import-inventory-request P:\game-test\ue-arpg `
  --allowed-root P:\game-test\ue-arpg --hook-manifest C:\path\hook.json
uv run dcc-mcp-epic-cli fab-launcher-status-request `
  --launcher-pid <EpicLauncherPID> --hook-manifest C:\path\hook.json
uv run dcc-mcp-epic-cli fab-download-batch-request P:\game-test\ue-arpg `
  <asset-id-1> <asset-id-2> --allowed-root P:\game-test\ue-arpg `
  --hook-manifest C:\path\hook.json --owned
uv run dcc-mcp-epic-cli fab-add-to-project-request <asset-id> P:\game-test\ue-arpg `
  --allowed-root P:\game-test\ue-arpg --hook-manifest C:\path\hook.json --owned
uv run dcc-mcp-epic-cli fab-add-to-project-batch-request P:\game-test\ue-arpg `
  <asset-id-1> <asset-id-2> --allowed-root P:\game-test\ue-arpg `
  --hook-manifest C:\path\hook.json --owned
uv run dcc-mcp-epic-cli fab-export-request <asset-id> P:\game-test\ue-arpg\Exports `
  --allowed-root P:\game-test\ue-arpg --hook-manifest C:\path\hook.json --owned
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
