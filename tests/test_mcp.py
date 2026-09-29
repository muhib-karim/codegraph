"""Protocol tests use the official client session; no network or model calls."""

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")
import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session

from codegraph.indexer import index
from codegraph.mcp_server import create_server

MINI = Path(__file__).parent / "fixtures" / "mini"


@pytest.fixture
def mcp_db(tmp_path):
    db = tmp_path / "graph.lbug"
    index(str(MINI), str(db))
    return db


def test_all_tools_through_sdk(mcp_db):
    before = hashlib.sha256(mcp_db.read_bytes()).hexdigest()

    async def exercise():
        async with create_connected_server_and_client_session(
            create_server(str(mcp_db))
        ) as session:
            tools = await session.list_tools()
            cases = {
                "find_symbol": {"symbol": "Circle"},
                "callers": {"symbol": "make"},
                "callees": {"symbol": "main"},
                "inherits": {"symbol": "Shape"},
                "dead_code": {"confidence": "likely"},
                "blast_radius": {"target": "SCALE"},
                "index_status": {},
            }
            assert {t.name for t in tools.tools} == set(cases)
            for tool in tools.tools:
                assert tool.annotations.readOnlyHint
                assert not tool.annotations.destructiveHint
                response = await session.call_tool(tool.name, cases[tool.name])
                assert not response.isError, response
                result = response.structuredContent
                assert result["results"]
                for row in result["results"]:
                    assert row["citation"] == f"{row['file']}:{row['line']}"
                    assert row["confidence"] in ("exact", "heuristic", "not_applicable")
            first = await session.call_tool("callers", {"symbol": "make", "limit": 1})
            assert first.structuredContent["next_offset"] == 1
            second = await session.call_tool("callers", {"symbol": "make", "offset": 1})
            assert second.structuredContent["results"][0]["line"] == 10
            for name, args, reason in [
                ("find_symbol", {"symbol": "/etc/passwd::root"}, "indexed repository"),
                ("callers", {"symbol": "make", "in_file": "../outside.py"}, "indexed repository"),
                ("dead_code", {"scope": "C:\\outside"}, "indexed repository"),
                ("blast_radius", {"target": "../../outside.py"}, "indexed repository"),
                ("callees", {"symbol": "main", "scope": "not-indexed"}, "indexed repository"),
                ("inherits", {"symbol": "Shape", "depth": 1000}, "depth must be"),
                ("index_status", {"limit": 10000}, "limit must be"),
                ("find_symbol", {"symbol": "not-a-symbol"}, "not-a-symbol"),
            ]:
                response = await session.call_tool(name, args)
                assert response.isError, (name, args, response)
                # The refusal must come from the named check, not an unrelated failure.
                assert reason in response.content[0].text, (name, response.content)

    anyio.run(exercise)
    assert hashlib.sha256(mcp_db.read_bytes()).hexdigest() == before


def test_stdio_config_roundtrip(tmp_path):
    # The exact README JSON is parsed, with only its two documented absolute paths substituted.
    readme = Path("README.md").read_text()
    config = json.loads(readme.split("```json\n", 1)[1].split("```", 1)[0])["mcpServers"][
        "codegraph"
    ]
    repo = tmp_path / "repo"
    import shutil

    shutil.copytree(MINI, repo)
    index(str(repo), str(repo / ".codegraph" / "graph.lbug"))
    command = config["command"].replace(
        "/absolute/path/to/codegraph/.venv/bin/codegraph",
        str(Path(sys.executable).parent / "codegraph"),
    )
    args = [a.replace("/absolute/path/to/repo", str(repo)) for a in config["args"]]

    async def exercise():
        params = StdioServerParameters(command=command, args=args, env=dict(os.environ))
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                answer = await session.call_tool("callers", {"symbol": "make"})
                assert not answer.isError
                assert [r["citation"] for r in answer.structuredContent["results"]] == [
                    "app.py:6",
                    "app.py:10",
                ]

    anyio.run(exercise)
