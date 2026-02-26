"""LLM provider configuration loaded from environment variables."""

from dataclasses import dataclass
from typing import Optional

from dotenv import dotenv_values

VALID_PROVIDERS = ("contrast", "bedrock", "anthropic", "gemini")

DEFAULT_CONTRAST_MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for the LLM fallback agent.

    Loaded from environment variables. Provider-specific credentials
    are validated at construction time.

    AGENT_MODEL uses provider-prefixed format matching SmartFix/LiteLLM:
        bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0
        anthropic/claude-sonnet-4-5
        gemini/gemini-2.0-flash

    When AGENT_MODEL is unset, defaults to the contrast provider with
    us.anthropic.claude-sonnet-4-5-20250929-v1:0 routed through the Contrast LLM proxy.
    """

    provider: str
    model_name: str = ""

    def __post_init__(self) -> None:
        self._validate()

    def __repr__(self) -> str:
        return f"LLMConfig(provider={self.provider!r}, model_name={self.model_name!r}, debug={self.debug})"

    # AWS Bedrock
    aws_region_name: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_session_token: Optional[str] = None
    aws_bearer_token_bedrock: Optional[str] = None

    # Anthropic
    anthropic_api_key: Optional[str] = None

    # Google Gemini
    gemini_api_key: Optional[str] = None

    # Agent settings
    debug: bool = False

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Load from environment variables.

        Provider is inferred from the AGENT_MODEL prefix (e.g. "bedrock/model-id").
        Raises ValueError if AGENT_MODEL is missing or credentials are incomplete.

        Uses dotenv_values() instead of os.environ so that only the .env file
        is read — shell env vars are deliberately ignored to prevent credential
        leakage from the host environment.
        """
        env = dotenv_values()

        agent_model = env.get("AGENT_MODEL", "")
        if not agent_model:
            # Default to Contrast LLM — no extra credentials needed
            provider, model_name = "contrast", DEFAULT_CONTRAST_MODEL
        else:
            provider, model_name = _parse_agent_model(agent_model)

        config = cls(
            provider=provider,
            model_name=model_name,
            aws_region_name=env.get("AWS_REGION_NAME"),
            aws_access_key_id=env.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=env.get("AWS_SECRET_ACCESS_KEY"),
            aws_session_token=env.get("AWS_SESSION_TOKEN"),
            aws_bearer_token_bedrock=env.get("AWS_BEARER_TOKEN_BEDROCK"),
            anthropic_api_key=env.get("ANTHROPIC_API_KEY"),
            gemini_api_key=env.get("GEMINI_API_KEY"),
            debug=env.get("DEBUG_LOGGING", "false").lower() == "true",
        )
        return config

    def _validate(self) -> None:
        """Validate that required credentials exist for the selected provider."""
        if not self.model_name:
            raise ValueError("model_name is required")
        if self.provider == "contrast":
            # Auth comes from ContrastConfig, not LLMConfig — nothing to validate here
            return
        elif self.provider == "bedrock":
            # Region is always required regardless of auth method
            if not self.aws_region_name:
                raise ValueError("Bedrock requires: AWS_REGION_NAME")
            # Need either bearer token OR IAM keys
            if not self.aws_bearer_token_bedrock:
                iam_missing = [
                    v for v in ("aws_access_key_id", "aws_secret_access_key")
                    if not getattr(self, v)
                ]
                if iam_missing:
                    raise ValueError(
                        f"Bedrock requires: {', '.join(v.upper() for v in iam_missing)}"
                    )
        elif self.provider == "anthropic":
            if not self.anthropic_api_key:
                raise ValueError("Anthropic requires: ANTHROPIC_API_KEY")
        elif self.provider == "gemini":
            if not self.gemini_api_key:
                raise ValueError("Gemini requires: GEMINI_API_KEY")
        else:
            raise ValueError(
                f"Unknown provider: {self.provider}. "
                f"Valid options: {', '.join(VALID_PROVIDERS)}"
            )


def _parse_agent_model(agent_model: str) -> tuple[str, str]:
    """Parse 'provider/model-name' into (provider, model_name).

    Raises ValueError if format is invalid or provider is unknown.
    """
    if "/" not in agent_model:
        raise ValueError(
            f"AGENT_MODEL must use provider/model format, got: {agent_model!r}. "
            f"Valid providers: {', '.join(VALID_PROVIDERS)}"
        )

    provider, _, model_name = agent_model.partition("/")
    provider = provider.strip().lower()
    model_name = model_name.strip()

    if provider not in VALID_PROVIDERS:
        raise ValueError(
            f"Unknown provider '{provider}' in AGENT_MODEL={agent_model!r}. "
            f"Valid providers: {', '.join(VALID_PROVIDERS)}"
        )

    if not model_name:
        raise ValueError(
            f"AGENT_MODEL must include a model name after the provider prefix, "
            f"got: {agent_model!r}"
        )

    return provider, model_name
