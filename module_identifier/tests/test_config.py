"""Tests for ContrastConfig credential loading."""

import base64

import pytest

from module_identifier.config import ContrastConfig, _decode_auth_token


class TestDecodeAuthToken:
    def test_valid_token(self):
        token = base64.b64encode(b"user@example.com:svc-key-123").decode()
        username, service_key = _decode_auth_token(token)
        assert username == "user@example.com"
        assert service_key == "svc-key-123"

    def test_colon_in_service_key(self):
        token = base64.b64encode(b"user:key:with:colons").decode()
        username, service_key = _decode_auth_token(token)
        assert username == "user"
        assert service_key == "key:with:colons"

    def test_missing_colon_raises(self):
        token = base64.b64encode(b"nocolon").decode()
        with pytest.raises(ValueError, match="base64"):
            _decode_auth_token(token)


class TestFromEnv:
    _ALL_VARS = [
        "CONTRAST_HOST_NAME", "CONTRAST_API_KEY", "CONTRAST_ORG_ID",
        "CONTRAST_USERNAME", "CONTRAST_SERVICE_KEY", "CONTRAST_AUTH_TOKEN",
    ]
    _BASE_ENV = {
        "CONTRAST_HOST_NAME": "test.contrastsecurity.com",
        "CONTRAST_API_KEY": "api-key",
        "CONTRAST_ORG_ID": "org-123",
    }

    def _clean_env(self, monkeypatch):
        for var in self._ALL_VARS:
            monkeypatch.delenv(var, raising=False)

    def test_explicit_creds(self, monkeypatch):
        self._clean_env(monkeypatch)
        for k, v in self._BASE_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("CONTRAST_USERNAME", "user")
        monkeypatch.setenv("CONTRAST_SERVICE_KEY", "svc")

        config = ContrastConfig.from_env()
        assert config.username == "user"
        assert config.service_key == "svc"

    def test_auth_token(self, monkeypatch):
        self._clean_env(monkeypatch)
        for k, v in self._BASE_ENV.items():
            monkeypatch.setenv(k, v)
        token = base64.b64encode(b"user@example.com:svc-key").decode()
        monkeypatch.setenv("CONTRAST_AUTH_TOKEN", token)

        config = ContrastConfig.from_env()
        assert config.username == "user@example.com"
        assert config.service_key == "svc-key"

    def test_explicit_takes_priority_over_token(self, monkeypatch):
        self._clean_env(monkeypatch)
        for k, v in self._BASE_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("CONTRAST_USERNAME", "explicit-user")
        monkeypatch.setenv("CONTRAST_SERVICE_KEY", "explicit-svc")
        token = base64.b64encode(b"token-user:token-svc").decode()
        monkeypatch.setenv("CONTRAST_AUTH_TOKEN", token)

        config = ContrastConfig.from_env()
        assert config.username == "explicit-user"
        assert config.service_key == "explicit-svc"

    def test_missing_all_auth_raises(self, monkeypatch):
        self._clean_env(monkeypatch)
        for k, v in self._BASE_ENV.items():
            monkeypatch.setenv(k, v)
        with pytest.raises(ValueError, match="CONTRAST_AUTH_TOKEN"):
            ContrastConfig.from_env()

    def test_missing_host_raises(self, monkeypatch):
        self._clean_env(monkeypatch)
        monkeypatch.setenv("CONTRAST_API_KEY", "key")
        monkeypatch.setenv("CONTRAST_ORG_ID", "org")
        monkeypatch.setenv("CONTRAST_USERNAME", "user")
        monkeypatch.setenv("CONTRAST_SERVICE_KEY", "svc")
        with pytest.raises(ValueError, match="CONTRAST_HOST_NAME"):
            ContrastConfig.from_env()
