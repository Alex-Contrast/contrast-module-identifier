"""Tests for CLI output (--output-env, --output, no-match guidance)."""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from module_identifier.config import ContrastConfig
from module_identifier.llm import LLMConfig
from module_identifier.models import DiscoveredModule, Ecosystem, Manifest
from module_identifier.resolver import AppCandidate, AppMatch


def _module(name="order-api"):
    return DiscoveredModule(
        name=name, path=".", manifest=Manifest.POM_XML, ecosystem=Ecosystem.JAVA,
    )


def _match(module=None, app_id="abc-123", app_name="order-api"):
    m = module or _module()
    return AppMatch(
        module=m, app_id=app_id, app_name=app_name,
        confidence=0.95, search_term="order-api", source="deterministic",
    )


@pytest.fixture
def env_vars(monkeypatch):
    """Set required env vars so ContrastConfig and LLMConfig don't fail."""
    # ContrastConfig reads from os.environ
    monkeypatch.setenv("CONTRAST_HOST_NAME", "app.contrastsecurity.com")
    monkeypatch.setenv("CONTRAST_API_KEY", "k")
    monkeypatch.setenv("CONTRAST_SERVICE_KEY", "s")
    monkeypatch.setenv("CONTRAST_USERNAME", "u")
    monkeypatch.setenv("CONTRAST_ORG_ID", "org-123")
    # LLMConfig reads from .env via dotenv_values
    monkeypatch.setattr("module_identifier.llm.config.dotenv_values", lambda: {
        "AGENT_MODEL": "anthropic/claude-sonnet-4-5",
        "ANTHROPIC_API_KEY": "test",
    })


class TestOutputEnv:
    def test_match_writes_app_id(self, tmp_path, env_vars):
        env_file = tmp_path / "result.env"
        match = _match()

        with patch("module_identifier.__main__.identify_repo", new_callable=AsyncMock, return_value=match):
            from module_identifier.__main__ import main
            sys.argv = ["prog", str(tmp_path), "--single", "--output-env", str(env_file)]
            main()

        assert env_file.read_text() == "APP_ID=abc-123\n"

    def test_no_match_writes_empty_and_exits_1(self, tmp_path, env_vars):
        env_file = tmp_path / "result.env"

        with patch("module_identifier.__main__.identify_repo", new_callable=AsyncMock, return_value=None):
            from module_identifier.__main__ import main
            sys.argv = ["prog", str(tmp_path), "--single", "--output-env", str(env_file)]
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        assert env_file.read_text() == "APP_ID=\n"

    def test_without_single_fails(self, tmp_path):
        env_file = tmp_path / "result.env"

        from module_identifier.__main__ import main
        sys.argv = ["prog", str(tmp_path), "--output-env", str(env_file)]
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        assert not env_file.exists()


class TestNoMatchGuidance:
    def test_no_match_prints_guidance_to_stderr(self, tmp_path, env_vars, capsys):
        with patch("module_identifier.__main__.identify_repo", new_callable=AsyncMock, return_value=None):
            from module_identifier.__main__ import main
            sys.argv = ["prog", str(tmp_path), "--single"]
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        stderr = capsys.readouterr().err
        assert "No matching Contrast application found." in stderr
        assert "Set CONTRAST_APP_ID manually:" in stderr
        assert "app.contrastsecurity.com" in stderr
        assert "org-123" in stderr

    def test_no_match_exits_1(self, tmp_path, env_vars):
        with patch("module_identifier.__main__.identify_repo", new_callable=AsyncMock, return_value=None):
            from module_identifier.__main__ import main
            sys.argv = ["prog", str(tmp_path), "--single"]
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1

    def test_match_exits_0(self, tmp_path, env_vars):
        match = _match()
        with patch("module_identifier.__main__.identify_repo", new_callable=AsyncMock, return_value=match):
            from module_identifier.__main__ import main
            sys.argv = ["prog", str(tmp_path), "--single"]
            main()  # should not raise SystemExit


class TestJsonOutput:
    def test_matched_has_status_field(self, tmp_path, env_vars):
        json_file = tmp_path / "result.json"
        match = _match()

        with patch("module_identifier.__main__.identify_repo", new_callable=AsyncMock, return_value=match):
            from module_identifier.__main__ import main
            sys.argv = ["prog", str(tmp_path), "--single", "--output", str(json_file)]
            main()

        data = json.loads(json_file.read_text())
        assert data["status"] == "matched"
        assert data["app_id"] == "abc-123"
        assert "guidance" not in data

    def test_no_match_has_status_and_guidance(self, tmp_path, env_vars):
        json_file = tmp_path / "result.json"

        with patch("module_identifier.__main__.identify_repo", new_callable=AsyncMock, return_value=None):
            from module_identifier.__main__ import main
            sys.argv = ["prog", str(tmp_path), "--single", "--output", str(json_file)]
            with pytest.raises(SystemExit):
                main()

        data = json.loads(json_file.read_text())
        assert data["status"] == "no_match"
        assert data["app_id"] is None
        assert "Set CONTRAST_APP_ID manually:" in data["guidance"]
        assert "app.contrastsecurity.com" in data["guidance"]
        assert "org-123" in data["guidance"]
