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
- 2.3 ✅ Request & Response Models (all tests passing)
- 2.4 ✅ API Authentication (all tests passing)
- 2.5 ✅ Context Validator (all tests passing)

## Current Sprint
Sprint 2 — Core Models, Auth & App Identifier

## Current Story
2.5 — Context Validator ✅ COMPLETE

## Next Story
2.6 — Query Endpoint Skeleton (user-facing)

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
                                    ← V1 in 2.4 (replaced api_key with client_api_key + foundry_api_key,
                                            added prod validator, fixed log_dir/log_archive_dir into
                                            merged["logging"] section)

- src/schema/schema_models.py       ← new in 1.3 (43 tests, all passing)
- src/schema/schema_repository.py   ← V1 in 2.4 (removed stale code= kwarg from all SchemaLoadError calls)
- src/schema/schema_validator.py

- src/core/exceptions.py            ← SchemaLoadError only in 1.4
                                    ← V1 in 2.1 (all 11 exception subclasses added)
                                    ← V2 in 2.5 (MissingContextFieldsError extended with
                                            missing_fields: list[str] | None = None parameter.
                                            Defaults to [] so all existing callers unaffected.
                                            Callers inspect error.missing_fields directly
                                            rather than parsing the message string.)

- src/core/constants.py             ← new in 1.6 (log stage constants only)
                                    ← updated in 2.1 (all 12 error code constants added)

- src/core/models.py                ← new in 2.1 (QueryContext + StructuredQuery + sub-models)
                                    KEY CONSTRAINTS discovered in 2.5:
                                      QueryContext.app_id: str = ""  — NOT Optional.
                                        Pydantic rejects None. Use "" for "not yet populated".
                                      QueryContext.app_schema_version: str = ""  — same rule.
                                      QueryContext.nl_query_original: str  — required, no default.
                                      StructuredQuery.app_id: str  — required, no default.
                                        Must pass app_id= when constructing: StructuredQuery(app_id="ABC_app")

- src/core/logging/log_models.py    ← new in 1.6
- src/core/logging/logger.py        ← new in 1.6

- src/api/app.py                    ← new in 1.5
                                    ← updated in 1.6 (log_dir path fixed)
                                    ← V1 in 2.5 (registered feedback_tool router:
                                            from src.api.tools.feedback_tool import router as feedback_tool_router
                                            app.include_router(feedback_tool_router, prefix="/v1/tools"))

- src/api/health.py                 ← new in 1.5
                                    ← updated in 1.6 (log_dir path fixed)
- src/api/auth.py                   ← new in 2.4 (require_client_key, require_foundry_key)
- src/api/models/request.py         ← new in 2.3
- src/api/models/response.py        ← new in 2.3

- src/api/tools/context_validator.py ← new in 2.5
                                        Design patterns: Strategy, Factory, Open/Closed,
                                        Single Responsibility
                                        StageRequirements: ABC with stage_name + required_fields
                                          abstract properties + @final validate() method.
                                          Subclasses cannot override validate logic.
                                        6 concrete subclasses (one per stage):
                                          AppIdentifierRequirements  → requires: nl_query_original
                                          IntentExtractorRequirements → requires: nl_query_original,
                                                                          app_id, app_schema_version
                                          SchemMapperRequirements    → requires: app_id,
                                                                          app_schema_version, intent_output
                                          ValidatorRequirements      → requires: app_id,
                                                                          app_schema_version,
                                                                          intent_output, mapping_output
                                          SqlBuilderRequirements     → requires: app_id, structured_query
                                          FullQueryRequirements      → requires: nl_query_original
                                        ContextValidator: holds registry dict[str, StageRequirements]
                                          built once via _build_registry() static method (Factory).
                                        Adding a new stage = one new subclass + one registry entry.
                                          Zero changes to ContextValidator.validate() (Open/Closed).
                                        request_id excluded from all validation — Pydantic
                                          auto-generates via default_factory; always guaranteed present.
                                        Validation rules:
                                          None → missing for any field type
                                          "" or whitespace-only → missing for string fields only
                                          {} (empty dict) → NOT missing, valid value
                                          Unknown stage name → raises ValueError (programming error)

- src/api/tools/feedback_tool.py    ← new in 2.5
                                        TODO Phase 3 placeholder only.
                                        POST /v1/tools/feedback → HTTP 501 Not Implemented.
                                        Router registered in app.py with prefix="/v1/tools".

- src/validator/app_identifier.py   ← new in 2.2

### Tests
- tests/config/test_settings.py             ← new in 1.2 (33 tests)
                                             ← updated in 1.6 (log_dir assertion fixed)
- tests/schema/test_schema_models.py        ← new in 1.3 (43 tests)
- tests/schema/test_schema_repository.py
- tests/schema/test_schema_validator.py
- tests/api/conftest.py                     ← new in 1.5
                                            ← V1 in 2.4 (CLIENT_API_KEY + FOUNDRY_API_KEY)
- tests/api/test_health.py                  ← new in 1.5 (27 tests)
                                            ← updated in 1.6 (log_dir path fixed)
- tests/core/logging/test_log_models.py     ← new in 1.6 (M1-M9)
- tests/core/logging/test_logger.py         ← new in 1.6 (L1-L17)
- tests/core/test_models.py                 ← new in 2.1
- tests/core/test_constants.py              ← new in 2.1
- tests/core/test_exceptions.py             ← new in 2.1
- tests/validator/test_app_identifier.py    ← new in 2.2
- tests/api/test_models.py                  ← new in 2.3
- tests/api/test_auth.py                    ← new in 2.4 (A1-A5, B1-B5, C1-C3, D1-D2)

- tests/api/tools/test_context_validator.py ← new in 2.5
                                              V1 — fixed make_context helper and tests:
                                                app_id="" not None (str field, Pydantic rejects None)
                                                app_schema_version="" not None (same reason)
                                                StructuredQuery(app_id="ABC_app") not StructuredQuery()
                                              Groups: A1-A6, B1-B5, C1-C2, D1-D4, E1-E2, F1-F4
                                              + StageRequirements direct unit tests
                                              All passing.

- tests/api/tools/test_feedback_tool.py     ← new in 2.5
                                              2 tests: 501 returned, message mentions Phase 3.
                                              Requires feedback_tool router registered in app.py.

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
- All nested blocks (versioning, business_rules, filter_control) are Optional at model level
- is_junction_table absent in non-junction table JSON — defaults to False in model
- RelationshipSchema uses Field(alias="from") — accessed in code as rel.from_
- HierarchyConfig uses model_config extra=allow — dynamic level keys captured without hardcoding
- Models parse faithfully — no business rule enforcement in models layer

### Schema Repository (1.4)
- Filename must match appId exactly — wrong_name.json raises SchemaLoadError
- Empty schema dir raises SchemaLoadError
- Non-.json files silently ignored
- get_schema() and get_all_schemas() both on SchemaRepository

### Schema Validator (1.4)
- validate_all() checks duplicate appId across schemas
- validate_one() for single schema validation
- Self-referencing relationships explicitly allowed
- Empty string and whitespace-only synonyms both rejected
- Junction tables: empty synonyms passes, non-empty raises

### Health Check API (1.5)
- Factory function: create_app(schema_dir=None) — override used in tests only
- All startup state on app.state
- Lifespan context manager (modern FastAPI pattern)
- /health and /ready auth-exempt
- 4 readiness checks: schemas_loaded, schemas_valid, llm_provider, log_dir_writable
- TestClient MUST be used as context manager to trigger lifespan startup

### Structured Logger (1.6)
- log_dir and log_archive_dir under LoggingSettings
- StructuredLogger(settings) — one JSONL file per request_id
- Rotation: on write — date check per entry. Phase 3: background scheduler.
- 9 log stage constants in constants.py

### Core Models & Constants (2.1)
- QueryContext is the single pipeline state object — travels through every stage
- nl_query_original is immutable after creation
- app_id: str = "" — NOT Optional. Pydantic rejects None. Use "" for "not yet populated".
- app_schema_version: str = "" — same rule as app_id
- StructuredQuery.app_id is required — no default. Always pass app_id= when constructing.
- request_id auto-generated as UUID if not provided
- All 12 error code constants in constants.py
- All 11 exception subclasses in exceptions.py
- Every exception takes message: str only — code injected from constants automatically

### App Identifier (2.2)
- run_app_identifier(context, schema_repo, logger) — single internal function, two callers
- Matching is case-insensitive AND whole-word — uses \b word boundary regex
- Path 1 — explicit app_id: validates against loaded schemas
- Path 2 — synonym matching: raises on 0 or 2+ matches
- APP_DETECTED log emitted on every success

### Request & Response Models (2.3)
- ToolRequest inherits QueryContext
- FeedbackRequest.status uses Literal["pass", "fail"]
- ToolResponse.context is Optional[QueryContext]
- request_id missing → auto-generated (not a ValidationError)

### API Authentication (2.4)
- Two separate keys: CLIENT_API_KEY and FOUNDRY_API_KEY — .env only, never YAML
- Same header X-API-Key for both — route determines which key validates
- require_client_key → POST /v1/query
- require_foundry_key → POST /v1/tools/*
- HTTP 401 for missing or wrong key — no info leakage
- prod: missing key at startup raises ValueError
- dev: missing key → every request to that route returns 401
- Exempt: GET /health, GET /ready

### Context Validator (2.5)
- Design patterns applied: Strategy, Factory, Open/Closed, Single Responsibility
- StageRequirements ABC + @final validate() — subclasses define fields, never logic
- 6 concrete subclasses — one per stage — see file list above for required fields
- ContextValidator registry built once at init via _build_registry() static method
- Adding a new stage = one new subclass + one registry entry. Zero other changes.
- request_id excluded from all stage validation — always guaranteed by Pydantic
- app_id="" is correct "not yet populated" state — app-identifier and query stages
  intentionally do NOT require app_id because they are the ones that produce it
- app-identifier and query (full pipeline) are stateless — agent sends "" app_id,
  stage fills it in, returns populated context. Same behaviour for both user-facing
  pipeline and Foundry tool scenario.
- MissingContextFieldsError carries missing_fields: list[str] — inspect directly
- feedback_tool.py Phase 3 placeholder — 501. Router registered in app.py.
- Architecture document updated to version 1.4

### Bug Fix (schema_repository.py — 2.4)
- SchemaLoadError calls fixed from SchemaLoadError(code=..., message=...)
  to SchemaLoadError(message=...) — code auto-injected from constants

## Architecture Document Updates Made

### Story 1.6
- Section 2 row 19: Log rotation updated to on-write with Phase 3 scheduler note
- Section 12: Rotation behaviour documented
- Section 17 Phase 3: Background scheduler rotation added

### Story 2.5 (Architecture v1.4)
- Section 6.4: Required fields table corrected — request_id removed from all stages;
  note added explaining Pydantic auto-generation
- Section 10.1: POST /v1/tools/feedback added as TODO Phase 3 (returns 501)
- Section 3.1: feedback_tool.py and test_feedback_tool.py added to file tree
- Section 2.2: New subsection — Design Patterns
  (Strategy, Factory, Repository, Dependency Injection,
   Template Method, Single Responsibility, Open/Closed)
- Section 17 Phase 3: Foundry feedback endpoint added to scope
- Change log: version 1.4 row added
