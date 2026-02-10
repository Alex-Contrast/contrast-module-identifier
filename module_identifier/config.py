"""Contrast Security credentials from environment."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ContrastConfig:
    host_name: str
    api_key: str
    service_key: str
    username: str
    org_id: str

    @classmethod
    def from_env(cls) -> "ContrastConfig":
        """Load from environment variables. Raises ValueError if any are missing."""
        missing = [
            var for var in (
                "CONTRAST_HOST_NAME",
                "CONTRAST_API_KEY",
                "CONTRAST_SERVICE_KEY",
                "CONTRAST_USERNAME",
                "CONTRAST_ORG_ID",
            )
            if not os.getenv(var)
        ]
        if missing:
            raise ValueError(f"Missing required env vars: {', '.join(missing)}")

        return cls(
            host_name=os.environ["CONTRAST_HOST_NAME"],
            api_key=os.environ["CONTRAST_API_KEY"],
            service_key=os.environ["CONTRAST_SERVICE_KEY"],
            username=os.environ["CONTRAST_USERNAME"],
            org_id=os.environ["CONTRAST_ORG_ID"],
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
