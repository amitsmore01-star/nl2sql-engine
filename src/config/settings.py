# src/config/settings.py
# V0 - Initial implementation
#
# Single source of truth for all configuration.
# This is the ONLY file that reads YAML files or environment variables.
# No other file in the project may call os.getenv() or read config directly.
#
# Merge order:
#   settings.base.yaml
#   + settings.{ENV}.yaml   (ENV from .env — dev | prod)
#   + .env                  (secrets override everything)
#   = final Settings object

import os
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError, model_validator
from pydantic import ConfigDict

# ---------------------------------------------------------------------------
# Load .env once at import time — secrets populate os.environ
# ---------------------------------------------------------------------------
load_dotenv()


# ---------------------------------------------------------------------------
# Sub-models — one per YAML section
# ---------------------------------------------------------------------------

class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    schema_dir: str


class ApiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    port: int
    prefix: str


class LLMSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    max_tokens: int
    timeout_seconds: int
    retry_max: int
    retry_backoff_seconds: int
    step1_token_target: int
    step2_token_target: int


class SQLSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_top_rows: int
    max_nl_query_length: int


class LoggingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str
    rotation: str
    log_dir: str
    log_archive_dir: str


# ---------------------------------------------------------------------------
# Root Settings model
# ---------------------------------------------------------------------------

class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # YAML sections
    app: AppSettings
    api: ApiSettings
    llm: LLMSettings
    sql: SQLSettings
    logging: LoggingSettings

    # Secrets from .env — flat on root
    api_key: str
    env: Literal["dev", "prod"]

    # Optional secrets — present only when provider needs them
    openai_api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_deployment_name: str | None = None
    azure_openai_api_version: str | None = None
    anthropic_api_key: str | None = None

    @model_validator(mode="after")
    def llm_provider_env_override(self) -> "Settings":
        """
        If LLM_PROVIDER is set in .env, it overrides whatever YAML says.
        This is the .env-wins rule from the architecture document.
        """
        env_provider = os.environ.get("LLM_PROVIDER")
        if env_provider:
            self.llm.provider = env_provider
        return self


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict:
    """Load a YAML file and return as dict. Returns empty dict if file missing."""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merge override into base.
    - Keys in override that exist in base: override value wins.
    - Keys in override NOT in base: added as-is (caught later by Pydantic extra=forbid).
    - Nested dicts are merged recursively.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# ---------------------------------------------------------------------------
# Public loader — called once at startup
# ---------------------------------------------------------------------------

def load_settings(config_dir: str | Path | None = None) -> Settings:
    """
    Load, merge, and validate all configuration.

    Args:
        config_dir: Path to the config/ directory. Defaults to
                    <project_root>/config relative to this file.

    Returns:
        Validated Settings object.

    Raises:
        ValueError: If ENV is missing, unknown, or a required secret is absent.
        ValueError: If merged config contains unknown keys or wrong types.
    """
    # Resolve config directory
    if config_dir is None:
        # src/config/settings.py → up two levels → project root → config/
        config_dir = Path(__file__).parent.parent.parent / "config"
    config_dir = Path(config_dir)

    # --- 1. Read ENV ---
    env = os.environ.get("ENV", "").strip()
    if not env:
        raise ValueError(
            "ENV environment variable is required but not set. "
            "Set ENV=dev or ENV=prod in your .env file."
        )
    if env not in ("dev", "prod"):
        raise ValueError(
            f"ENV='{env}' is not valid. Must be 'dev' or 'prod'."
        )

    # --- 2. Load and merge YAML layers ---
    base = _load_yaml(config_dir / "settings.base.yaml")
    override = _load_yaml(config_dir / f"settings.{env}.yaml")
    merged = _deep_merge(base, override)

    # --- 3. Inject secrets from environment ---
    api_key = os.environ.get("API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "API_KEY environment variable is required but not set. "
            "Add API_KEY=your-key to your .env file."
        )

    merged["api_key"] = api_key
    merged["env"] = env

    # Optional secrets — only injected if present in environment
    _optional_secrets = [
        "openai_api_key",
        "azure_openai_endpoint",
        "azure_openai_api_key",
        "azure_openai_deployment_name",
        "azure_openai_api_version",
        "anthropic_api_key",
        "log_dir",
        "log_archive_dir",
    ]
    for secret in _optional_secrets:
        env_val = os.environ.get(secret.upper())
        if env_val is not None:
            merged[secret] = env_val

    # --- 4. Validate via Pydantic (extra=forbid catches unknown keys) ---
    try:
        settings = Settings(**merged)
    except ValidationError as exc:
        raise ValueError(
            f"Configuration validation failed:\n{exc}"
        ) from exc

    return settings
