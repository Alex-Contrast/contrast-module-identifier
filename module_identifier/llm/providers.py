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
    from pydantic_ai.providers.bedrock import BedrockProvider

    if config.aws_bearer_token_bedrock:
        provider = BedrockProvider(
            api_key=config.aws_bearer_token_bedrock,
            region_name=config.aws_region,
        )
    else:
        import boto3

        session = boto3.Session(
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
            aws_session_token=config.aws_session_token,
            region_name=config.aws_region,
        )
        client = session.client("bedrock-runtime")
        provider = BedrockProvider(bedrock_client=client)

    return BedrockConverseModel(
        model_name=config.bedrock_model_id,
        provider=provider,
    )


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
