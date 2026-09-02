# Native bridge contract

The future `epic-launcher-bridge.exe` must expose only named commands over an
authenticated local named pipe. Every request includes a nonce, adapter version,
exact Launcher PID/HWND, executable path, and an idempotency key.

Initial allowlist:

- `launcher.status`
- `engine.install.request`
- `engine.update.request`
- `engine.verify.request`
- `fab.download.request`
- `fab.export.request`

The bridge must reject arbitrary command lines, URLs, PowerShell, credentials,
purchase actions, and manifest writes. Long operations return a job ID and are
verified by fresh filesystem/asset-registry evidence before completion.

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
