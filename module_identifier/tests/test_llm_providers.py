"""Tests for LLM provider factory."""

import pytest
from unittest.mock import patch, MagicMock
from module_identifier.llm.config import LLMConfig
from module_identifier.llm.providers import get_model


class TestGetModel:
    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            LLMConfig(provider="unknown")

    @patch("module_identifier.llm.providers._create_bedrock_model")
    def test_bedrock_dispatch(self, mock_create):
        mock_create.return_value = MagicMock()
        config = LLMConfig(
            provider="bedrock",
            aws_region="us-east-1",
            aws_access_key_id="AKID",
            aws_secret_access_key="secret",
            bedrock_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        )
        get_model(config)
        mock_create.assert_called_once_with(config)

    @patch("module_identifier.llm.providers._create_anthropic_model")
    def test_anthropic_dispatch(self, mock_create):
        mock_create.return_value = MagicMock()
        config = LLMConfig(provider="anthropic", anthropic_api_key="sk-test")
        get_model(config)
        mock_create.assert_called_once_with(config)

    @patch("module_identifier.llm.providers._create_azure_model")
    def test_azure_dispatch(self, mock_create):
        mock_create.return_value = MagicMock()
        config = LLMConfig(
            provider="azure",
            azure_openai_endpoint="https://foo.openai.azure.com",
            azure_openai_api_key="key",
            azure_openai_deployment="gpt-4",
        )
        get_model(config)
        mock_create.assert_called_once_with(config)

    @patch("module_identifier.llm.providers._create_gemini_model")
    def test_gemini_dispatch(self, mock_create):
        mock_create.return_value = MagicMock()
        config = LLMConfig(provider="gemini", google_api_key="gk-test", gemini_model="gemini-1.5-pro")
        get_model(config)
        mock_create.assert_called_once_with(config)
