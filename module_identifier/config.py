"""Contrast Security credentials from environment."""

import base64
import os
from dataclasses import dataclass


def _decode_auth_token(token: str) -> tuple[str, str]:
    """Decode base64(username:service_key) into (username, service_key)."""
    decoded = base64.b64decode(token).decode("utf-8")
    username, _, service_key = decoded.partition(":")
    if not username or not service_key:
        raise ValueError("CONTRAST_AUTH_TOKEN must be base64(username:service_key)")
    return username, service_key


@dataclass(frozen=True)
class ContrastConfig:
    host_name: str
    api_key: str
    service_key: str
    username: str
    org_id: str

    @classmethod
    def from_env(cls) -> "ContrastConfig":
        """Load from environment variables.

        Accepts either:
          - CONTRAST_USERNAME + CONTRAST_SERVICE_KEY (explicit)
          - CONTRAST_AUTH_TOKEN (base64 of username:service_key, set by onboarding)

        Always required: CONTRAST_HOST_NAME, CONTRAST_API_KEY, CONTRAST_ORG_ID
        """
        host_name = os.getenv("CONTRAST_HOST_NAME", "")
        api_key = os.getenv("CONTRAST_API_KEY", "")
        org_id = os.getenv("CONTRAST_ORG_ID", "")
        username = os.getenv("CONTRAST_USERNAME", "")
        service_key = os.getenv("CONTRAST_SERVICE_KEY", "")
        auth_token = os.getenv("CONTRAST_AUTH_TOKEN", "")

        # Derive username/service_key from auth token if not provided directly
        if auth_token and (not username or not service_key):
            username, service_key = _decode_auth_token(auth_token)

        missing = []
        if not host_name:
            missing.append("CONTRAST_HOST_NAME")
        if not api_key:
            missing.append("CONTRAST_API_KEY")
        if not org_id:
            missing.append("CONTRAST_ORG_ID")
        if not username or not service_key:
            missing.append("CONTRAST_AUTH_TOKEN (or CONTRAST_USERNAME + CONTRAST_SERVICE_KEY)")
        if missing:
            raise ValueError(f"Missing required env vars: {', '.join(missing)}")

        return cls(
            host_name=host_name,
            api_key=api_key,
            service_key=service_key,
            username=username,
            org_id=org_id,
        )

    def __repr__(self) -> str:
        return (
            f"ContrastConfig(host_name={self.host_name!r}, "
            f"api_key='***', service_key='***', "
            f"username={self.username!r}, org_id={self.org_id!r})"
        )

    def as_env(self) -> dict[str, str]:
        """Return as env dict for passing to subprocess."""
        return {
            "CONTRAST_HOST_NAME": self.host_name,
            "CONTRAST_API_KEY": self.api_key,
            "CONTRAST_SERVICE_KEY": self.service_key,
            "CONTRAST_USERNAME": self.username,
            "CONTRAST_ORG_ID": self.org_id,
        }
