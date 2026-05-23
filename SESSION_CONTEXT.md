# SESSION_CONTEXT.md

## Completed Stories (all tests passing)
- 1.1 ✅ Project Scaffold
- 1.2 ✅ Configuration
- 1.3 ✅ Schema Models
- 1.4 ✅ Schema Repository & Validator
- 1.5 ✅ Health Check API (27 tests, all passing)
- 1.6 ✅ Structured Logger (all tests passing)
- 2.1 ✅ Core Models & Constants (all tests passing)
- 2.2 ✅ App Identifier (all tests passing)

## Current Sprint
Sprint 2 — Core Models, Auth & App Identifier

## Current Story
2.2 — App Identifier ✅ COMPLETE

## Next Story
2.3 — Request & Response Models

## Files Built So Far

### Project Root
- main.py
- requirements.txt
- .env.example
- .gitignore
- README.md

### Config
- config/settings.base.yaml        ← updated in 1.2 (added llm.provider to base)
                                   ← updated in 1.6 (log_dir, log_archive_dir moved under logging:)
- config/settings.dev.yaml
- config/settings.prod.yaml

### Schemas
- schemas/ABC_app.json

### Source
- src/config/settings.py            ← new in 1.2
                                    ← updated in 1.6 (log_dir, log_archive_dir moved into LoggingSettings)
- src/schema/schema_models.py       ← new in 1.3 (43 tests, all passing)
- src/schema/schema_repository.py
- src/schema/schema_validator.py
- src/core/exceptions.py            ← SchemaLoadError only in 1.4
                                    ← updated in 2.1 (all 11 exception subclasses added)
- src/core/constants.py             ← new in 1.6 (log stage constants only)
                                    ← updated in 2.1 (all 12 error code constants added)
- src/core/models.py                ← new in 2.1 (QueryContext + StructuredQuery + sub-models)
- src/core/logging/log_models.py    ← new in 1.6
- src/core/logging/logger.py        ← new in 1.6
- src/api/app.py                    ← new in 1.5
                                    ← updated in 1.6 (log_dir path fixed to settings.logging.log_dir)
- src/api/health.py                 ← new in 1.5
                                    ← updated in 1.6 (log_dir path fixed to settings.logging.log_dir)
- src/validator/app_identifier.py   ← new in 2.2

### Tests
- tests/config/test_settings.py          ← new in 1.2 (33 tests, all passing)
                                          ← updated in 1.6 (log_dir assertion fixed)
- tests/schema/test_schema_models.py     ← new in 1.3 (43 tests, all passing)
- tests/schema/test_schema_repository.py
- tests/schema/test_schema_validator.py
- tests/api/conftest.py                  ← new in 1.5 (sets ENV/API_KEY/LLM_PROVIDER for all api tests)
- tests/api/test_health.py               ← new in 1.5 (27 tests, all passing)
                                          ← updated in 1.6 (log_dir path fixed)
- tests/core/logging/test_log_models.py  ← new in 1.6 (M1-M9, all passing)
- tests/core/logging/test_logger.py      ← new in 1.6 (L1-L17, all passing)
- tests/core/test_models.py              ← new in 2.1
- tests/core/test_constants.py           ← new in 2.1
- tests/core/test_exceptions.py          ← new in 2.1
- tests/validator/test_app_identifier.py ← new in 2.2 (all tests passing)

### Init Files
- All __init__.py files (25 total) ← created in 1.1

## Key Decisions Made

### Configuration (1.2)
- ENV is case-sensitive — must be exactly `dev` or `prod` (not `DEV`)
- settings.base.yaml owns all keys — dev/prod only override values, never introduce new keys
- Unknown YAML keys not in Pydantic model raise ValueError at startup (extra=forbid)
- LLM_PROVIDER in .env overrides whatever YAML says
- settings.py is the only file allowed to call os.getenv() / os.environ

### Schema Models (1.3)
- All nested blocks (versioning, business_rules, filter_control) are Optional at model level — validator (1.4) enforces business rules
- is_junction_table absent in non-junction table JSON — defaults to False in model
- is_junction_table present and True only for junction tables (e.g. Major.PackagePlan)
- Non-junction tables do not have is_junction_table property in JSON at all
- RelationshipSchema uses Field(alias="from") — accessed in code as rel.from_ (from is Python reserved word)
- HierarchyConfig uses model_config extra=allow — dynamic level keys (top_Acc, sub_Acc) captured without hardcoding
- Models parse faithfully — no business rule enforcement in models layer
- Validator layer (Story 1.4) is sole enforcer of schema business rules

### Schema Repository (1.4)
- Filename must match appId exactly — wrong_name.json with appId ABC_app raises SchemaLoadError
- Empty schema dir raises SchemaLoadError — at least one schema required
- Non-.json files silently ignored
- Empty file, malformed JSON, invalid schema structure all raise SchemaLoadError
- Empty appId raises SchemaLoadError
- get_schema() and get_all_schemas() both on SchemaRepository

### Schema Validator (1.4)
- validate_all() checks duplicate appId across schemas — validator's responsibility
- validate_one() for single schema validation
- Self-referencing relationships (Major.Acc → Major.Acc) explicitly allowed
- Empty string and whitespace-only synonyms both rejected
- Duplicate synonyms checked both within same table and across tables
- Junction tables: empty synonyms passes, non-empty synonyms raises
- src/core/exceptions.py created with NL2SQLBaseError + SchemaLoadError only

### Health Check API (1.5)
- Factory function pattern: create_app(schema_dir=None) — schema_dir override used in tests only
- Startup failure behaviour: if schemas fail to load, service still starts but /ready returns 503
- All startup state stored on app.state — health endpoints read from it, never re-load
- app.state fields: settings, schema_repo, schemas_loaded_ok, schemas_valid_ok, startup_error, schema_dir
- Lifespan context manager used (modern FastAPI pattern) — not deprecated @app.on_event
- /health and /ready are both auth-exempt — no X-API-Key required
- LLM provider check: reads settings.llm.provider only — no real API call
- log_dir_writable check: reads settings.logging.log_dir (updated in 1.6)
- 4 readiness checks: schemas_loaded, schemas_valid, llm_provider, log_dir_writable
- TestClient MUST be used as context manager ("with" block) to trigger lifespan startup
- without "with", startup never fires and app.state stays uninitialised
- tests/api/conftest.py sets ENV/API_KEY/LLM_PROVIDER via monkeypatch autouse fixture
- this means tests work on any machine with or without a .env file
- _make_schema_dir uses parents=True, exist_ok=True — handles nested temp paths on Windows
- ready_response fixture in TestReadyHappyPath captures response inside "with" block and returns it
- All 27 tests pass: H1-H4, H3b, R1-R7, F1-F7, E1-E5 + 2 extras

### Structured Logger (1.6)
- log_dir and log_archive_dir moved from flat root Settings into LoggingSettings
- YAML keys: logging.log_dir and logging.log_archive_dir (under logging: section)
- Code access: settings.logging.log_dir and settings.logging.log_archive_dir
- app.py and health.py updated manually to use new path
- test_settings.py updated: log_dir assertion fixed + _write_valid_base helper updated
- StructuredLogger(settings) — receives full Settings object, reads logging sub-model
- One JSONL file per request_id: {log_dir}/{request_id}.log
- Rotation: on write — checks file mtime before each write
- If file mtime date < today → move to {log_archive_dir}/YYYY-MM-DD/ then write fresh file
- Rotation tested using os.utime() to set file mtime to yesterday — no mocking needed
- After rotation: old file in archive, new file created in log_dir with new entry only
- Phase 3: background scheduler rotation to replace on-write rotation
- src/core/constants.py created with 9 log stage constants only (rest in 2.1):
    REQUEST_RECEIVED, APP_DETECTED, LLM_INTENT_OUTPUT, LLM_SCHEMA_MAPPING_OUTPUT,
    VALIDATION_RESULT, STRUCTURED_QUERY_BUILT, SQL_BUILT, RESPONSE_SENT, USER_FEEDBACK

### Core Models & Constants (2.1)
- QueryContext is the single pipeline state object — travels through every stage
- nl_query_original is immutable after creation — __setattr__ override raises AttributeError
- _initialised flag set via object.__setattr__ in model_post_init to bypass the override
- StructuredQuery is the SQL blueprint — built by validator, consumed by SQL builder
- Sub-models: ResolvedTable, ResolvedColumn, ResolvedJoin, ResolvedFilter
- top_rows on StructuredQuery is Optional[int] — None means use config default
- QueryContext.status defaults to "pending" — updated to "success" or "failed" by pipeline
- QueryContext.request_id auto-generated as UUID if not provided
- All list fields use Field(default_factory=list) — never share state across instances
- All 12 error code constants added to constants.py
- All 11 exception subclasses added to exceptions.py
- Every exception takes only message: str — code injected from constants automatically

### App Identifier (2.2)
- run_app_identifier(context, schema_repo, logger) — single internal function, two callers
- Two callers: pipeline orchestrator (POST /v1/query) and Foundry tool (POST /v1/tools/app-identifier, Story 5.6)
- Matching is case-insensitive AND whole-word — uses \b word boundary regex
- _is_whole_word_match(synonym, text) — private helper, unit tested directly
- re.escape() used on synonym before building regex — handles special characters safely
- Matching checks app_name first, then each appSynonyms entry — first hit per app wins
- Path 1 — explicit app_id: validates against loaded schemas, raises AppNotDeterminedError if unknown
- Path 2 — synonym matching: scans all schemas, collects all matches, raises on 0 or 2+
- match_method = "explicit" or "synonym" — logged in APP_DETECTED payload
- APP_DETECTED log emitted on every success — contains app_id, schema_version, match_method
- latency_ms["app_identifier"] set on context after every successful call
- Tests use MagicMock for schema and repo objects — no real JSON files needed in unit tests
- Second fake schema used in C1/E2 tests to force MultipleAppsMatchedError
- All test groups pass: A1-A7, B1-B3, C1, D1-D1c, D2-D3, E1-E2 + helper unit tests

## Architecture Document Updates Made
### Story 1.6
- Section 2 row 19: Log rotation updated to "Daily — triggered on write (date check per entry). Phase 3: background scheduler"
- Section 12: Rotation behaviour documented as on-write date check
- Section 17 Phase 3: Background scheduler rotation added to scope