"""Tests for LLM provider factory."""

import pytest
from unittest.mock import patch, MagicMock
from module_identifier.llm.config import LLMConfig
from module_identifier.llm.providers import get_model


class TestGetModel:
    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            LLMConfig(provider="unknown", model_name="x")

    @patch("module_identifier.llm.providers._create_bedrock_model")
    def test_bedrock_dispatch(self, mock_create):
        mock_create.return_value = MagicMock()
        config = LLMConfig(
            provider="bedrock",
            model_name="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            aws_region_name="us-east-1",
            aws_access_key_id="AKID",
            aws_secret_access_key="secret",
            aws_session_token="token",
        )
        get_model(config)
        mock_create.assert_called_once_with(config)

    @patch("module_identifier.llm.providers._create_anthropic_model")
    def test_anthropic_dispatch(self, mock_create):
        mock_create.return_value = MagicMock()
        config = LLMConfig(provider="anthropic", model_name="claude-sonnet-4-5", anthropic_api_key="sk-test")
        get_model(config)
        mock_create.assert_called_once_with(config)

    @patch("module_identifier.llm.providers._create_gemini_model")
    def test_gemini_dispatch(self, mock_create):
        mock_create.return_value = MagicMock()
        config = LLMConfig(provider="gemini", model_name="gemini-2.0-flash", gemini_api_key="gk-test")
        get_model(config)
        mock_create.assert_called_once_with(config)
