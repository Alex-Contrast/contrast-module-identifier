"""Tests for LLM MCP toolset setup."""

import os
from unittest.mock import patch, MagicMock

import pytest

from module_identifier.config import ContrastConfig
from module_identifier.llm.mcp_tools import (
    create_mcp_toolsets,
    FILESYSTEM_TOOLS,
    CONTRAST_TOOLS,
)


def _contrast_config():
    return ContrastConfig(
        host_name="test.contrastsecurity.com",
        api_key="api-key",
        service_key="svc-key",
        username="user",
        org_id="org-123",
    )


class TestToolSets:
    def test_filesystem_tools_use_double_underscore_prefix(self):
        """Tool names have double underscore: prefix_ + _ + tool_name."""
        for tool in FILESYSTEM_TOOLS:
            assert tool.startswith("fs__"), f"Expected fs__ prefix, got: {tool}"

    def test_contrast_tools_use_double_underscore_prefix(self):
        for tool in CONTRAST_TOOLS:
            assert tool.startswith("contrast__"), f"Expected contrast__ prefix, got: {tool}"

    def test_filesystem_tools_are_read_only(self):
        """No write/delete/move tools should be exposed."""
        write_tools = {"fs__write_file", "fs__create_directory", "fs__move_file", "fs__delete_file"}
        assert FILESYSTEM_TOOLS.isdisjoint(write_tools)

    def test_contrast_tools_only_search(self):
        """Only search_applications should be exposed, not all 13+ tools."""
        assert len(CONTRAST_TOOLS) == 1
        assert "contrast__search_applications" in CONTRAST_TOOLS


class TestCreateMCPToolsets:
    @patch("pydantic_ai.mcp.MCPServerStdio")
    async def test_creates_two_toolsets(self, MockStdio):
        """Should create filesystem + Contrast MCP servers."""
        mock_server = MagicMock()
        mock_server.filtered.return_value = MagicMock()
        MockStdio.return_value = mock_server

        toolsets = await create_mcp_toolsets(_contrast_config(), "/tmp/repo")
        assert len(toolsets) == 2

    @patch("pydantic_ai.mcp.MCPServerStdio")
    async def test_filesystem_scoped_to_repo_path(self, MockStdio):
        """Filesystem MCP should receive the repo path in its args."""
        mock_server = MagicMock()
        mock_server.filtered.return_value = MagicMock()
        MockStdio.return_value = mock_server

        await create_mcp_toolsets(_contrast_config(), "/my/repo")

        # First call is filesystem server
        fs_call_kwargs = MockStdio.call_args_list[0].kwargs
        assert "/my/repo" in fs_call_kwargs["args"]

    @patch("pydantic_ai.mcp.MCPServerStdio")
    async def test_uses_jar_when_exists(self, MockStdio):
        """Should use java -jar when jar file exists."""
        mock_server = MagicMock()
        mock_server.filtered.return_value = MagicMock()
        MockStdio.return_value = mock_server

        with patch("os.path.isfile", return_value=True):
            await create_mcp_toolsets(_contrast_config(), "/tmp/repo", jar_path="/path/to/mcp.jar")

        # Second call is Contrast server — should use java
        contrast_call_kwargs = MockStdio.call_args_list[1].kwargs
        assert contrast_call_kwargs["command"] == "java"

    @patch("pydantic_ai.mcp.MCPServerStdio")
    async def test_falls_back_to_docker(self, MockStdio):
        """Should use Docker when no jar file exists."""
        mock_server = MagicMock()
        mock_server.filtered.return_value = MagicMock()
        MockStdio.return_value = mock_server

        with patch("os.path.isfile", return_value=False):
            await create_mcp_toolsets(_contrast_config(), "/tmp/repo")

        contrast_call_kwargs = MockStdio.call_args_list[1].kwargs
        assert contrast_call_kwargs["command"] == "docker"

    @patch("pydantic_ai.mcp.MCPServerStdio")
    async def test_filtered_called_on_both_servers(self, MockStdio):
        """Both servers should have .filtered() applied for token savings."""
        mock_server = MagicMock()
        mock_server.filtered.return_value = MagicMock()
        MockStdio.return_value = mock_server

        await create_mcp_toolsets(_contrast_config(), "/tmp/repo")

        # filtered() called twice: once for fs, once for contrast
        assert mock_server.filtered.call_count == 2
