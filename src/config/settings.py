# src/config/settings.py
# V0 - Initial implementation
# V1 - Replaced api_key with client_api_key + foundry_api_key (Story 2.4)
#      Added prod-only validator for missing keys
#      Fixed log_dir / log_archive_dir to inject into merged["logging"] section
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
from typing import Literal, Optional

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
    env: Literal["dev", "prod"]

    # Auth keys — both optional at field level.
    # model_validator below enforces both are present in prod.
    client_api_key: Optional[str] = None
    foundry_api_key: Optional[str] = None

    # Optional LLM secrets — present only when provider needs them
    openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_deployment_name: Optional[str] = None
    azure_openai_api_version: Optional[str] = None
    anthropic_api_key: Optional[str] = None

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

    @model_validator(mode="after")
    def require_keys_in_prod(self) -> "Settings":
        """
        In prod, both CLIENT_API_KEY and FOUNDRY_API_KEY must be set.
        In dev, missing keys are allowed — requests will just return 401.
        """
        if self.env == "prod":
            missing = []
            if not self.client_api_key:
                missing.append("CLIENT_API_KEY")
            if not self.foundry_api_key:
                missing.append("FOUNDRY_API_KEY")
            if missing:
                raise ValueError(
                    f"Missing required environment variable(s) in prod: "
                    f"{', '.join(missing)}. Add them to your .env file."
                )
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
        ValueError: If ENV is missing or unknown.
        ValueError: If prod and CLIENT_API_KEY or FOUNDRY_API_KEY is missing.
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

    # --- 3. Inject ENV ---
    merged["env"] = env

    # --- 4. Inject auth keys from environment (optional at this stage) ---
    client_api_key = os.environ.get("CLIENT_API_KEY", "").strip() or None
    foundry_api_key = os.environ.get("FOUNDRY_API_KEY", "").strip() or None
    merged["client_api_key"] = client_api_key
    merged["foundry_api_key"] = foundry_api_key

    # --- 5. Inject logging overrides into the nested logging section ---
    # LOG_DIR and LOG_ARCHIVE_DIR override the YAML logging: section values.
    # They are injected directly into merged["logging"] so Pydantic sees them
    # as part of LoggingSettings, not as unknown flat root keys.
    if "logging" not in merged:
        merged["logging"] = {}
    log_dir_env = os.environ.get("LOG_DIR")
    log_archive_dir_env = os.environ.get("LOG_ARCHIVE_DIR")
    if log_dir_env is not None:
        merged["logging"]["log_dir"] = log_dir_env
    if log_archive_dir_env is not None:
        merged["logging"]["log_archive_dir"] = log_archive_dir_env

    # --- 6. Inject optional LLM secrets from environment ---
    _optional_llm_secrets = [
        "openai_api_key",
        "azure_openai_endpoint",
        "azure_openai_api_key",
        "azure_openai_deployment_name",
        "azure_openai_api_version",
        "anthropic_api_key",
    ]
    for secret in _optional_llm_secrets:
        env_val = os.environ.get(secret.upper())
        if env_val is not None:
            merged[secret] = env_val

    # --- 7. Validate via Pydantic (extra=forbid catches unknown keys) ---
    try:
        settings = Settings(**merged)
    except ValidationError as exc:
        raise ValueError(
            f"Configuration validation failed:\n{exc}"
        ) from exc

    return settings
