"""LLM provider factory for multi-provider support."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai.models import Model

from .config import LLMConfig

if TYPE_CHECKING:
    from ..config import ContrastConfig


def get_model(config: LLMConfig, contrast_config: ContrastConfig | None = None) -> Model:
    """Create an LLM model instance for the configured provider.

    Uses lazy imports so provider-specific packages are only required
    when that provider is selected.

    Args:
        config: LLM configuration (provider, model name, credentials).
        contrast_config: Contrast credentials, required when provider is "contrast".
    """
    provider = config.provider

    if provider == "contrast":
        if contrast_config is None:
            raise ValueError("contrast provider requires ContrastConfig")
        return _create_contrast_model(config, contrast_config)
    elif provider == "bedrock":
        return _create_bedrock_model(config)
    elif provider == "anthropic":
        return _create_anthropic_model(config)
    elif provider == "gemini":
        return _create_gemini_model(config)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def _create_bedrock_model(config: LLMConfig) -> Model:
    from pydantic_ai.models.bedrock import BedrockConverseModel
    from pydantic_ai.providers.bedrock import BedrockProvider

    if config.aws_bearer_token_bedrock:
        provider = BedrockProvider(
            api_key=config.aws_bearer_token_bedrock,
            region_name=config.aws_region_name,
        )
    else:
        import boto3

        session = boto3.Session(
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
            aws_session_token=config.aws_session_token,
            region_name=config.aws_region_name,
        )
        client = session.client("bedrock-runtime")
        provider = BedrockProvider(bedrock_client=client)

    return BedrockConverseModel(
        model_name=config.model_name,
        provider=provider,
    )


def _create_anthropic_model(config: LLMConfig) -> Model:
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    return AnthropicModel(
        model_name=config.model_name,
        provider=AnthropicProvider(api_key=config.anthropic_api_key),
    )


def _create_gemini_model(config: LLMConfig) -> Model:
    from pydantic_ai.models.gemini import GeminiModel
    from pydantic_ai.providers.google_gla import GoogleGLAProvider

    return GeminiModel(
        model_name=config.model_name,
        provider=GoogleGLAProvider(api_key=config.gemini_api_key),
    )


def _create_contrast_model(config: LLMConfig, contrast_config: ContrastConfig) -> Model:
    import base64

    from anthropic import AsyncAnthropic
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    auth_token = base64.b64encode(
        f"{contrast_config.username}:{contrast_config.service_key}".encode()
    ).decode()

    host = contrast_config.host_name.rstrip("/")
    base_url = f"https://{host}/api/llm-proxy/v2/anthropic"

    client = AsyncAnthropic(
        api_key=contrast_config.api_key,
        base_url=base_url,
        default_headers={
            "API-Key": contrast_config.api_key,
            "Authorization": auth_token,
        },
    )
    provider = AnthropicProvider(anthropic_client=client)
    return AnthropicModel(model_name=config.model_name, provider=provider)
