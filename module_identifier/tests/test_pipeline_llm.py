"""Tests for pipeline LLM integration — mocked agent, real pipeline logic."""

from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from module_identifier.llm.config import LLMConfig
from module_identifier.llm.models import LLMMatch
from module_identifier.models import DiscoveredModule, Ecosystem, Manifest
from module_identifier.resolver import AppCandidate
from module_identifier.pipeline import run, PipelineResult
from module_identifier.config import ContrastConfig


def _module(name, path, manifest=Manifest.PACKAGE_JSON, ecosystem=Ecosystem.NODE):
    return DiscoveredModule(name=name, path=path, manifest=manifest, ecosystem=ecosystem)


def _llm_config():
    return LLMConfig(provider="anthropic", model_name="claude-sonnet-4-5", anthropic_api_key="sk-test")


def _contrast_config():
    return ContrastConfig(
        host_name="test", api_key="k", service_key="s",
        username="u", org_id="o",
    )


class TestPipelineResult:
    def test_has_llm_matched_field(self):
        result = PipelineResult(matched={}, unmatched=[], llm_matched={}, total=0)
        assert result.llm_matched == {}

    def test_default_llm_matched(self):
        result = PipelineResult(matched={}, unmatched=[], total=0)
        assert result.llm_matched == {}


class TestPipelineLLMIntegration:
    @pytest.fixture
    def mock_discover(self):
        with patch("module_identifier.pipeline.discover_modules") as mock:
            yield mock

    @pytest.fixture
    def mock_mcp(self):
        """Mock the ContrastMCP context manager."""
        with patch("module_identifier.pipeline.ContrastMCP") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.list_applications = AsyncMock(return_value=[
                AppCandidate(app_id="app-1", name="order-api", language="Node"),
                AppCandidate(app_id="app-2", name="billing-api", language="Node"),
            ])
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            yield mock_cls

    async def test_llm_resolves_unmatched(self, mock_discover, mock_mcp):
        """LLM should be called for unmatched modules and results merged."""
        mock_discover.return_value = [
            _module("order-api", "services/order"),
            _module("mystery-module", "libs/mystery"),
        ]

        llm_match = LLMMatch(
            application_id="app-99",
            application_name="mystery-service",
            confidence="MEDIUM",
            reasoning="Found via README analysis",
        )

        mock_llm = AsyncMock(return_value={"libs/mystery": llm_match})

        with patch("module_identifier.pipeline.resolve_modules") as mock_resolve, \
             patch("module_identifier.pipeline.llm_resolve_modules", mock_llm):
            mock_resolve.return_value = {
                "services/order": MagicMock(app_name="order-api", confidence=1.0),
                "libs/mystery": None,
            }

            result = await run("/tmp/repo", _contrast_config(), _llm_config())

        assert "services/order" in result.matched
        assert "libs/mystery" in result.llm_matched
        assert result.llm_matched["libs/mystery"].application_name == "mystery-service"
        assert result.unmatched == []

    async def test_llm_still_unmatched(self, mock_discover, mock_mcp):
        """If LLM also can't resolve, module stays in unmatched."""
        mock_discover.return_value = [
            _module("hopeless-module", "libs/hopeless"),
        ]

        mock_llm = AsyncMock(return_value={"libs/hopeless": None})

        with patch("module_identifier.pipeline.resolve_modules") as mock_resolve, \
             patch("module_identifier.pipeline.llm_resolve_modules", mock_llm):
            mock_resolve.return_value = {"libs/hopeless": None}

            result = await run("/tmp/repo", _contrast_config(), _llm_config())

        assert result.unmatched == ["libs/hopeless"]
        assert result.llm_matched == {}

    async def test_all_matched_skips_llm(self, mock_discover, mock_mcp):
        """If deterministic matches everything, LLM should not be called."""
        mock_discover.return_value = [
            _module("order-api", "services/order"),
        ]

        mock_llm = AsyncMock()

        with patch("module_identifier.pipeline.resolve_modules") as mock_resolve, \
             patch("module_identifier.pipeline.llm_resolve_modules", mock_llm):
            mock_resolve.return_value = {
                "services/order": MagicMock(app_name="order-api", confidence=1.0),
            }

            result = await run("/tmp/repo", _contrast_config(), _llm_config())

        mock_llm.assert_not_called()
        assert result.unmatched == []
