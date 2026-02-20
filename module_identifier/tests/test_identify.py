"""Tests for identify_repo() — EA entry point."""

from unittest.mock import AsyncMock, patch

import pytest

from module_identifier.config import ContrastConfig
from module_identifier.identify import _best_deterministic_match, _is_ambiguous, identify_repo
from module_identifier.llm import LLMConfig
from module_identifier.models import DiscoveredModule, Ecosystem, Manifest
from module_identifier.resolver import AppCandidate, AppMatch


def _module(name, manifest=Manifest.POM_XML, ecosystem=Ecosystem.JAVA, path="."):
    return DiscoveredModule(name=name, path=path, manifest=manifest, ecosystem=ecosystem)


def _candidate(name, app_id="app-1", language="Java"):
    return AppCandidate(app_id=app_id, name=name, language=language)


@pytest.fixture
def config():
    return ContrastConfig(
        host_name="h", api_key="k", service_key="s",
        username="u", org_id="o",
    )


@pytest.fixture
def llm_config():
    return LLMConfig(provider="anthropic", model_name="claude-sonnet-4-5", anthropic_api_key="test")


# --- _best_deterministic_match ---


class TestBestDeterministicMatch:
    def test_single_module_exact_match(self):
        modules = [_module("order-api")]
        candidates = [_candidate("order-api")]
        best = _best_deterministic_match(modules, candidates)
        assert best is not None
        assert best.app_name == "order-api"
        assert best.confidence == 1.0

    def test_picks_highest_confidence(self):
        modules = [
            _module("frontend", Manifest.PACKAGE_JSON, Ecosystem.NODE, path="ui"),
            _module("order-api", path="backend"),
        ]
        candidates = [_candidate("order-api")]
        best = _best_deterministic_match(modules, candidates)
        assert best is not None
        assert best.module.name == "order-api"

    def test_no_candidates_returns_none(self):
        modules = [_module("order-api")]
        assert _best_deterministic_match(modules, []) is None

    def test_no_modules_returns_none(self):
        candidates = [_candidate("order-api")]
        assert _best_deterministic_match([], candidates) is None

    def test_no_overlap_returns_low_score(self):
        modules = [_module("xyz-service")]
        candidates = [_candidate("abc-app")]
        best = _best_deterministic_match(modules, candidates)
        # Still returns something (threshold=0.0) but low confidence
        assert best is None or best.confidence < 0.5


# --- _is_ambiguous ---


class TestIsAmbiguous:
    def test_single_strong_candidate_not_ambiguous(self):
        module = _module("order-api")
        candidates = [_candidate("order-api"), _candidate("zzz-unrelated")]
        assert not _is_ambiguous(module, candidates)

    def test_multiple_strong_candidates_is_ambiguous(self):
        """employee-management case: exact match + prefixed variant both score high."""
        module = _module("employee-management")
        candidates = [
            _candidate("employee-management", app_id="a1"),
            _candidate("alex-employee-management", app_id="a2"),
        ]
        assert _is_ambiguous(module, candidates)

    def test_no_strong_candidates_not_ambiguous(self):
        module = _module("xyz-service")
        candidates = [_candidate("abc-app"), _candidate("def-app")]
        assert not _is_ambiguous(module, candidates)


# --- identify_repo ---


def _mock_mcp(candidates):
    """Create a mock ContrastMCP context manager returning candidates."""
    mcp = AsyncMock()
    mcp.list_applications = AsyncMock(return_value=candidates)
    mcp.__aenter__ = AsyncMock(return_value=mcp)
    mcp.__aexit__ = AsyncMock(return_value=False)
    return mcp


class TestIdentifyRepo:
    @patch("module_identifier.identify.ContrastMCP")
    @patch("module_identifier.identify.discover_modules")
    async def test_exact_match_returns_app(self, mock_discover, mock_mcp_cls, tmp_path, config, llm_config):
        mock_discover.return_value = [_module("order-api")]
        mock_mcp_cls.return_value = _mock_mcp([_candidate("order-api")])

        result = await identify_repo(tmp_path, config, llm_config)

        assert result is not None
        assert result.app_id == "app-1"
        assert result.app_name == "order-api"
        assert result.confidence == 1.0
        assert result.source == "deterministic"

    @patch("module_identifier.llm.agent.resolve_module")
    @patch("module_identifier.identify.ContrastMCP")
    @patch("module_identifier.identify.discover_modules")
    async def test_below_threshold_returns_llm(self, mock_discover, mock_mcp_cls, mock_llm, tmp_path, config, llm_config):
        mock_discover.return_value = [_module("xyz-service")]
        mock_mcp_cls.return_value = _mock_mcp([_candidate("abc-app")])
        mock_llm.return_value = None

        result = await identify_repo(tmp_path, config, llm_config)
        assert result is None
        mock_llm.assert_called_once()

    @patch("module_identifier.identify.ContrastMCP")
    @patch("module_identifier.identify.discover_modules")
    async def test_no_modules_returns_none(self, mock_discover, mock_mcp_cls, tmp_path, config, llm_config):
        mock_discover.return_value = []
        mock_mcp_cls.return_value = _mock_mcp([_candidate("order-api")])

        result = await identify_repo(tmp_path, config, llm_config)
        assert result is None

    @patch("module_identifier.identify.ContrastMCP")
    @patch("module_identifier.identify.discover_modules")
    async def test_no_candidates_returns_none(self, mock_discover, mock_mcp_cls, tmp_path, config, llm_config):
        mock_discover.return_value = [_module("order-api")]
        mock_mcp_cls.return_value = _mock_mcp([])

        result = await identify_repo(tmp_path, config, llm_config)
        assert result is None

    @patch("module_identifier.identify.ContrastMCP")
    @patch("module_identifier.identify.discover_modules")
    async def test_picks_best_across_modules(self, mock_discover, mock_mcp_cls, tmp_path, config, llm_config):
        mock_discover.return_value = [
            _module("frontend", Manifest.PACKAGE_JSON, Ecosystem.NODE, path="ui"),
            _module("order-api", path="backend"),
        ]
        mock_mcp_cls.return_value = _mock_mcp([_candidate("order-api")])

        result = await identify_repo(tmp_path, config, llm_config)
        assert result is not None
        assert result.app_name == "order-api"
        assert result.module.path == "backend"

    @patch("module_identifier.identify.ContrastMCP")
    @patch("module_identifier.identify.discover_modules")
    async def test_custom_threshold(self, mock_discover, mock_mcp_cls, tmp_path, config, llm_config):
        """A match at 0.8 passes default 0.7 threshold but fails 0.9."""
        mock_discover.return_value = [_module("order-api")]
        # Exact name + language match = 1.0, so use a partial match
        mock_mcp_cls.return_value = _mock_mcp([
            _candidate("order-api-service", language="Java"),
        ])

        # Low threshold — partial match should pass
        result = await identify_repo(tmp_path, config, llm_config, confidence_threshold=0.3)
        assert result is not None

        # High threshold — same match should fail (falls to LLM)
        with patch("module_identifier.llm.agent.resolve_module", return_value=None):
            result = await identify_repo(tmp_path, config, llm_config, confidence_threshold=0.99)
        assert result is None

    @patch("module_identifier.llm.agent.resolve_module")
    @patch("module_identifier.identify.ContrastMCP")
    @patch("module_identifier.identify.discover_modules")
    async def test_llm_fallback(self, mock_discover, mock_mcp_cls, mock_llm, tmp_path, config, llm_config):
        """When below threshold, LLM is called."""
        mock_discover.return_value = [_module("xyz-service")]
        mock_mcp_cls.return_value = _mock_mcp([_candidate("abc-app")])

        from module_identifier.llm.models import LLMMatch
        mock_llm.return_value = LLMMatch(
            application_id="app-99",
            application_name="XYZ Service",
            confidence="HIGH",
            reasoning="Found via README",
        )

        result = await identify_repo(tmp_path, config, llm_config)
        assert result is not None
        assert result.app_id == "app-99"
        assert result.app_name == "XYZ Service"
        assert result.confidence == 0.95
        assert result.source == "llm"
        mock_llm.assert_called_once()

    @patch("module_identifier.llm.agent.resolve_module")
    @patch("module_identifier.identify.ContrastMCP")
    @patch("module_identifier.identify.discover_modules")
    async def test_llm_not_found_returns_none(self, mock_discover, mock_mcp_cls, mock_llm, tmp_path, config, llm_config):
        """LLM returning None (NOT_FOUND) means no match."""
        mock_discover.return_value = [_module("xyz-service")]
        mock_mcp_cls.return_value = _mock_mcp([_candidate("abc-app")])
        mock_llm.return_value = None

        result = await identify_repo(tmp_path, config, llm_config)
        assert result is None

    @patch("module_identifier.llm.agent.resolve_module")
    @patch("module_identifier.identify.ContrastMCP")
    @patch("module_identifier.identify.discover_modules")
    async def test_ambiguous_triggers_llm(self, mock_discover, mock_mcp_cls, mock_llm, tmp_path, config, llm_config):
        """employee-management case: exact match exists but so does a prefixed variant."""
        mock_discover.return_value = [_module("employee-management")]
        mock_mcp_cls.return_value = _mock_mcp([
            _candidate("employee-management", app_id="wrong"),
            _candidate("alex-employee-management", app_id="correct"),
        ])

        from module_identifier.llm.models import LLMMatch
        mock_llm.return_value = LLMMatch(
            application_id="correct",
            application_name="alex-employee-management",
            confidence="HIGH",
            reasoning="README says alex-employee-management",
        )

        result = await identify_repo(tmp_path, config, llm_config)
        assert result is not None
        assert result.app_id == "correct"
        assert result.source == "llm"
        mock_llm.assert_called_once()

    @patch("module_identifier.llm.agent.resolve_module")
    @patch("module_identifier.identify.ContrastMCP")
    @patch("module_identifier.identify.discover_modules")
    async def test_ambiguous_llm_not_found(self, mock_discover, mock_mcp_cls, mock_llm, tmp_path, config, llm_config):
        """Ambiguous match where LLM also can't decide returns None."""
        mock_discover.return_value = [_module("employee-management")]
        mock_mcp_cls.return_value = _mock_mcp([
            _candidate("employee-management", app_id="a1"),
            _candidate("alex-employee-management", app_id="a2"),
        ])
        mock_llm.return_value = None

        result = await identify_repo(tmp_path, config, llm_config)
        assert result is None

    @patch("module_identifier.identify.ContrastMCP")
    @patch("module_identifier.identify.discover_modules")
    async def test_contrast_yaml_skips_ambiguity(self, mock_discover, mock_mcp_cls, tmp_path, config, llm_config):
        """contrast_security.yaml match is trusted — no ambiguity check."""
        mock_discover.return_value = [
            DiscoveredModule(
                name="employee-management", path=".", manifest=Manifest.POM_XML,
                ecosystem=Ecosystem.JAVA, contrast_app_name="alex-employee-management",
            ),
        ]
        mock_mcp_cls.return_value = _mock_mcp([
            _candidate("employee-management", app_id="wrong"),
            _candidate("alex-employee-management", app_id="correct"),
        ])

        result = await identify_repo(tmp_path, config, llm_config)
        assert result is not None
        assert result.app_id == "correct"
        assert result.app_name == "alex-employee-management"
        assert result.source == "deterministic"
