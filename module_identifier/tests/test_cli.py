"""Tests for CLI --output-env flag."""

import subprocess
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
    monkeypatch.setenv("CONTRAST_HOST_NAME", "h")
    monkeypatch.setenv("CONTRAST_API_KEY", "k")
    monkeypatch.setenv("CONTRAST_SERVICE_KEY", "s")
    monkeypatch.setenv("CONTRAST_USERNAME", "u")
    monkeypatch.setenv("CONTRAST_ORG_ID", "o")
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

    def test_no_match_writes_empty(self, tmp_path, env_vars):
        env_file = tmp_path / "result.env"

        with patch("module_identifier.__main__.identify_repo", new_callable=AsyncMock, return_value=None):
            from module_identifier.__main__ import main
            sys.argv = ["prog", str(tmp_path), "--single", "--output-env", str(env_file)]
            main()

        assert env_file.read_text() == "APP_ID=\n"

    def test_without_single_fails(self, tmp_path):
        env_file = tmp_path / "result.env"

        from module_identifier.__main__ import main
        sys.argv = ["prog", str(tmp_path), "--output-env", str(env_file)]
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        assert not env_file.exists()
