"""Output models for LLM fallback agent."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class LLMMatch(BaseModel):
    """Structured output from the LLM agent for a single module resolution."""

    application_id: str = Field(description="Contrast application ID")
    application_name: str = Field(description="Application display name in Contrast")
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description="Confidence level"
    )
    reasoning: str = Field(
        description="Explanation of why this application was selected"
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Additional metadata (language, tags, search terms tried)",
    )
