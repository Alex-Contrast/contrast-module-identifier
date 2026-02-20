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

    @patch("module_identifier.llm.providers._create_bedrock_model")
    def test_bedrock_bearer_token_dispatch(self, mock_create):
        """Bearer token config still dispatches to bedrock factory."""
        mock_create.return_value = MagicMock()
        config = LLMConfig(
            provider="bedrock",
            model_name="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            aws_region_name="us-east-1",
            aws_bearer_token_bedrock="token-abc",
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


class TestBedrockModelCreation:
    @patch("pydantic_ai.providers.bedrock.BedrockProvider")
    @patch("pydantic_ai.models.bedrock.BedrockConverseModel")
    def test_bearer_token_passes_api_key(self, mock_model_cls, mock_provider_cls):
        """When bearer token is set, pass it as api_key to BedrockProvider."""
        from module_identifier.llm.providers import _create_bedrock_model

        config = LLMConfig(
            provider="bedrock",
            model_name="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            aws_region_name="us-east-1",
            aws_bearer_token_bedrock="token-abc",
        )
        _create_bedrock_model(config)

        mock_provider_cls.assert_called_once_with(
            api_key="token-abc",
            region_name="us-east-1",
        )
        mock_model_cls.assert_called_once_with(
            model_name="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            provider=mock_provider_cls.return_value,
        )

    @patch("boto3.Session")
    @patch("pydantic_ai.providers.bedrock.BedrockProvider")
    @patch("pydantic_ai.models.bedrock.BedrockConverseModel")
    def test_iam_keys_uses_boto3_session(self, mock_model_cls, mock_provider_cls, mock_session_cls):
        """When IAM keys are set (no bearer token), use boto3 session as before."""
        from module_identifier.llm.providers import _create_bedrock_model

        config = LLMConfig(
            provider="bedrock",
            model_name="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            aws_region_name="us-east-1",
            aws_access_key_id="AKID",
            aws_secret_access_key="secret",
        )
        _create_bedrock_model(config)

        mock_session_cls.assert_called_once_with(
            aws_access_key_id="AKID",
            aws_secret_access_key="secret",
            aws_session_token=None,
            region_name="us-east-1",
        )
        mock_provider_cls.assert_called_once_with(
            bedrock_client=mock_session_cls.return_value.client.return_value,
        )
