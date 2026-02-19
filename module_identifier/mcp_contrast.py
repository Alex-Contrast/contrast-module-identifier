"""MCP client for Contrast Security search_applications.

Connects to mcp-contrast via stdio (jar or Docker),
exposes a simple search function that returns AppCandidates
compatible with the resolver's SearchFn type.
"""

import json
import logging
import os
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from .config import ContrastConfig
from .resolver import AppCandidate

log = logging.getLogger(__name__)


def _default_jar_path() -> str:
    """Read jar path from env (set by load_dotenv at runtime)."""
    raw = os.environ.get("MCP_CONTRAST_JAR_PATH", "")
    return str(Path(os.path.expanduser(raw)).resolve()) if raw else ""


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

    jar = jar_path or _default_jar_path()
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

        # Handle list, {"items": [...]}, or single app responses
        if isinstance(data, list):
            apps = data
        elif isinstance(data, dict) and isinstance(data.get("items"), list):
            apps = data["items"]
        else:
            apps = [data]
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


def _has_more_pages(result) -> bool:
    """Check if the MCP paginated response indicates more pages."""
    for block in result.content:
        if block.type != "text":
            continue
        try:
            data = json.loads(block.text)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict):
            return bool(data.get("hasMorePages", False))
    return False


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
        """Fetch all applications from the Contrast org, paginating if needed."""
        assert self._session is not None, "Not connected — use 'async with'"

        all_candidates: list[AppCandidate] = []
        page = 1
        page_size = 100  # MCP server max

        while True:
            t0 = time.monotonic()
            result = await self._session.call_tool(
                "search_applications",
                {"page": page, "pageSize": page_size},
            )
            elapsed = time.monotonic() - t0

            self._call_count += 1
            self._total_time += elapsed

            raw_bytes = sum(len(b.text) for b in result.content if b.type == "text")
            candidates = _parse_candidates(result)
            all_candidates.extend(candidates)

            has_more = _has_more_pages(result)
            log.info(
                "list_applications page %d → %d apps, %d bytes, %.2fs (hasMore=%s)",
                page, len(candidates), raw_bytes, elapsed, has_more,
            )

            if not has_more or not candidates:
                break
            page += 1

        self._total_candidates += len(all_candidates)
        return all_candidates
