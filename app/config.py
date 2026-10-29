# app/config.py
"""
Loads runtime configuration from environment variables (and .env file).

All sensitive values (secrets, credentials) must come from the environment,
never hardcoded in source code.
"""

import os
from dotenv import load_dotenv

# Load variables from .env if it exists (no error if it doesn't)
load_dotenv()


class Config:
    """Central config object used across the application."""

    # --- Security ---
    # HMAC secret for signing security events.
    # Must be set in .env (or the real environment) before running.
    HMAC_SECRET_KEY: str = os.environ.get("HMAC_SECRET_KEY", "")

    # --- Demo credentials (simulation only) ---
    DEMO_USERNAME: str = os.environ.get("DEMO_USERNAME", "admin")
    DEMO_PASSWORD: str = os.environ.get("DEMO_PASSWORD", "secret123")

    # --- Flask ---
    DEBUG: bool = os.environ.get("FLASK_DEBUG", "1") == "1"

    @classmethod
    def validate(cls) -> None:
        """
        Raise an error at startup if critical config is missing.
        This prevents the application from running with an empty secret.
        """
        if not cls.HMAC_SECRET_KEY:
            raise EnvironmentError(
                "HMAC_SECRET_KEY is not set. "
                "Copy .env.example to .env and set a strong random value."
            )
