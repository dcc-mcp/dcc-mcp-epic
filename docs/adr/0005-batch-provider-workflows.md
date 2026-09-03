# ADR 0005: Prefer batch provider workflows over per-control CUA

## Decision

Expose free Fab discovery and free-asset synchronization as versioned
`epic.hook.v1` operations. `fab.catalog_free.request` is read-only;
`fab.free_assets_sync.request` accepts up to 100 explicitly-free listings and
dispatches one confirmation-gated provider job for library ownership,
download, verification, and optional project import.

The payload advertises `cua_calls_expected: 0`. The existing
`launcher.action.request` surface remains the bounded dcc-cua fallback for
custom-rendered controls that have no supported native/provider path.

## Rationale

Per-item CUA actions are slow and fragile for a workflow whose business state
is account ownership, local cache state, and Unreal project inventory. A
provider-owned batch job can use an official API or native bridge, preserve
idempotency and per-asset evidence, and keep credentials/login outside this
adapter. The JSON hook protocol is language-neutral; a C++/C# reflection shim
is not required merely to expose the contract.

## Consequences

- Hooks must re-check current price and return per-asset ownership/download
  evidence before callers treat the job as complete.
- The adapter still enforces confirmation, a maximum of 100 assets, supported
  formats, exact optional Launcher identity, and allowed-root confinement.
- Native UE editor code remains an optional provider implementation detail, not
  a dependency of the public MCP contract.
