"""Tests for LLM configuration."""

import os
import pytest
from module_identifier.llm.config import LLMConfig


class TestLLMConfigValidation:
    def test_bedrock_valid(self):
        config = LLMConfig(
            provider="bedrock",
            aws_region="us-east-1",
            aws_access_key_id="AKID",
            aws_secret_access_key="secret",
            bedrock_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        )
        assert config.provider == "bedrock"

    def test_bedrock_missing_region(self):
        with pytest.raises(ValueError, match="AWS_REGION"):
            LLMConfig(
                provider="bedrock",
                aws_access_key_id="AKID",
                aws_secret_access_key="secret",
                bedrock_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            )

    def test_bedrock_missing_key(self):
        with pytest.raises(ValueError, match="AWS_ACCESS_KEY_ID"):
            LLMConfig(
                provider="bedrock",
                aws_region="us-east-1",
                aws_secret_access_key="secret",
                bedrock_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            )

    def test_bedrock_missing_model_id(self):
        with pytest.raises(ValueError, match="BEDROCK_MODEL_ID"):
            LLMConfig(
                provider="bedrock",
                aws_region="us-east-1",
                aws_access_key_id="AKID",
                aws_secret_access_key="secret",
            )

    def test_bedrock_valid_with_bearer_token(self):
        """Bearer token + region + model_id is sufficient — no IAM keys needed."""
        config = LLMConfig(
            provider="bedrock",
            aws_region="us-east-1",
            aws_bearer_token_bedrock="token-abc",
            bedrock_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        )
        assert config.provider == "bedrock"
        assert config.aws_bearer_token_bedrock == "token-abc"

    def test_bedrock_bearer_token_without_region_fails(self):
        """Region is still required even with bearer token."""
        with pytest.raises(ValueError, match="AWS_REGION"):
            LLMConfig(
                provider="bedrock",
                aws_bearer_token_bedrock="token-abc",
                bedrock_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            )

    def test_bedrock_bearer_token_without_model_fails(self):
        """Model ID is still required even with bearer token."""
        with pytest.raises(ValueError, match="BEDROCK_MODEL_ID"):
            LLMConfig(
                provider="bedrock",
                aws_region="us-east-1",
                aws_bearer_token_bedrock="token-abc",
            )

    def test_bedrock_no_credentials_at_all_fails(self):
        """Must have either bearer token or IAM keys."""
        with pytest.raises(ValueError, match="AWS_ACCESS_KEY_ID"):
            LLMConfig(
                provider="bedrock",
                aws_region="us-east-1",
                bedrock_model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
            )

    def test_anthropic_valid(self):
        config = LLMConfig(provider="anthropic", anthropic_api_key="sk-test")
        assert config.provider == "anthropic"

    def test_anthropic_missing_key(self):
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            LLMConfig(provider="anthropic")

    def test_azure_valid(self):
        config = LLMConfig(
            provider="azure",
            azure_openai_endpoint="https://foo.openai.azure.com",
            azure_openai_api_key="key",
            azure_openai_deployment="gpt-4",
        )
        assert config.provider == "azure"

    def test_azure_missing_endpoint(self):
        with pytest.raises(ValueError, match="AZURE_OPENAI_ENDPOINT"):
            LLMConfig(
                provider="azure",
                azure_openai_api_key="key",
                azure_openai_deployment="gpt-4",
            )

    def test_gemini_valid(self):
        config = LLMConfig(provider="gemini", google_api_key="gk-test", gemini_model="gemini-1.5-pro")
        assert config.provider == "gemini"

    def test_gemini_missing_key(self):
        with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
            LLMConfig(provider="gemini", gemini_model="gemini-1.5-pro")

    def test_gemini_missing_model(self):
        with pytest.raises(ValueError, match="GEMINI_MODEL"):
            LLMConfig(provider="gemini", google_api_key="gk-test")

    def test_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            LLMConfig(provider="openai")


class TestLLMConfigFromEnv:
    def test_from_env_bedrock(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "bedrock")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKID")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")

        config = LLMConfig.from_env()
        assert config.provider == "bedrock"
        assert config.aws_region == "us-east-1"
        assert config.bedrock_model_id == "us.anthropic.claude-sonnet-4-20250514-v1:0"

    def test_from_env_anthropic(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

        config = LLMConfig.from_env()
        assert config.provider == "anthropic"
        assert config.anthropic_api_key == "sk-test"

    def test_from_env_bedrock_bearer_token(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "bedrock")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "token-abc")
        monkeypatch.setenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)

        config = LLMConfig.from_env()
        assert config.provider == "bedrock"
        assert config.aws_bearer_token_bedrock == "token-abc"

    def test_from_env_defaults_to_bedrock(self, monkeypatch):
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKID")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")

        config = LLMConfig.from_env()
        assert config.provider == "bedrock"

    def test_from_env_debug_flag(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("DEBUG_LOGGING", "true")

        config = LLMConfig.from_env()
        assert config.debug is True


class TestLLMConfigDefaults:
    def test_debug_default_false(self):
        config = LLMConfig(provider="anthropic", anthropic_api_key="sk-test")
        assert config.debug is False
