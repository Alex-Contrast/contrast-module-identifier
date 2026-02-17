"""Tests for LLM output models."""

from module_identifier.llm.models import LLMMatch


class TestLLMMatch:
    def test_creation(self):
        match = LLMMatch(
            application_id="abc-123",
            application_name="order-api",
            confidence="HIGH",
            reasoning="Exact match found via search",
        )
        assert match.application_id == "abc-123"
        assert match.application_name == "order-api"
        assert match.confidence == "HIGH"
        assert match.metadata == {}

    def test_with_metadata(self):
        match = LLMMatch(
            application_id="abc-123",
            application_name="order-api",
            confidence="MEDIUM",
            reasoning="Matched via source code analysis",
            metadata={"language": "Java", "search_terms": ["order", "ordering"]},
        )
        assert match.metadata["language"] == "Java"

    def test_not_found(self):
        match = LLMMatch(
            application_id="NOT_FOUND",
            application_name="NOT_FOUND",
            confidence="LOW",
            reasoning="No Contrast app corresponds to this internal utility module",
        )
        assert match.application_id == "NOT_FOUND"

    def test_serialization(self):
        match = LLMMatch(
            application_id="abc-123",
            application_name="order-api",
            confidence="HIGH",
            reasoning="Exact match",
        )
        d = match.model_dump()
        assert d["application_id"] == "abc-123"
        assert d["confidence"] == "HIGH"
        assert "metadata" in d

    def test_from_dict(self):
        data = {
            "application_id": "xyz-789",
            "application_name": "billing-svc",
            "confidence": "LOW",
            "reasoning": "Weak match",
            "metadata": {"language": "Node"},
        }
        match = LLMMatch(**data)
        assert match.application_name == "billing-svc"
