# ADR 0002: Treat Epic manifests as evidence, not a write API

## Decision

The adapter reads `.item` files under Epic's manifest directory to inventory
installed UE versions. It never edits, deletes, moves, or fabricates manifest
entries.

## Rationale

Manifest formats are Launcher-owned implementation details. Direct mutation can
desynchronize installation state and bypass account/licensing checks.

## Consequence

Install and update requests return a plan or an explicit unavailable/human
required result until a supported native bridge is verified.
