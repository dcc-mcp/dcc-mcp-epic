# ADR 0004: Publish Epic integration as a separate repository

## Decision

Keep Epic Games Launcher, Fab, and Unreal provider code in the dedicated
`dcc-mcp-epic` repository. Keep `dcc-mcp-core` provider-neutral: it owns MCP
transport, gateway/sidecar lifecycle, path and policy primitives, and generic
adapter catalog contracts.

If a frozen, no-Python distribution becomes necessary, publish the shared
PyOxidizer bundle as a separate `dcc-mcp-runtime` project. It must not become an
Epic-specific artifact in `dcc-mcp-core`.

## Rationale

Epic and UE releases, Windows integration, Fab licensing, and native bridge
security have a different release cadence and test matrix from the core. A
separate repository limits dependency and licensing blast radius while allowing
independent adapter releases. Core can later receive a small catalog/entry-point
registration change without taking on provider implementation ownership.

## Consequence

The adapter depends on stable public core contracts when needed, but the initial
read-only MVP remains runnable as a standalone MCP stdio service. CI and release
artifacts are owned by `dcc-mcp-epic`; cross-repository integration is validated
through explicit compatibility tests.
