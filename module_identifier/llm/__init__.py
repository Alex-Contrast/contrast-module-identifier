"""LLM fallback agent for resolving modules the deterministic scorer couldn't match."""

from .agent import resolve_modules as llm_resolve_modules
from .config import LLMConfig
from .models import LLMMatch

__all__ = [
    "llm_resolve_modules",
    "LLMConfig",
    "LLMMatch",
]
