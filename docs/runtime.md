# Runtime deployment

## Selection order

1. Use an explicitly configured shared `dcc-mcp-runtime` bundle when present.
2. Otherwise reuse the installed DCC-MCP sidecar/gateway and a compatible
   Python environment.
3. If neither exists, install the signed PyOxidizer runtime bundle.

`dcc-mcp-epic-cli runtime-doctor` reports the selected recommendation. The
report is read-only and does not launch processes or change PATH.

The installed Rust `dcc-mcp-server translate` command can bridge this adapter's
stdio MCP server to Streamable HTTP. This reuses the DCC-MCP gateway boundary;
it does not mean that the Rust binary embeds or replaces Python dependencies.

## Why not Unreal's Python?

The Unreal Editor Python runtime is embedded, version-specific, and affected by
the project's enabled plugins. It is appropriate for UE project scripts but is
not a stable process boundary for Epic Launcher/Fab automation. The adapter
therefore remains an external process and talks to UE through typed project or
plugin bridges.

## Packaging boundary

The future `dcc-mcp-runtime` repository owns the single `pyoxidizer.bzl` and
ships the interpreter, core gateway, signatures, and base dependencies. Adapter
repositories publish normal wheels loaded from `lib/adapters`. This avoids
shipping a complete Python interpreter in every DCC adapter while preserving
independent adapter updates.
