# tests/config/test_settings.py
# V0 - Initial implementation
# V1 - Updated CLIENT_API_KEY + FOUNDRY_API_KEY (Story 2.4)
# V2 - Replaced step1_token_target + step2_token_target with nl_to_ir_strategy
#      and prompt_example_set throughout (Story 3.6, architecture v1.6)
#      Added Scenario P — prompts.yaml loading tests
#
# Tests for src/config/settings.py
# All 9 agreed scenarios covered.
# Uses monkeypatch to control environment variables — no real .env required.

import pytest
from pathlib import Path

from src.config import settings
from src.config.settings import load_settings, _deep_merge

# ---------------------------------------------------------------------------
# Path to the real config/ directory (used by most tests)
# ---------------------------------------------------------------------------
REAL_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


# ---------------------------------------------------------------------------
# Shared env helpers
# ---------------------------------------------------------------------------
BASE_ENV = {
    "ENV": "dev",
    "API_KEY": "test-api-key",
}

PROD_ENV = {
    "ENV": "prod",
    "API_KEY": "test-api-key",
}


def _set_env(monkeypatch, env_dict: dict):
    """Helper — sets all keys in env_dict and clears LLM_PROVIDER."""
    for k, v in env_dict.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)


# ===========================================================================
# Scenario 1 — Base config loads correctly
# ===========================================================================
class TestBaseConfigLoads:

    def test_app_name(self, monkeypatch):
        """app.name is nl2sql-engine as declared in base YAML."""
        _set_env(monkeypatch, BASE_ENV)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.app.name == "nl2sql-engine"

    def test_app_version(self, monkeypatch):
        """app.version is 1.0 as declared in base YAML."""
        _set_env(monkeypatch, BASE_ENV)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.app.version == "1.0"

    def test_app_schema_dir(self, monkeypatch):
        """app.schema_dir is schemas as declared in base YAML."""
        _set_env(monkeypatch, BASE_ENV)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.app.schema_dir == "schemas"

    def test_api_port(self, monkeypatch):
        """api.port is 8000 as declared in base YAML."""
        _set_env(monkeypatch, BASE_ENV)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.api.port == 8000

    def test_api_prefix(self, monkeypatch):
        """api.prefix is /v1 as declared in base YAML."""
        _set_env(monkeypatch, BASE_ENV)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.api.prefix == "/v1"

    def test_sql_default_top_rows(self, monkeypatch):
        """sql.default_top_rows is 0 as declared in base YAML."""
        _set_env(monkeypatch, BASE_ENV)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.sql.default_top_rows == 0

    def test_sql_max_nl_query_length(self, monkeypatch):
        """sql.max_nl_query_length is 0 as declared in base YAML."""
        _set_env(monkeypatch, BASE_ENV)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.sql.max_nl_query_length == 0

    def test_llm_max_tokens(self, monkeypatch):
        """llm.max_tokens is 1000 as declared in base YAML."""
        _set_env(monkeypatch, BASE_ENV)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.llm.max_tokens == 1000

    def test_llm_retry_max(self, monkeypatch):
        """llm.retry_max is 3 as declared in base YAML."""
        _set_env(monkeypatch, BASE_ENV)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.llm.retry_max == 3


# ===========================================================================
# Scenario 2 — Dev overrides apply
# ===========================================================================
class TestDevOverrides:

    def test_logging_level_is_debug_in_dev(self, monkeypatch):
        """settings.dev.yaml sets logging.level=DEBUG — overrides base INFO."""
        _set_env(monkeypatch, BASE_ENV)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.logging.level == "DEBUG"

    def test_llm_provider_is_mock_in_dev(self, monkeypatch):
        """settings.dev.yaml sets llm.provider=mock."""
        _set_env(monkeypatch, BASE_ENV)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.llm.provider == "mock"

    def test_base_values_not_in_dev_yaml_unchanged(self, monkeypatch):
        """Base keys not touched by dev override retain their base values."""
        _set_env(monkeypatch, BASE_ENV)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.sql.default_top_rows == 0
        assert settings.app.name == "nl2sql-engine"
        assert settings.llm.max_tokens == 1000


# ===========================================================================
# Scenario 3 — Prod overrides apply
# ===========================================================================
class TestProdOverrides:

    def test_llm_provider_is_azure_openai_in_prod(self, monkeypatch):
        """settings.prod.yaml sets llm.provider=azure_openai."""
        _set_env(monkeypatch, PROD_ENV)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.llm.provider == "azure_openai"

    def test_logging_level_is_info_in_prod(self, monkeypatch):
        """settings.prod.yaml keeps logging.level=INFO."""
        _set_env(monkeypatch, PROD_ENV)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.logging.level == "INFO"

    def test_base_values_unchanged_in_prod(self, monkeypatch):
        """Base keys not overridden by prod retain their base values."""
        _set_env(monkeypatch, PROD_ENV)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.sql.default_top_rows == 0
        assert settings.app.name == "nl2sql-engine"


# ===========================================================================
# Scenario 4 — .env secrets load
# ===========================================================================
class TestEnvSecretsLoad:

    def test_api_key_loaded(self, monkeypatch):
        """API_KEY from environment is available on settings.api_key."""
        _set_env(monkeypatch, BASE_ENV)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.client_api_key  == "your-client-api-key-here"
        assert settings.foundry_api_key  == "your-foundry-api-key-here"

    def test_optional_openai_key_loaded(self, monkeypatch):
        """OPENAI_API_KEY from environment is available on settings.openai_api_key."""
        _set_env(monkeypatch, BASE_ENV)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.openai_api_key == "sk-test-openai"

    def test_optional_anthropic_key_loaded(self, monkeypatch):
        """ANTHROPIC_API_KEY from environment is available on settings.anthropic_api_key."""
        _set_env(monkeypatch, BASE_ENV)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.anthropic_api_key == "sk-ant-test"

    def test_optional_secret_absent_is_none(self, monkeypatch):
        """Optional secrets not in environment are None — not an error."""
        _set_env(monkeypatch, BASE_ENV)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.openai_api_key is None
        assert settings.anthropic_api_key is None

    def test_log_dir_default(self, monkeypatch):
        """log_dir defaults to 'logs' when not set in environment."""
        _set_env(monkeypatch, BASE_ENV)
        monkeypatch.delenv("LOG_DIR", raising=False)
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.logging.log_dir == "logs"


# ===========================================================================
# Scenario 5 — .env LLM_PROVIDER overrides YAML
# ===========================================================================
class TestEnvOverridesYaml:

    def test_llm_provider_env_wins_over_dev_yaml(self, monkeypatch):
        """LLM_PROVIDER=openai in environment overrides llm.provider=mock from dev YAML."""
        _set_env(monkeypatch, BASE_ENV)
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.llm.provider == "openai"

    def test_llm_provider_env_wins_over_prod_yaml(self, monkeypatch):
        """LLM_PROVIDER=anthropic in environment overrides llm.provider=azure_openai from prod YAML."""
        _set_env(monkeypatch, PROD_ENV)
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.llm.provider == "anthropic"

    def test_llm_provider_env_mock_wins_over_prod(self, monkeypatch):
        """LLM_PROVIDER=mock in environment overrides prod's azure_openai."""
        _set_env(monkeypatch, PROD_ENV)
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        settings = load_settings(REAL_CONFIG_DIR)
        assert settings.llm.provider == "mock"


# ===========================================================================
# Scenario 6 — Missing required secret raises clear error
# ===========================================================================
class TestMissingRequiredSecret:

    def test_missing_api_key_in_dev_env_no_error(self, monkeypatch):
        """Absent API_KEY in dev environment does not raise an error."""
        monkeypatch.setenv("ENV", "dev")
        monkeypatch.delenv("CLIENT_API_KEY", raising=False)
        monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
        monkeypatch.delenv("LLM_PROVIDER", raising=False)

        settings = load_settings(REAL_CONFIG_DIR)
        assert settings is not None

    def test_missing_env_var_raises_value_error(self, monkeypatch):
        """Absent ENV raises ValueError with ENV mentioned in message."""
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.setenv("CLIENT_API_KEY",  "test-api-key")
        monkeypatch.setenv("FOUNDRY_API_KEY", "test-api-key")
        monkeypatch.delenv("LLM_PROVIDER", raising=False)

        with pytest.raises(ValueError, match="ENV"):
            load_settings(REAL_CONFIG_DIR)

    def test_error_message_is_descriptive_for_api_key(self, monkeypatch):
        """Error message for missing CLIENT_API_KEY tells user what to do."""
        monkeypatch.setenv("ENV", "prod")
        monkeypatch.delenv("CLIENT_API_KEY", raising=False)
        monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
        monkeypatch.delenv("LLM_PROVIDER", raising=False)

        with pytest.raises(ValueError, match=".env"):
            load_settings(REAL_CONFIG_DIR)


# ===========================================================================
# Scenario 7 — Unknown ENV value raises clear error
# ===========================================================================
class TestUnknownEnvValue:

    def test_env_staging_raises_value_error(self, monkeypatch):
        """ENV=staging is not dev or prod — raises ValueError mentioning staging."""
        monkeypatch.setenv("ENV", "staging")
        monkeypatch.setenv("CLIENT_API_KEY", "test-api-key")
        monkeypatch.setenv("FOUNDRY_API_KEY","test-api-key")
        monkeypatch.delenv("LLM_PROVIDER", raising=False)

        with pytest.raises(ValueError, match="staging"):
            load_settings(REAL_CONFIG_DIR)

    def test_env_empty_string_raises_value_error(self, monkeypatch):
        """ENV='' (empty string) raises ValueError mentioning ENV."""
        monkeypatch.setenv("ENV", "")
        monkeypatch.setenv("CLIENT_API_KEY", "test-api-key")
        monkeypatch.setenv("FOUNDRY_API_KEY", "test-api-key")
        monkeypatch.delenv("LLM_PROVIDER", raising=False)

        with pytest.raises(ValueError, match="ENV"):
            load_settings(REAL_CONFIG_DIR)

    def test_env_uppercase_dev_raises(self, monkeypatch):
        """ENV=DEV (wrong case) raises ValueError — must be lowercase dev."""
        monkeypatch.setenv("ENV", "DEV")
        monkeypatch.setenv("CLIENT_API_KEY", "test-api-key")
        monkeypatch.setenv("FOUNDRY_API_KEY", "test-api-key")
        monkeypatch.delenv("LLM_PROVIDER", raising=False)

        with pytest.raises(ValueError, match="DEV"):
            load_settings(REAL_CONFIG_DIR)


# ===========================================================================
# Scenario 8 — No other file calls os.getenv() / os.environ
# ===========================================================================
class TestSingleLoadPoint:

    def test_settings_module_is_sole_env_reader(self):
        """
        Structural check: no src/ file outside settings.py imports os and
        calls os.getenv / os.environ directly.
        """
        src_root = Path(__file__).parent.parent.parent / "src"
        settings_file = (src_root / "config" / "settings.py").resolve()
        violations = []

        for py_file in src_root.rglob("*.py"):
            if py_file.resolve() == settings_file:
                continue  # settings.py is the allowed exception
            content = py_file.read_text(encoding="utf-8")
            if "os.getenv" in content or "os.environ" in content:
                violations.append(str(py_file.relative_to(src_root)))

        assert violations == [], (
            "Files outside settings.py are calling os.getenv/os.environ:\n"
            + "\n".join(f"  src/{v}" for v in violations)
        )


# ===========================================================================
# Scenario 9 — Unknown key in YAML not in Pydantic model raises clear error
# ===========================================================================
class TestUnknownKeyInYaml:

    def _write_valid_base(self, tmp_path: Path) -> None:
        """
        Helper — writes a valid settings.base.yaml to tmp_path.
        Kept in sync with the real settings.base.yaml structure (V2).
        Uses nl_to_ir_strategy + prompt_example_set (not step1/step2 token targets).
        """
        (tmp_path / "settings.base.yaml").write_text(
            "app:\n"
            "  name: nl2sql-engine\n"
            "  version: '1.0'\n"
            "  schema_dir: schemas\n"
            "api:\n"
            "  port: 8000\n"
            "  prefix: /v1\n"
            "llm:\n"
            "  provider: mock\n"
            "  max_tokens: 1000\n"
            "  timeout_seconds: 30\n"
            "  retry_max: 3\n"
            "  retry_backoff_seconds: 2\n"
            "  nl_to_ir_strategy: single_call\n"
            "  prompt_example_set: default\n"
            "sql:\n"
            "  default_top_rows: 0\n"
            "  max_nl_query_length: 0\n"
            "logging:\n"
            "  level: INFO\n"
            "  rotation: daily\n"
            "  log_dir: logs\n"
            "  log_archive_dir: logs/archive\n",
            encoding="utf-8",
        )
        # These tests use tmp_path which has no prompts.yaml — we write a minimal one
        # so load_settings() does not fail on the missing prompts file check.
        (tmp_path / "prompts.yaml").write_text(
            "nl_to_structured_query:\n"
            "  role_description: 'You are a test assistant.'\n"
            "  output_structure: 'Return JSON.'\n"
            "  rules:\n"
            "    output: ['Output rule']\n"
            "    tables: ['Tables rule']\n"
            "    columns: ['Columns rule']\n"
            "    filters: ['Filters rule']\n"
            "    source: ['Source rule']\n"
            "    limit: ['Limit rule']\n"
            "    aggregation: ['Aggregation rule']\n"
            "    sort: ['Sort rule']\n"
            "  example_sets:\n"
            "    default:\n"
            "      - example_one\n"
            "  examples:\n"
            "    example_one:\n"
            "      schema: 'table: Major.Customer'\n"
            "      query: 'get customers'\n"
            "      correct: '{\"tables\": [], \"columns\": [], \"filters\": [], \"limit\": null, \"aggregation\": null, \"sort\": []}'\n"
            "  user_template: 'Schema summary:\\n<SCHEMA_SUMMARY>\\n\\nUser query:\\n<USER_QUERY>'\n",
            encoding="utf-8",
        )

    def test_unknown_top_level_key_in_base_raises(self, monkeypatch, tmp_path):
        """Unknown top-level key in settings.base.yaml raises ValueError."""
        self._write_valid_base(tmp_path)
        # Append an unknown top-level key
        with open(tmp_path / "settings.base.yaml", "a") as f:
            f.write("unknown_section:\n  some_key: some_value\n")

        (tmp_path / "settings.dev.yaml").write_text(
            "logging:\n  level: DEBUG\n", encoding="utf-8"
        )

        monkeypatch.setenv("ENV", "dev")
        monkeypatch.setenv("API_KEY", "test-api-key")
        monkeypatch.delenv("LLM_PROVIDER", raising=False)

        with pytest.raises(ValueError, match="unknown_section"):
            load_settings(tmp_path)

    def test_unknown_key_in_dev_yaml_raises(self, monkeypatch, tmp_path):
        """Unknown key introduced only in settings.dev.yaml raises ValueError."""
        self._write_valid_base(tmp_path)
        (tmp_path / "settings.dev.yaml").write_text(
            "logging:\n"
            "  level: DEBUG\n"
            "mystery_key: oops\n",
            encoding="utf-8",
        )

        monkeypatch.setenv("ENV", "dev")
        monkeypatch.setenv("API_KEY", "test-api-key")
        monkeypatch.delenv("LLM_PROVIDER", raising=False)

        with pytest.raises(ValueError, match="mystery_key"):
            load_settings(tmp_path)

    def test_unknown_key_in_prod_yaml_raises(self, monkeypatch, tmp_path):
        """Unknown key introduced only in settings.prod.yaml raises ValueError."""
        self._write_valid_base(tmp_path)
        (tmp_path / "settings.prod.yaml").write_text(
            "llm:\n"
            "  provider: azure_openai\n"
            "rogue_key: bad_value\n",
            encoding="utf-8",
        )

        monkeypatch.setenv("ENV", "prod")
        monkeypatch.setenv("API_KEY", "test-api-key")
        monkeypatch.delenv("LLM_PROVIDER", raising=False)

        with pytest.raises(ValueError, match="rogue_key"):
            load_settings(tmp_path)


# ===========================================================================
# Scenario P — prompts.yaml loading
# ===========================================================================
class TestPromptsYamlLoading:

    def test_P1_settings_prompts_is_not_none(self, monkeypatch):
        """P1 — settings.prompts is populated after load_settings()."""
        _set_env(monkeypatch, BASE_ENV)
        s = load_settings(REAL_CONFIG_DIR)
        assert s.prompts is not None

    def test_P2_prompts_has_role_description(self, monkeypatch):
        """P2 — settings.prompts.role_description is a non-empty string."""
        _set_env(monkeypatch, BASE_ENV)
        s = load_settings(REAL_CONFIG_DIR)
        assert isinstance(s.prompts.role_description, str)
        assert len(s.prompts.role_description.strip()) > 0

    def test_P3_prompts_has_rules_with_groups(self, monkeypatch):
        """P3 — settings.prompts.rules has at least one non-empty rule group."""
        _set_env(monkeypatch, BASE_ENV)
        s = load_settings(REAL_CONFIG_DIR)
        rules = s.prompts.rules
        assert rules is not None
        # At least one group must have at least one rule
        rules_dict = rules.model_dump()
        assert any(len(v) > 0 for v in rules_dict.values())

    def test_P4_prompts_has_default_example_set(self, monkeypatch):
        """P4 — settings.prompts.example_sets has a 'default' key."""
        _set_env(monkeypatch, BASE_ENV)
        s = load_settings(REAL_CONFIG_DIR)
        assert "default" in s.prompts.example_sets
        assert len(s.prompts.example_sets["default"]) > 0

    def test_P5_prompts_has_at_least_one_example(self, monkeypatch):
        """P5 — settings.prompts.examples has at least one entry."""
        _set_env(monkeypatch, BASE_ENV)
        s = load_settings(REAL_CONFIG_DIR)
        assert len(s.prompts.examples) > 0

    def test_P6_user_template_has_required_placeholders(self, monkeypatch):
        """P6 — user_template contains both <SCHEMA_SUMMARY> and <USER_QUERY>."""
        _set_env(monkeypatch, BASE_ENV)
        s = load_settings(REAL_CONFIG_DIR)
        assert "<SCHEMA_SUMMARY>" in s.prompts.user_template
        assert "<USER_QUERY>" in s.prompts.user_template

    def test_P7_nl_to_ir_strategy_is_single_call(self, monkeypatch):
        """P7 — settings.llm.nl_to_ir_strategy is 'single_call' from base YAML."""
        _set_env(monkeypatch, BASE_ENV)
        s = load_settings(REAL_CONFIG_DIR)
        assert s.llm.nl_to_ir_strategy == "single_call"

    def test_P8_prompt_example_set_is_default(self, monkeypatch):
        """P8 — settings.llm.prompt_example_set is 'default' from base YAML."""
        _set_env(monkeypatch, BASE_ENV)
        s = load_settings(REAL_CONFIG_DIR)
        assert s.llm.prompt_example_set == "default"

    def test_P9_missing_prompts_yaml_raises_value_error(self, monkeypatch, tmp_path):
        """P9 — Missing prompts.yaml causes load_settings() to raise ValueError."""
        # Write a valid settings.base.yaml but NO prompts.yaml
        (tmp_path / "settings.base.yaml").write_text(
            "app:\n"
            "  name: nl2sql-engine\n"
            "  version: '1.0'\n"
            "  schema_dir: schemas\n"
            "api:\n"
            "  port: 8000\n"
            "  prefix: /v1\n"
            "llm:\n"
            "  provider: mock\n"
            "  max_tokens: 1000\n"
            "  timeout_seconds: 30\n"
            "  retry_max: 3\n"
            "  retry_backoff_seconds: 2\n"
            "  nl_to_ir_strategy: single_call\n"
            "  prompt_example_set: default\n"
            "sql:\n"
            "  default_top_rows: 0\n"
            "  max_nl_query_length: 0\n"
            "logging:\n"
            "  level: INFO\n"
            "  rotation: daily\n"
            "  log_dir: logs\n"
            "  log_archive_dir: logs/archive\n",
            encoding="utf-8",
        )
        (tmp_path / "settings.dev.yaml").write_text(
            "logging:\n  level: DEBUG\n", encoding="utf-8"
        )
        # No prompts.yaml written — intentional

        monkeypatch.setenv("ENV", "dev")
        monkeypatch.delenv("LLM_PROVIDER", raising=False)

        with pytest.raises(ValueError, match="prompts.yaml"):
            load_settings(tmp_path)
