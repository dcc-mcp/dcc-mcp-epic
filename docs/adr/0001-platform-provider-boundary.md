# ADR 0001: Keep Epic platform contracts separate from Launcher providers

## Decision

The public adapter is `dcc-mcp-epic`. Epic Games Launcher is an implementation
provider under `providers/epic_launcher`; Fab and Unreal project integration are
separate providers.

## Rationale

Engine inventory, Fab ownership, and UE project validation should not depend on
window automation or on one version of the Launcher. This keeps the MCP contract
stable if Epic exposes a supported API or Fab Integration later.

## Consequence

The first release is Windows-first and read-only for Launcher manifests. Mutating
operations require a signed, fixed-command bridge and explicit user confirmation.
