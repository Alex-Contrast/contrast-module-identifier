"""MCP client for Contrast Security search_applications.

Connects to mcp-contrast via stdio (jar or Docker),
exposes a simple search function that returns AppCandidates
compatible with the resolver's SearchFn type.
"""

import json
import logging
import os
import time

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from .config import ContrastConfig
from .resolver import AppCandidate

log = logging.getLogger(__name__)


DEFAULT_JAR_PATH = os.path.expanduser(
    "~/dev/aiml/mcp-contrast/target/mcp-contrast-0.0.16-SNAPSHOT.jar"
)


def _server_params(
    config: ContrastConfig,
    jar_path: str | None = None,
) -> StdioServerParameters:
    """Build MCP stdio params for the Contrast MCP server.

    Prefers running the jar directly (faster, no Docker overhead).
    Falls back to Docker if no jar_path provided and default doesn't exist.
    """
    env = config.as_env()
    env["PATH"] = os.environ.get("PATH", "")

    jar = jar_path or DEFAULT_JAR_PATH
    if os.path.isfile(jar):
        return StdioServerParameters(
            command="java",
            args=["-jar", jar, "-t", "stdio"],
            env=env,
        )

    # Fallback: Docker
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
            app_id = app.get("appID") or app.get("app_id") or app.get("application_id") or app.get("id")
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

    def __init__(self, config: ContrastConfig, jar_path: str | None = None):
        self._config = config
        self._jar_path = jar_path
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "ContrastMCP":
        params = _server_params(self._config, self._jar_path)
        log.info("Starting MCP server: %s %s", params.command, " ".join(params.args[:3]))
        t0 = time.monotonic()

        self._stdio_cm = stdio_client(params)
        read, write = await self._stdio_cm.__aenter__()

        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()

        elapsed = time.monotonic() - t0
        log.info("MCP server ready (%.1fs)", elapsed)
        self._call_count = 0
        self._total_candidates = 0
        self._total_time = 0.0
        return self

    async def __aexit__(self, *exc):
        log.info(
            "MCP session: %d calls, %d total candidates, %.1fs total search time",
            self._call_count, self._total_candidates, self._total_time,
        )
        if self._session_cm:
            await self._session_cm.__aexit__(*exc)
        if self._stdio_cm:
            await self._stdio_cm.__aexit__(*exc)

    async def list_applications(self) -> list[AppCandidate]:
        """Fetch all applications from the Contrast org. Single call."""
        assert self._session is not None, "Not connected — use 'async with'"

        t0 = time.monotonic()
        result = await self._session.call_tool(
            "search_applications",
            {"query": ""},
        )
        elapsed = time.monotonic() - t0

        raw_bytes = sum(len(b.text) for b in result.content if b.type == "text")
        candidates = _parse_candidates(result)

        self._call_count += 1
        self._total_candidates += len(candidates)
        self._total_time += elapsed

        log.info(
            "list_applications → %d apps, %d bytes, %.2fs",
            len(candidates), raw_bytes, elapsed,
        )
        return candidates
