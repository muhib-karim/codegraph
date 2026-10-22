"""Optional official MCP SDK server. Only stdio is exposed by the CLI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .service import GraphService


def create_server(db_path: str) -> FastMCP:
    graph = GraphService(db_path)

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[None]:
        try:
            yield None
        finally:
            graph.close()

    server = FastMCP(
        "codegraph",
        lifespan=lifespan,
        instructions="Read-only indexed Python/Java/TypeScript/JavaScript snapshot. "
        "Inspect index_status first; use search to find symbol names. "
        "Citations are repo-relative; exact describes static binding, not runtime proof.",
    )
    annotations = ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    )

    @server.tool(annotations=annotations)
    def find_symbol(
        symbol: str, in_file: str = "", scope: str = "", limit: int = 100, offset: int = 0
    ) -> dict[str, Any]:
        """Find definitions by bare/qualified name or full symbol id; return all matches."""
        return graph.query("find", symbol, in_file=in_file, scope=scope, limit=limit, offset=offset)

    @server.tool(annotations=annotations)
    def callers(
        symbol: str,
        in_file: str = "",
        scope: str = "",
        depth: int = 1,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Incoming calls AND value references, with use-site citations. Depth 1..10."""
        return graph.query(
            "callers", symbol, in_file=in_file, scope=scope, depth=depth, limit=limit, offset=offset
        )

    @server.tool(annotations=annotations)
    def callees(
        symbol: str, in_file: str = "", scope: str = "", limit: int = 100, offset: int = 0
    ) -> dict[str, Any]:
        """Direct outgoing calls, with call-site citations and target definitions."""
        return graph.query(
            "callees", symbol, in_file=in_file, scope=scope, limit=limit, offset=offset
        )

    @server.tool(annotations=annotations)
    def inherits(
        symbol: str,
        in_file: str = "",
        scope: str = "",
        ancestors: bool = False,
        depth: int = 3,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Descendants or ancestors, citing the declaring class. Depth 1..10 (default 3)."""
        return graph.query(
            "inherits",
            symbol,
            in_file=in_file,
            scope=scope,
            ancestors=ancestors,
            depth=depth,
            limit=limit,
            offset=offset,
        )

    @server.tool(annotations=annotations)
    def dead_code(
        scope: str = "",
        kinds: list[str] | None = None,
        confidence: str = "all",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Candidates without incoming edges: confidence all/likely/possible; not safe-delete proof."""
        return graph.query(
            "dead-code", scope=scope, kinds=kinds, confidence=confidence, limit=limit, offset=offset
        )

    @server.tool(annotations=annotations)
    def blast_radius(
        target: str,
        in_file: str = "",
        scope: str = "",
        depth: int = 3,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Reverse calls, references and inheritance for a symbol or indexed file; depth 1..10."""
        return graph.query(
            "blast", target, in_file=in_file, scope=scope, depth=depth, limit=limit, offset=offset
        )

    @server.tool(annotations=annotations)
    def impact(
        target: str,
        in_file: str = "",
        scope: str = "",
        depth: int = 3,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """What a change to a symbol or indexed file can affect: reverse calls, references
        and inheritance, with depth 1..10 (default 3). Same answer as blast_radius."""
        return graph.query(
            "impact", target, in_file=in_file, scope=scope, depth=depth, limit=limit, offset=offset
        )

    @server.tool(annotations=annotations)
    def search(
        query: str,
        kinds: list[str] | None = None,
        scope: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Case-insensitive substring search over symbol names (qualified names if the query
        has a dot); exact, then prefix, then substring matches, each citing the definition."""
        return graph.query("search", query, kinds=kinds, scope=scope, limit=limit, offset=offset)

    @server.tool(annotations=annotations)
    def index_status(limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """Coverage and content staleness, citing file starts; file confidence is not_applicable."""
        return graph.status(limit, offset)

    return server


def serve(db_path: str) -> None:
    create_server(db_path).run(transport="stdio")
