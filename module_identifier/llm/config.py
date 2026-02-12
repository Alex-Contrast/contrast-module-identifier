"""LLM provider configuration loaded from environment variables."""

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for the LLM fallback agent.

    Loaded from environment variables. Provider-specific credentials
    are validated at construction time.
    """

    provider: str

    def __post_init__(self) -> None:
        self._validate()

    # AWS Bedrock
    aws_region: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    bedrock_model_id: Optional[str] = None

    # Anthropic
    anthropic_api_key: Optional[str] = None

    # Azure OpenAI
    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_deployment: Optional[str] = None

    # Google Gemini
    google_api_key: Optional[str] = None
    gemini_model: Optional[str] = None

    # Agent settings
    debug: bool = False

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Load from environment variables.

        Raises ValueError if required credentials for the selected provider are missing.
        """
        load_dotenv()
        provider = os.getenv("LLM_PROVIDER", "bedrock").lower()

        config = cls(
            provider=provider,
            aws_region=os.getenv("AWS_REGION"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            bedrock_model_id=os.getenv("BEDROCK_MODEL_ID"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_openai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            gemini_model=os.getenv("GEMINI_MODEL"),
            debug=os.getenv("DEBUG_LOGGING", "false").lower() == "true",
        )
        return config

    def _validate(self) -> None:
        """Validate that required credentials exist for the selected provider."""
        if self.provider == "bedrock":
            missing = [
                v for v in ("aws_region", "aws_access_key_id", "aws_secret_access_key", "bedrock_model_id")
                if not getattr(self, v)
            ]
            if missing:
                raise ValueError(
                    f"Bedrock requires: {', '.join(v.upper() for v in missing)}"
                )
        elif self.provider == "anthropic":
            if not self.anthropic_api_key:
                raise ValueError("Anthropic requires: ANTHROPIC_API_KEY")
        elif self.provider == "azure":
            missing = [
                v for v in ("azure_openai_endpoint", "azure_openai_api_key", "azure_openai_deployment")
                if not getattr(self, v)
            ]
            if missing:
                raise ValueError(
                    f"Azure OpenAI requires: {', '.join(v.upper() for v in missing)}"
                )
        elif self.provider == "gemini":
            missing = [
                v for v in ("google_api_key", "gemini_model")
                if not getattr(self, v)
            ]
            if missing:
                raise ValueError(
                    f"Gemini requires: {', '.join(v.upper() for v in missing)}"
                )
        else:
            raise ValueError(
                f"Unknown provider: {self.provider}. "
                f"Valid options: bedrock, anthropic, azure, gemini"
            )
