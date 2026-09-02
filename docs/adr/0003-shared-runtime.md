# ADR 0003: Use one shared sidecar/runtime for external adapters

## Decision

Adapters such as Epic, Fab, LiquiGen, and Unity run as external Python wheels
under one DCC-MCP runtime. When Python is already available, reuse the verified
`dcc-mcp-server` sidecar/gateway and its compatible Python environment. When no
Python installation is available, distribute one PyOxidizer-built
`dcc-mcp-runtime` bundle with adapters loaded from an adjacent `lib/adapters`
directory.

The Unreal Editor's embedded Python is never used as the adapter runtime.

## Rationale

UE embedded Python is tied to the exact Editor build and enabled plugins. A
per-adapter frozen interpreter duplicates security patches and increases release
coupling. A shared sidecar keeps the host boundary external and lets adapters
release independently.

## Consequence

The runtime repository owns `pyoxidizer.bzl`, interpreter updates, signing, and
the runtime ABI contract. Adapter repositories own typed provider logic and
wheel compatibility metadata. A runtime doctor reports whether the current
machine can reuse `dcc-mcp-server` or needs the bundled runtime.
