"""LLM provider factory for multi-provider support."""

from pydantic_ai.models import Model

from .config import LLMConfig


def get_model(config: LLMConfig) -> Model:
    """Create an LLM model instance for the configured provider.

    Uses lazy imports so provider-specific packages are only required
    when that provider is selected.
    """
    provider = config.provider

    if provider == "bedrock":
        return _create_bedrock_model(config)
    elif provider == "anthropic":
        return _create_anthropic_model(config)
    elif provider == "azure":
        return _create_azure_model(config)
    elif provider == "gemini":
        return _create_gemini_model(config)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def _create_bedrock_model(config: LLMConfig) -> Model:
    from pydantic_ai.models.bedrock import BedrockConverseModel
    import os

    if config.aws_access_key_id:
        os.environ["AWS_ACCESS_KEY_ID"] = config.aws_access_key_id
    if config.aws_secret_access_key:
        os.environ["AWS_SECRET_ACCESS_KEY"] = config.aws_secret_access_key
    if config.aws_region:
        os.environ["AWS_DEFAULT_REGION"] = config.aws_region

    return BedrockConverseModel(model_name=config.bedrock_model_id)


def _create_anthropic_model(config: LLMConfig) -> Model:
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    return AnthropicModel(
        model_name="claude-sonnet-4-5",
        provider=AnthropicProvider(api_key=config.anthropic_api_key),
    )


def _create_azure_model(config: LLMConfig) -> Model:
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider

    return OpenAIModel(
        model_name=config.azure_openai_deployment,
        provider=OpenAIProvider(
            base_url=config.azure_openai_endpoint,
            api_key=config.azure_openai_api_key,
        ),
    )


def _create_gemini_model(config: LLMConfig) -> Model:
    from pydantic_ai.models.gemini import GeminiModel
    from pydantic_ai.providers.google_gla import GoogleGLAProvider

    return GeminiModel(
        model_name=config.gemini_model,
        provider=GoogleGLAProvider(api_key=config.google_api_key),
    )
