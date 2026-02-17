"""Tests for LLM agent — instruction building, scoring context, and message trimming."""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from module_identifier.llm.agent import (
    _build_scoring_context,
    _sanitize,
    _score_all_candidates,
    _trim_messages,
    resolve_module,
    AGENT_INSTRUCTIONS,
    TOP_N_CANDIDATES,
    MAX_MESSAGES_BEFORE_TRIM,
    MESSAGES_TO_KEEP_AFTER_TRIM,
)
from module_identifier.llm.config import LLMConfig
from module_identifier.llm.models import LLMMatch
from module_identifier.config import ContrastConfig
from module_identifier.models import DiscoveredModule, Ecosystem, Manifest
from module_identifier.resolver import AppCandidate


def _module(name="my-app", path=".", manifest=Manifest.PACKAGE_JSON, ecosystem=Ecosystem.NODE):
    return DiscoveredModule(name=name, path=path, manifest=manifest, ecosystem=ecosystem)


def _candidate(name="my-app", app_id="abc-123", language="Node"):
    return AppCandidate(app_id=app_id, name=name, language=language)


class TestBuildScoringContext:
    def test_no_scores(self):
        module = _module()
        context = _build_scoring_context(module, [], [])
        assert "No candidates" in context

    def test_with_scores(self):
        module = _module(name="order-api")
        c1 = _candidate(name="ordering-service", app_id="1", language="Node")
        c2 = _candidate(name="order-api-v2", app_id="2", language="Node")
        scores = [(c2, 0.45), (c1, 0.25)]

        context = _build_scoring_context(module, [c1, c2], scores)
        assert "order-api-v2" in context
        assert "ordering-service" in context
        assert "0.45" in context
        assert "below the 0.5 threshold" in context

    def test_very_low_scores(self):
        module = _module(name="foo")
        c1 = _candidate(name="totally-different", app_id="1")
        scores = [(c1, 0.1)]

        context = _build_scoring_context(module, [c1], scores)
        assert "very low" in context

    def test_limits_to_top_n(self):
        module = _module()
        candidates = [_candidate(name=f"app-{i}", app_id=str(i)) for i in range(10)]
        scores = [(c, 0.5 - i * 0.05) for i, c in enumerate(candidates)]

        context = _build_scoring_context(module, candidates, scores)
        # Should only show TOP_N_CANDIDATES entries
        assert context.count("→ score=") == TOP_N_CANDIDATES


class TestScoreAllCandidates:
    def test_returns_sorted_descending(self):
        module = _module(name="order-api")
        candidates = [
            _candidate(name="billing-api", app_id="1", language="Node"),
            _candidate(name="order-api", app_id="2", language="Node"),
            _candidate(name="order-service", app_id="3", language="Node"),
        ]

        scored = _score_all_candidates(module, candidates)
        scores = [s for _, s in scored]
        assert scores == sorted(scores, reverse=True)
        assert scored[0][0].name == "order-api"  # exact match should be first

    def test_empty_candidates(self):
        module = _module()
        assert _score_all_candidates(module, []) == []


class TestAgentInstructions:
    def test_placeholders_present(self):
        assert "{module_name}" in AGENT_INSTRUCTIONS
        assert "{module_path}" in AGENT_INSTRUCTIONS
        assert "{ecosystem}" in AGENT_INSTRUCTIONS
        assert "{manifest}" in AGENT_INSTRUCTIONS
        assert "{scoring_context}" in AGENT_INSTRUCTIONS

    def test_instructions_format(self):
        formatted = AGENT_INSTRUCTIONS.format(
            module_name="order-api",
            module_path="services/order",
            ecosystem="java",
            manifest="pom.xml",
            contrast_app_name_line="",
            scoring_context="No candidates scored above 0.0.",
            already_matched_context="",
        )
        assert "order-api" in formatted
        assert "services/order" in formatted
        assert "java" in formatted

    def test_instructions_with_contrast_app_name(self):
        formatted = AGENT_INSTRUCTIONS.format(
            module_name="order-api",
            module_path=".",
            ecosystem="java",
            manifest="pom.xml",
            contrast_app_name_line="- Contrast config app name: webgoat-sm\n",
            scoring_context="No candidates.",
            already_matched_context="",
        )
        assert "webgoat-sm" in formatted


class TestTrimMessages:
    def test_no_trim_under_threshold(self):
        messages = [f"msg-{i}" for i in range(MAX_MESSAGES_BEFORE_TRIM)]
        assert _trim_messages(messages) == messages

    def test_no_trim_at_threshold(self):
        messages = [f"msg-{i}" for i in range(MAX_MESSAGES_BEFORE_TRIM)]
        assert _trim_messages(messages) is messages

    def test_trims_over_threshold(self):
        messages = [f"msg-{i}" for i in range(MAX_MESSAGES_BEFORE_TRIM + 5)]
        result = _trim_messages(messages)
        assert len(result) == 1 + MESSAGES_TO_KEEP_AFTER_TRIM
        assert result[0] == "msg-0"  # first (system) message kept
        assert result[-1] == messages[-1]  # last message kept

    def test_empty_list(self):
        assert _trim_messages([]) == []

    def test_single_message(self):
        assert _trim_messages(["only"]) == ["only"]


class TestSanitize:
    def test_normal_module_names_unchanged(self):
        assert _sanitize("employee-management") == "employee-management"
        assert _sanitize("WhackTheCat") == "WhackTheCat"
        assert _sanitize("contrast-security-app") == "contrast-security-app"

    def test_scoped_and_qualified_names(self):
        assert _sanitize("com.acme:order-api") == "com.acme:order-api"
        assert _sanitize("@scope/billing-api") == "@scope/billing-api"
        assert _sanitize("github.com/acme/svc") == "github.com/acme/svc"

    def test_paths_with_spaces(self):
        assert _sanitize("My Project/src") == "My Project/src"
        assert _sanitize("C:\\Users\\dev\\My App") == "C:\\Users\\dev\\My App"

    def test_strips_control_characters(self):
        assert _sanitize("module\r\nname") == "module name"
        assert _sanitize("module\x00name") == "modulename"
        assert _sanitize("module\tname") == "modulename"

    def test_strips_curly_braces(self):
        assert "{" not in _sanitize("{__class__.__init__.__globals__}")
        assert "{" not in _sanitize("module-{name}")

    def test_strips_angle_brackets_and_quotes(self):
        assert "<" not in _sanitize("<script>alert(1)</script>")
        assert "'" not in _sanitize("module'name")
        assert "`" not in _sanitize("module`name")

    def test_truncates_long_input(self):
        assert len(_sanitize("a" * 500)) == 200

    def test_empty_string(self):
        assert _sanitize("") == ""

    def test_equals_sign_stripped(self):
        result = _sanitize("app_id=HACKED")
        assert "=" not in result


class TestResolveModule:
    def _llm_config(self):
        return LLMConfig(provider="anthropic", anthropic_api_key="sk-test")

    def _contrast_config(self):
        return ContrastConfig(
            host_name="test", api_key="k", service_key="s",
            username="u", org_id="o",
        )

    async def test_returns_match(self):
        module = _module(name="mystery-app", path="libs/mystery")
        candidates = [_candidate(name="other-app", app_id="1")]

        expected = LLMMatch(
            application_id="app-99",
            application_name="mystery-service",
            confidence="HIGH",
            reasoning="Found via README",
        )

        mock_result = MagicMock()
        mock_result.output = expected
        mock_result.usage.return_value = {}

        with patch("module_identifier.llm.agent.get_model", return_value=MagicMock()), \
             patch("module_identifier.llm.agent.create_mcp_toolsets", new_callable=AsyncMock, return_value=[]), \
             patch("module_identifier.llm.agent.Agent") as MockAgent:
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(return_value=mock_result)
            MockAgent.return_value = mock_agent_instance

            result = await resolve_module(
                module=module,
                candidates=candidates,
                llm_config=self._llm_config(),
                contrast_config=self._contrast_config(),
                repo_path="/tmp/repo",
            )

        assert result is not None
        assert result.application_id == "app-99"
        assert result.application_name == "mystery-service"

    async def test_returns_none_for_not_found(self):
        module = _module(name="internal-tool", path="tools/internal")
        candidates = []

        not_found = LLMMatch(
            application_id="NOT_FOUND",
            application_name="NOT_FOUND",
            confidence="LOW",
            reasoning="No Contrast app for this utility",
        )

        mock_result = MagicMock()
        mock_result.output = not_found

        with patch("module_identifier.llm.agent.get_model", return_value=MagicMock()), \
             patch("module_identifier.llm.agent.create_mcp_toolsets", new_callable=AsyncMock, return_value=[]), \
             patch("module_identifier.llm.agent.Agent") as MockAgent:
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(return_value=mock_result)
            MockAgent.return_value = mock_agent_instance

            result = await resolve_module(
                module=module,
                candidates=candidates,
                llm_config=self._llm_config(),
                contrast_config=self._contrast_config(),
                repo_path="/tmp/repo",
            )

        assert result is None

    async def test_returns_none_on_exception(self):
        module = _module(name="broken", path="libs/broken")

        with patch("module_identifier.llm.agent.get_model", return_value=MagicMock()), \
             patch("module_identifier.llm.agent.create_mcp_toolsets", new_callable=AsyncMock, return_value=[]), \
             patch("module_identifier.llm.agent.Agent") as MockAgent:
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(side_effect=RuntimeError("LLM failed"))
            MockAgent.return_value = mock_agent_instance

            result = await resolve_module(
                module=module,
                candidates=[],
                llm_config=self._llm_config(),
                contrast_config=self._contrast_config(),
                repo_path="/tmp/repo",
            )

        assert result is None
