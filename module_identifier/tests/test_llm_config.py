"""Tests for LLM configuration."""

import pytest
from module_identifier.llm.config import LLMConfig, _parse_agent_model


class TestParseAgentModel:
    def test_bedrock(self):
        provider, model = _parse_agent_model("bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0")
        assert provider == "bedrock"
        assert model == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

    def test_anthropic(self):
        provider, model = _parse_agent_model("anthropic/claude-sonnet-4-5")
        assert provider == "anthropic"
        assert model == "claude-sonnet-4-5"

    def test_gemini(self):
        provider, model = _parse_agent_model("gemini/gemini-2.0-flash")
        assert provider == "gemini"
        assert model == "gemini-2.0-flash"

    def test_case_insensitive_provider(self):
        provider, model = _parse_agent_model("Bedrock/some-model")
        assert provider == "bedrock"

    def test_no_slash_raises(self):
        with pytest.raises(ValueError, match="must use provider/model format"):
            _parse_agent_model("just-a-model")

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider 'openai'"):
            _parse_agent_model("openai/gpt-4")

    def test_empty_model_raises(self):
        with pytest.raises(ValueError, match="must include a model name"):
            _parse_agent_model("bedrock/")


class TestLLMConfigValidation:
    def test_bedrock_valid(self):
        config = LLMConfig(
            provider="bedrock",
            model_name="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            aws_region_name="us-east-1",
            aws_access_key_id="AKID",
            aws_secret_access_key="secret",
            aws_session_token="token",
        )
        assert config.provider == "bedrock"
        assert config.model_name == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

    def test_bedrock_missing_region(self):
        with pytest.raises(ValueError, match="AWS_REGION_NAME"):
            LLMConfig(
                provider="bedrock",
                model_name="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                aws_access_key_id="AKID",
                aws_secret_access_key="secret",
                aws_session_token="token",
            )

    def test_bedrock_missing_key(self):
        with pytest.raises(ValueError, match="AWS_ACCESS_KEY_ID"):
            LLMConfig(
                provider="bedrock",
                model_name="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                aws_region_name="us-east-1",
                aws_secret_access_key="secret",
                aws_session_token="token",
            )

    def test_bedrock_valid_without_session_token(self):
        """Session token is optional — long-lived IAM keys don't have one."""
        config = LLMConfig(
            provider="bedrock",
            model_name="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            aws_region_name="us-east-1",
            aws_access_key_id="AKID",
            aws_secret_access_key="secret",
        )
        assert config.aws_session_token is None

    def test_anthropic_valid(self):
        config = LLMConfig(provider="anthropic", model_name="claude-sonnet-4-5", anthropic_api_key="sk-test")
        assert config.provider == "anthropic"

    def test_anthropic_missing_key(self):
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            LLMConfig(provider="anthropic", model_name="claude-sonnet-4-5")

    def test_gemini_valid(self):
        config = LLMConfig(provider="gemini", model_name="gemini-2.0-flash", gemini_api_key="gk-test")
        assert config.provider == "gemini"

    def test_gemini_missing_key(self):
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            LLMConfig(provider="gemini", model_name="gemini-2.0-flash")

    def test_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            LLMConfig(provider="openai", model_name="gpt-4")


def _mock_dotenv(values):
    """Return a monkeypatch helper that mocks dotenv_values to return the given dict."""
    def patcher(monkeypatch):
        monkeypatch.setattr("module_identifier.llm.config.dotenv_values", lambda: values)
    return patcher


class TestLLMConfigFromEnv:
    def test_from_env_bedrock(self, monkeypatch):
        _mock_dotenv({
            "AGENT_MODEL": "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "AWS_REGION_NAME": "us-east-1",
            "AWS_ACCESS_KEY_ID": "AKID",
            "AWS_SECRET_ACCESS_KEY": "secret",
            "AWS_SESSION_TOKEN": "token",
        })(monkeypatch)

        config = LLMConfig.from_env()
        assert config.provider == "bedrock"
        assert config.model_name == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
        assert config.aws_region_name == "us-east-1"

    def test_from_env_anthropic(self, monkeypatch):
        _mock_dotenv({
            "AGENT_MODEL": "anthropic/claude-sonnet-4-5",
            "ANTHROPIC_API_KEY": "sk-test",
        })(monkeypatch)

        config = LLMConfig.from_env()
        assert config.provider == "anthropic"
        assert config.model_name == "claude-sonnet-4-5"
        assert config.anthropic_api_key == "sk-test"

    def test_from_env_gemini(self, monkeypatch):
        _mock_dotenv({
            "AGENT_MODEL": "gemini/gemini-2.0-flash",
            "GEMINI_API_KEY": "gk-test",
        })(monkeypatch)

        config = LLMConfig.from_env()
        assert config.provider == "gemini"
        assert config.model_name == "gemini-2.0-flash"

    def test_from_env_missing_agent_model(self, monkeypatch):
        _mock_dotenv({})(monkeypatch)
        with pytest.raises(ValueError, match="AGENT_MODEL is required"):
            LLMConfig.from_env()

    def test_from_env_debug_flag(self, monkeypatch):
        _mock_dotenv({
            "AGENT_MODEL": "anthropic/claude-sonnet-4-5",
            "ANTHROPIC_API_KEY": "sk-test",
            "DEBUG_LOGGING": "true",
        })(monkeypatch)

        config = LLMConfig.from_env()
        assert config.debug is True

    def test_from_env_ignores_shell_env(self, monkeypatch):
        """Env vars in os.environ should NOT be picked up — only .env file."""
        _mock_dotenv({
            "AGENT_MODEL": "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "AWS_REGION_NAME": "us-east-1",
        })(monkeypatch)
        # These are in shell but NOT in .env — should not be used
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "shell-leak")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "shell-leak")

        with pytest.raises(ValueError, match="AWS_ACCESS_KEY_ID"):
            LLMConfig.from_env()


class TestLLMConfigFromEnvFailure:
    """Verify from_env() produces correct error messages with SmartFix-aligned env var names."""

    def test_bedrock_missing_all(self, monkeypatch):
        _mock_dotenv({
            "AGENT_MODEL": "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        })(monkeypatch)
        with pytest.raises(ValueError) as exc_info:
            LLMConfig.from_env()
        msg = str(exc_info.value)
        assert "AWS_REGION_NAME" in msg
        assert "AWS_ACCESS_KEY_ID" in msg
        assert "AWS_SECRET_ACCESS_KEY" in msg

    def test_gemini_missing_key(self, monkeypatch):
        _mock_dotenv({
            "AGENT_MODEL": "gemini/gemini-2.0-flash",
        })(monkeypatch)
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            LLMConfig.from_env()

    def test_anthropic_missing_key(self, monkeypatch):
        _mock_dotenv({
            "AGENT_MODEL": "anthropic/claude-sonnet-4-5",
        })(monkeypatch)
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            LLMConfig.from_env()

    def test_invalid_agent_model_format(self, monkeypatch):
        _mock_dotenv({
            "AGENT_MODEL": "just-a-model-name",
        })(monkeypatch)
        with pytest.raises(ValueError, match="must use provider/model format"):
            LLMConfig.from_env()

    def test_unknown_provider_in_agent_model(self, monkeypatch):
        _mock_dotenv({
            "AGENT_MODEL": "openai/gpt-4",
        })(monkeypatch)
        with pytest.raises(ValueError, match="Unknown provider 'openai'"):
            LLMConfig.from_env()


class TestLLMConfigDefaults:
    def test_debug_default_false(self):
        config = LLMConfig(provider="anthropic", model_name="claude-sonnet-4-5", anthropic_api_key="sk-test")
        assert config.debug is False
