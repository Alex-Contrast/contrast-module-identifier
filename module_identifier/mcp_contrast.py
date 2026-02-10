"""MCP client for Contrast Security search_applications.

Connects to contrast/mcp-contrast Docker image via stdio,
exposes a simple search function that returns AppCandidates
compatible with the resolver's SearchFn type.
"""

import json
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from .config import ContrastConfig
from .resolver import AppCandidate


def _server_params(config: ContrastConfig) -> StdioServerParameters:
    """Build MCP stdio params for the Contrast Docker container."""
    env = os.environ.copy()
    env.update(config.as_env())

    return StdioServerParameters(
        command="docker",
        args=[
            "run", "-i", "--rm",
            "-e", "CONTRAST_HOST_NAME",
            "-e", "CONTRAST_API_KEY",
            "-e", "CONTRAST_SERVICE_KEY",
            "-e", "CONTRAST_USERNAME",
            "-e", "CONTRAST_ORG_ID",
            "contrast/mcp-contrast:latest",
            "-t", "stdio",
        ],
        env=env,
    )


def _parse_candidates(result) -> list[AppCandidate]:
    """Parse MCP tool result into AppCandidates."""
    candidates = []
    for block in result.content:
        if block.type != "text":
            continue
        try:
            data = json.loads(block.text)
        except (json.JSONDecodeError, TypeError):
            continue

        # Handle both list of apps and single app responses
        apps = data if isinstance(data, list) else [data]
        for app in apps:
            if not isinstance(app, dict):
                continue
            app_id = app.get("app_id") or app.get("application_id") or app.get("id")
            name = app.get("name") or app.get("application_name")
            language = app.get("language", "")
            if app_id and name:
                candidates.append(AppCandidate(
                    app_id=str(app_id),
                    name=name,
                    language=language,
                ))
    return candidates


class ContrastMCP:
    """Async context manager for the Contrast MCP connection.

    Usage:
        async with ContrastMCP(config) as mcp:
            candidates = await mcp.search_applications("order-api")
    """

    def __init__(self, config: ContrastConfig):
        self._config = config
        self._session: ClientSession | None = None
        self._cleanup_fns: list = []

    async def __aenter__(self) -> "ContrastMCP":
        params = _server_params(self._config)
        # stdio_client is an async context manager that yields (read, write)
        self._stdio_cm = stdio_client(params)
        read, write = await self._stdio_cm.__aenter__()

        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()
        return self

    async def __aexit__(self, *exc):
        if self._session_cm:
            await self._session_cm.__aexit__(*exc)
        if self._stdio_cm:
            await self._stdio_cm.__aexit__(*exc)

    async def search_applications(self, query: str) -> list[AppCandidate]:
        """Search Contrast for applications matching query."""
        assert self._session is not None, "Not connected — use 'async with'"
        result = await self._session.call_tool(
            "search_applications",
            {"query": query},
        )
        return _parse_candidates(result)

    def search_fn(self):
        """Return a SearchFn-compatible callable for the resolver.

        Usage:
            async with ContrastMCP(config) as mcp:
                matches = resolve_modules(modules, mcp.search_fn())
        """
        # resolve_modules expects a sync SearchFn today.
        # This returns an async version — we'll bridge the gap
        # when we wire up the pipeline (asyncio.run or make resolver async).
        return self.search_applications
