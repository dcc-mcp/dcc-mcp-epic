# Native bridge contract

The future `epic-launcher-bridge.exe` must expose only named commands over an
authenticated local named pipe. Every request includes a nonce, adapter version,
exact Launcher PID/HWND, executable path, and an idempotency key.

Initial allowlist:

- `launcher.status`
- `engine.install.request`
- `engine.update.request`
- `engine.download.request`
- `engine.verify.request`
- `engine.launch.request`
- `fab.download.request`
- `fab.download_batch.request`
- `fab.add_to_project.request`
- `fab.export.request`
- `fab.import_cached.request`
- `fab.import_all_cached.request`
- `fab.import_inventory.request`
- `fab.launcher_import.request`
- `fab.launcher_status.request`
- `project.import.request`

The adapter also implements cached import locally. This path is intentionally
separate from the native bridge: it reads Epic's local library index, requires
an acquisition row and an existing cache path, copies only Unreal Content
files, and writes a provenance manifest under the project. It never edits
`listings_v1.db` or claims that a cached asset is free; license terms remain
the user's responsibility.

UE 5.5's installed FabLauncher plugin exposes a loopback TCP import endpoint
on `127.0.0.1:23429` and sends completion status to the Launcher on
`127.0.0.1:24563`. The typed `fab-launcher-probe`/`fab-launcher-import` tools
bind the endpoint to an exact UnrealEditor PID, HWND, and executable before
sending the plugin's JSON payload. They never accept arbitrary URLs, commands,
or credentials; `fab-launcher-status-probe` separately verifies the Launcher
callback listener. Completion still requires fresh UE asset-registry evidence.

The bridge must reject arbitrary command lines, URLs, PowerShell, credentials,
purchase actions, and manifest writes. Long operations return a job ID and are
verified by fresh filesystem/asset-registry evidence before completion.

`epic_fab_download_request` is the typed hook entry for a user-owned download
bridge. It rejects non-zero prices and unverified ownership, sends only the
asset/project/format/quality payload, defaults to dry-run, and reports the
request as incomplete until the local Fab index and project inventory are
re-read.

`epic_fab_download_batch_request` applies the same free/owned policy to a
bounded list (maximum 100 IDs) and sends one deterministic batch payload. The
hook must report its own job/result; callers must re-read every asset's
`epic_fab_download_status` and the project import inventory before treating the
batch as complete.

UE-native Fab content is not batch-downloadable in Launcher. The typed
`epic_fab_add_to_project_request` operation is the official native-content path;
it sends one asset ID and a scoped `.uproject`/project directory to a declared
hook. The hook must report completion, after which callers re-read Fab status and
the Unreal project inventory. Exchange formats such as FBX, GLTF/GLB, OBJ, and
USD remain available through the batch/export operations.

`epic_hook_contract` (or `hook-contract` in the CLI) is the source of truth for
operation names, required identity fields, mutation flags, and confirmation
defaults. Hook authors should consume that contract instead of depending on
private Epic Launcher/Fab implementation details.

## Self-owned hook bridge

For capabilities not exposed by the Launcher, a user-owned bridge can register
an `epic.hook.v1` manifest. The manifest declares an absolute command, SHA-256,
operation allowlist, and confirmation-required operations. The adapter invokes
the command with a fixed argv and a JSON request on stdin; `shell=False` is
always used. Dry-run is the default, and a hook cannot widen the adapter's
project-root or free-asset policy.

Example shape:

```json
{
  "protocol": "epic.hook.v1",
  "name": "studio-epic-bridge",
  "version": "1.0.0",
  "command": ["C:/Studio/epic-bridge.exe"],
  "operations": ["engine.update.request", "fab.download.request"],
  "requires_confirmation": ["engine.update.request", "fab.download.request"],
  "sha256": "<64-hex-digest>"
}
```
