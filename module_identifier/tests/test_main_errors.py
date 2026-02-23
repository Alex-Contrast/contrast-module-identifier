"""Tests for CLI exception handling in --single mode (AIML-475)."""

from unittest.mock import patch

import pytest
from mcp import McpError
from mcp.types import ErrorData

from module_identifier.__main__ import main
from module_identifier.config import ContrastConfig
from module_identifier.llm import LLMConfig


# -- Fixtures --


_CONTRAST_CONFIG = ContrastConfig(
    host_name="h", api_key="k", service_key="s", username="u", org_id="o",
)
_LLM_CONFIG = LLMConfig(
    provider="anthropic", model_name="claude-sonnet-4-5", anthropic_api_key="test",
)


# -- Helpers --


def _patch_configs(monkeypatch):
    """Patch config constructors to bypass .env file reads."""
    monkeypatch.setattr(
        "module_identifier.__main__.ContrastConfig.from_env",
        staticmethod(lambda: _CONTRAST_CONFIG),
    )
    monkeypatch.setattr(
        "module_identifier.__main__.LLMConfig.from_env",
        staticmethod(lambda: _LLM_CONFIG),
    )


def _run_main_single_error(monkeypatch, capsys):
    """Run main() expecting SystemExit, return (exit_code, stderr)."""
    _patch_configs(monkeypatch)
    monkeypatch.setattr("sys.argv", ["module_identifier", "--single", "/tmp/fakerepo"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    captured = capsys.readouterr()
    return exc_info.value.code, captured.err


def _run_main_single_ok(monkeypatch, capsys):
    """Run main() expecting normal return (no SystemExit)."""
    _patch_configs(monkeypatch)
    monkeypatch.setattr("sys.argv", ["module_identifier", "--single", "/tmp/fakerepo"])
    main()
    return capsys.readouterr()


# -- Exception handling tests --


class TestMcpConnectionRefused:
    @patch("module_identifier.__main__.identify_repo")
    def test_connection_refused_clean_exit(self, mock_identify, monkeypatch, capsys):
        mock_identify.side_effect = ConnectionRefusedError("Connection refused")

        code, stderr = _run_main_single_error(monkeypatch, capsys)

        assert code == 1
        assert "Cannot connect to Contrast MCP server" in stderr

    @patch("module_identifier.__main__.identify_repo")
    def test_connection_error_clean_exit(self, mock_identify, monkeypatch, capsys):
        mock_identify.side_effect = ConnectionError("Network unreachable")

        code, stderr = _run_main_single_error(monkeypatch, capsys)

        assert code == 1
        assert "Cannot connect to Contrast MCP server" in stderr


class TestMcpAuthFailure:
    @patch("module_identifier.__main__.identify_repo")
    def test_mcp_error_clean_exit(self, mock_identify, monkeypatch, capsys):
        mock_identify.side_effect = McpError(
            ErrorData(code=-32600, message="Authentication failed")
        )

        code, stderr = _run_main_single_error(monkeypatch, capsys)

        assert code == 1
        assert "Contrast API error" in stderr
        assert "Authentication failed" in stderr


class TestMcpServerStartFailure:
    @patch("module_identifier.__main__.identify_repo")
    def test_file_not_found_clean_exit(self, mock_identify, monkeypatch, capsys):
        mock_identify.side_effect = FileNotFoundError("java not found")

        code, stderr = _run_main_single_error(monkeypatch, capsys)

        assert code == 1
        assert "Cannot start Contrast MCP server" in stderr

    @patch("module_identifier.__main__.identify_repo")
    def test_os_error_clean_exit(self, mock_identify, monkeypatch, capsys):
        mock_identify.side_effect = OSError("No such process")

        code, stderr = _run_main_single_error(monkeypatch, capsys)

        assert code == 1
        assert "Cannot start Contrast MCP server" in stderr


class TestFilesystemErrors:
    @patch("module_identifier.__main__.identify_repo")
    def test_permission_error_clean_exit(self, mock_identify, monkeypatch, capsys):
        mock_identify.side_effect = PermissionError("Permission denied")

        code, stderr = _run_main_single_error(monkeypatch, capsys)

        assert code == 1
        assert "Cannot read repository" in stderr


class TestTimeoutErrors:
    @patch("module_identifier.__main__.identify_repo")
    def test_timeout_clean_exit(self, mock_identify, monkeypatch, capsys):
        mock_identify.side_effect = TimeoutError()

        code, stderr = _run_main_single_error(monkeypatch, capsys)

        assert code == 1
        assert "Timeout connecting to Contrast" in stderr


class TestUnexpectedErrors:
    @patch("module_identifier.__main__.identify_repo")
    def test_unexpected_error_clean_exit(self, mock_identify, monkeypatch, capsys):
        mock_identify.side_effect = RuntimeError("something broke")

        code, stderr = _run_main_single_error(monkeypatch, capsys)

        assert code == 1
        assert "Unexpected error" in stderr
        assert "RuntimeError" in stderr
        assert "something broke" in stderr


# -- Edge case tests (no crash) --


class TestNoMatchNoCrash:
    @patch("module_identifier.__main__.identify_repo")
    def test_empty_repo_no_crash(self, mock_identify, monkeypatch, capsys):
        """Empty repo: identify_repo returns None, CLI completes normally."""
        mock_identify.return_value = None
        _run_main_single_ok(monkeypatch, capsys)

    @patch("module_identifier.__main__.identify_repo")
    def test_zero_candidates_no_crash(self, mock_identify, monkeypatch, capsys):
        """Uninstrumented app: modules found but no Contrast apps → None, no crash."""
        mock_identify.return_value = None
        _run_main_single_ok(monkeypatch, capsys)

    @patch("module_identifier.__main__.identify_repo")
    def test_candidates_no_match_no_crash(self, mock_identify, monkeypatch, capsys):
        """Candidates exist but none match → None, no crash."""
        mock_identify.return_value = None
        _run_main_single_ok(monkeypatch, capsys)
