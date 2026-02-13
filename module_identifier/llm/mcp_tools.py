"""MCP toolset setup for the LLM fallback agent.

Provides two MCP servers:
  - Filesystem: read-only access to the repository being scanned
  - Contrast: search_applications only

Tool filtering reduces token usage by ~70% (see app-identifier research).
"""

import os
from typing import List

from ..config import ContrastConfig
from ..mcp_contrast import _default_jar_path


# Filtered tool sets — only tools the agent actually needs.
# Double underscore: pydantic-ai joins tool_prefix ("fs_") + "_" + tool name → "fs__search_files".
FILESYSTEM_TOOLS = frozenset({
    "fs__search_files",
    "fs__read_text_file",
    "fs__read_multiple_files",
    "fs__list_directory",
})

CONTRAST_TOOLS = frozenset({
    "contrast__search_applications",
})


async def create_mcp_toolsets(
    contrast_config: ContrastConfig,
    repo_path: str,
    jar_path: str | None = None,
) -> List:
    """Create filtered MCP server instances for the agent.

    Args:
        contrast_config: Contrast credentials for the Contrast MCP server.
        repo_path: Repository path to scope filesystem access to.
        jar_path: Optional path to mcp-contrast jar (falls back to Docker).

    Returns:
        List of filtered MCP server instances for pydantic-ai agent.
    """
    from pydantic_ai.mcp import MCPServerStdio

    toolsets = []

    # Filesystem MCP — scoped to repo, read-only tools only
    # TODO(M-3): When Dockerized, install @modelcontextprotocol/server-filesystem@2025.11.25
    # at image build time and invoke the binary directly instead of npx. This eliminates
    # the runtime fetch from public npm and closes the supply chain risk.
    # See: .docs/smartfix_integration.md "Supply Chain" section.
    fs_server = MCPServerStdio(
        command="npx",
        args=[
            "-y",
            "--registry", "https://registry.npmjs.org",
            "--cache", "/tmp/.npm-cache",
            "--prefer-offline",
            "@modelcontextprotocol/server-filesystem@2025.11.25",
            repo_path,
        ],
        cwd=repo_path,
        tool_prefix="fs_",
        timeout=30,
    )
    fs_filtered = fs_server.filtered(
        lambda ctx, tool_def: tool_def.name in FILESYSTEM_TOOLS
    )
    toolsets.append(fs_filtered)

    # Contrast MCP — search only
    env = contrast_config.as_env()
    env["PATH"] = os.environ.get("PATH", "")

    jar = jar_path or _default_jar_path()
    if os.path.isfile(jar):
        contrast_server = MCPServerStdio(
            command="java",
            args=["-jar", jar, "-t", "stdio"],
            env=env,
            tool_prefix="contrast_",
            timeout=30,
        )
    else:
        contrast_server = MCPServerStdio(
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
            tool_prefix="contrast_",
            timeout=30,
        )

    contrast_filtered = contrast_server.filtered(
        lambda ctx, tool_def: tool_def.name in CONTRAST_TOOLS
    )
    toolsets.append(contrast_filtered)

    return toolsets
