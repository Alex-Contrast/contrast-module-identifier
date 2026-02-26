"""Tests for LLM provider factory."""

import pytest
from unittest.mock import patch, MagicMock
from module_identifier.config import ContrastConfig
from module_identifier.llm.config import LLMConfig, DEFAULT_CONTRAST_MODEL
from module_identifier.llm.providers import get_model


def _make_contrast_config(**overrides):
    defaults = dict(
        host_name="app.contrastsecurity.com",
        api_key="test-api-key",
        service_key="test-service-key",
        username="test-user",
        org_id="test-org-id",
    )
    defaults.update(overrides)
    return ContrastConfig(**defaults)


class TestGetModel:
    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            LLMConfig(provider="unknown", model_name="x")

    @patch("module_identifier.llm.providers._create_contrast_model")
    def test_contrast_dispatch(self, mock_create):
        mock_create.return_value = MagicMock()
        config = LLMConfig(provider="contrast", model_name=DEFAULT_CONTRAST_MODEL)
        cc = _make_contrast_config()
        get_model(config, contrast_config=cc)
        mock_create.assert_called_once_with(config, cc)

    def test_contrast_without_contrast_config_raises(self):
        config = LLMConfig(provider="contrast", model_name=DEFAULT_CONTRAST_MODEL)
        with pytest.raises(ValueError, match="requires ContrastConfig"):
            get_model(config)

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


class TestContrastModelCreation:
    @patch("anthropic.AsyncAnthropic")
    @patch("pydantic_ai.providers.anthropic.AnthropicProvider")
    @patch("pydantic_ai.models.anthropic.AnthropicModel")
    def test_creates_client_with_correct_base_url_and_headers(
        self, mock_model_cls, mock_provider_cls, mock_client_cls
    ):
        from module_identifier.llm.providers import _create_contrast_model

        config = LLMConfig(provider="contrast", model_name=DEFAULT_CONTRAST_MODEL)
        cc = _make_contrast_config()
        _create_contrast_model(config, cc)

        import base64
        expected_auth = base64.b64encode(b"test-user:test-service-key").decode()

        mock_client_cls.assert_called_once_with(
            api_key="test-api-key",
            base_url="https://app.contrastsecurity.com/api/llm-proxy/v2/organizations/test-org-id/anthropic",
            default_headers={
                "API-Key": "test-api-key",
                "Authorization": expected_auth,
            },
        )
        mock_provider_cls.assert_called_once_with(
            anthropic_client=mock_client_cls.return_value,
        )
        mock_model_cls.assert_called_once_with(
            model_name=DEFAULT_CONTRAST_MODEL,
            provider=mock_provider_cls.return_value,
        )

    @patch("anthropic.AsyncAnthropic")
    @patch("pydantic_ai.providers.anthropic.AnthropicProvider")
    @patch("pydantic_ai.models.anthropic.AnthropicModel")
    def test_strips_trailing_slash_from_host(
        self, mock_model_cls, mock_provider_cls, mock_client_cls
    ):
        from module_identifier.llm.providers import _create_contrast_model

        config = LLMConfig(provider="contrast", model_name=DEFAULT_CONTRAST_MODEL)
        cc = _make_contrast_config(host_name="app.contrastsecurity.com/")
        _create_contrast_model(config, cc)

        call_kwargs = mock_client_cls.call_args[1]
        assert call_kwargs["base_url"] == "https://app.contrastsecurity.com/api/llm-proxy/v2/organizations/test-org-id/anthropic"
