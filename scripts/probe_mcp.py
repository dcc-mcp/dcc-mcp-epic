"""Smoke-test the real MCP stdio surface against the local checkout."""

from __future__ import annotations

import asyncio
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    server = StdioServerParameters(
        command="uv",
        args=["run", "dcc-mcp-epic"],
        cwd=root,
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(tool.name for tool in tools.tools)
            print({"tool_count": len(names), "tools": names})
            result = await session.call_tool("epic_engine_list_installed", {})
            print({"engine_inventory_result": result.content[0].text[:500]})


if __name__ == "__main__":
    asyncio.run(main())
