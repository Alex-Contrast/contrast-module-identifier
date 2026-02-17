"""Tests for mcp_contrast parsing and server param construction."""

import json
from dataclasses import dataclass
from types import SimpleNamespace

from module_identifier.config import ContrastConfig
from module_identifier.mcp_contrast import _parse_candidates, _server_params


# --- Helpers ---

def _fake_config() -> ContrastConfig:
    return ContrastConfig(
        host_name="test.contrastsecurity.com",
        api_key="key",
        service_key="svc",
        username="user",
        org_id="org-123",
    )


def _mcp_result(text: str):
    """Simulate an MCP CallToolResult with a single text content block."""
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[block])


def _mcp_result_blocks(blocks: list):
    """Simulate an MCP CallToolResult with multiple content blocks."""
    return SimpleNamespace(content=blocks)


# --- _parse_candidates ---


class TestParseCandidates:
    def test_real_response_shape(self):
        """Matches the actual shape returned by contrast/mcp-contrast."""
        data = [
            {
                "name": "webgoat-server",
                "status": "offline",
                "appID": "adc11a30-3a0b-4866-9524-80eb5b61d014",
                "lastSeenAt": "2025-12-09T12:53:00-05:00",
                "language": "Java",
                "metadata": [],
                "tags": [],
                "technologies": ["undertow", "J2EE", "Spring MVC"],
            },
            {
                "name": "juice-shop",
                "status": "offline",
                "appID": "bf180fef-33cb-4bcb-a207-926fa4d5dde8",
                "lastSeenAt": "2025-12-10T10:22:00-05:00",
                "language": "Node",
                "metadata": [],
                "tags": [],
                "technologies": [],
            },
        ]
        result = _mcp_result(json.dumps(data))
        candidates = _parse_candidates(result)

        assert len(candidates) == 2
        assert candidates[0].app_id == "adc11a30-3a0b-4866-9524-80eb5b61d014"
        assert candidates[0].name == "webgoat-server"
        assert candidates[0].language == "Java"
        assert candidates[1].app_id == "bf180fef-33cb-4bcb-a207-926fa4d5dde8"
        assert candidates[1].name == "juice-shop"
        assert candidates[1].language == "Node"

    def test_items_null_treated_as_single_object(self):
        """{"items": null} should not crash — treated as single object, skipped."""
        data = {"items": None}
        result = _mcp_result(json.dumps(data))
        assert _parse_candidates(result) == []

    def test_items_wrapped_response(self):
        """mcp-contrast 1.0.0+ wraps results in {"items": [...]}."""
        data = {
            "items": [
                {
                    "name": "webgoat-server",
                    "appID": "adc11a30-3a0b-4866-9524-80eb5b61d014",
                    "language": "Java",
                },
                {
                    "name": "juice-shop",
                    "appID": "bf180fef-33cb-4bcb-a207-926fa4d5dde8",
                    "language": "Node",
                },
            ]
        }
        result = _mcp_result(json.dumps(data))
        candidates = _parse_candidates(result)

        assert len(candidates) == 2
        assert candidates[0].app_id == "adc11a30-3a0b-4866-9524-80eb5b61d014"
        assert candidates[0].name == "webgoat-server"
        assert candidates[1].name == "juice-shop"

    def test_single_app_response(self):
        data = {
            "name": "my-app",
            "appID": "abc-123",
            "language": "Python",
        }
        result = _mcp_result(json.dumps(data))
        candidates = _parse_candidates(result)

        assert len(candidates) == 1
        assert candidates[0].app_id == "abc-123"
        assert candidates[0].name == "my-app"

    def test_empty_list(self):
        result = _mcp_result("[]")
        assert _parse_candidates(result) == []

    def test_missing_name_skipped(self):
        data = [{"appID": "abc-123", "language": "Java"}]
        result = _mcp_result(json.dumps(data))
        assert _parse_candidates(result) == []

    def test_missing_app_id_skipped(self):
        data = [{"name": "my-app", "language": "Java"}]
        result = _mcp_result(json.dumps(data))
        assert _parse_candidates(result) == []

    def test_missing_language_defaults_empty(self):
        data = [{"name": "my-app", "appID": "abc-123"}]
        result = _mcp_result(json.dumps(data))
        candidates = _parse_candidates(result)
        assert len(candidates) == 1
        assert candidates[0].language == ""

    def test_malformed_json(self):
        result = _mcp_result("not json at all")
        assert _parse_candidates(result) == []

    def test_non_text_blocks_ignored(self):
        blocks = [
            SimpleNamespace(type="image", text="irrelevant"),
            SimpleNamespace(type="text", text=json.dumps([
                {"name": "app", "appID": "id1", "language": "Go"}
            ])),
        ]
        result = _mcp_result_blocks(blocks)
        candidates = _parse_candidates(result)
        assert len(candidates) == 1

    def test_non_dict_entries_skipped(self):
        data = ["just a string", 42, {"name": "real-app", "appID": "id1", "language": "Java"}]
        result = _mcp_result(json.dumps(data))
        candidates = _parse_candidates(result)
        assert len(candidates) == 1
        assert candidates[0].name == "real-app"


# --- _server_params ---


class TestServerParams:
    def test_jar_path_when_file_exists(self, tmp_path):
        jar = tmp_path / "mcp.jar"
        jar.touch()
        cfg = _fake_config()
        params = _server_params(cfg, jar_path=str(jar))

        assert params.command == "java"
        assert "-jar" in params.args
        assert str(jar) in params.args

    def test_docker_fallback_when_no_jar(self):
        cfg = _fake_config()
        params = _server_params(cfg, jar_path="/nonexistent/path.jar")

        assert params.command == "docker"
        assert "contrast/mcp-contrast:latest" in params.args

    def test_env_includes_contrast_creds(self, tmp_path):
        jar = tmp_path / "mcp.jar"
        jar.touch()
        cfg = _fake_config()
        params = _server_params(cfg, jar_path=str(jar))

        assert params.env["CONTRAST_HOST_NAME"] == "test.contrastsecurity.com"
        assert params.env["CONTRAST_API_KEY"] == "key"
        assert params.env["CONTRAST_ORG_ID"] == "org-123"
