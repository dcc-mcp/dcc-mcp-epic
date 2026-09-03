# Bundled Epic skills

`dcc-mcp-epic` publishes two agent-facing skill packages. They are wrappers
around the adapter's typed services, not a second UI automation layer.

## `epic-fab`

Use `$epic-fab` to inspect local `listings_v1.db` sources, search owned and
downloaded entries, preflight the exact Epic Launcher window through the
project-owned `dcc-cua`, plan or execute one bounded free-asset sync, and audit
`.dcc-mcp-fab.json` import manifests in a UE project. The sync script sends one
`epic.hook.v1` request to the configured official/native provider. With
`execute=false` (the default), the worker returns a typed `read_only` dry-run
and never invokes a provider mutation.

## `epic-unreal`

Use `$epic-unreal` to verify a `.uproject` (UE 5.5 by default), inspect Epic
`.item` engine manifests, and produce a read-only editor launch plan. The skill
does not start processes and does not use generic Computer Use.

## Validation

From a checkout with `dcc-mcp-core` available:

```powershell
python -c "from dcc_mcp_core import validate_skill; from pathlib import Path; root=Path('src/dcc_mcp_epic/skills'); [print(name, validate_skill(root/name)) for name in ('epic-fab','epic-unreal')]"
uv run pytest
uv run ruff check .
uv build
```

The package-data declaration in `pyproject.toml` keeps all skill files in
published artifacts.
