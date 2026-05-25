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
- 2.6 ✅ Query Endpoint Skeleton (user-facing)
- 3.1 ✅ LLM Base & Factory (all tests passing — 9 pass, 3 skipped)
- 3.2 ✅ Mock + OpenAI Provider (all tests passing — 22 passed, 2 skipped)
- 3.3 ✅ Azure OpenAI + Anthropic Provider
- 3.4 ✅ Schema Summary Builder (all tests passing)
- 3.5 ✅ NL-to-IR Strategy Scaffold + QueryContext Refactor (all tests passing)

## Completed Sprints
Sprint 1 — Foundation ✅ COMPLETE
Sprint 2 — Core Models, Auth & App Identifier ✅ COMPLETE

## Current Sprint
Sprint 3 — LLM Layer

## Current Story
3.5 — NL-to-IR Strategy Scaffold + QueryContext Refactor ✅ COMPLETE

## Next Story
3.6 — Single-Call Strategy + Prompt Assembly

## Files Built So Far

### Project Root
- main.py
- requirements.txt                  ← added respx==0.23.1
- .env.example
- .gitignore
- README.md

### Config
- config/settings.base.yaml         ← updated in 1.2 (added llm.provider to base)
                                    ← updated in 1.6 (log_dir, log_archive_dir moved under logging:)
                                    ← TO UPDATE in Story 3.6: add nl_to_ir_strategy and
                                       prompt_example_set under llm: section
- config/settings.dev.yaml
- config/settings.prod.yaml
- config/prompts.yaml               ← TO CREATE in Story 3.6 (sectioned prompt definitions)

### Schemas
- schemas/ABC_app.json

### Source
- src/config/settings.py            ← new in 1.2
                                    ← updated in 1.6 (log_dir, log_archive_dir moved into LoggingSettings)
                                    ← V1 in 2.4 (replaced api_key with client_api_key + foundry_api_key,
                                            added prod validator, fixed log_dir/log_archive_dir into
                                            merged["logging"] section)
                                    ← TO UPDATE in Story 3.6: V2 — load prompts.yaml, add
                                       nl_to_ir_strategy + prompt_example_set to LLMSettings

- src/config/prompts_models.py      ← TO CREATE in Story 3.6 (Pydantic models for prompts.yaml)

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
                                    ← V3. Added UnknownProviderError class.Raised by LLMProviderFactory when provider string does not match any known provider.
                                    ← V4. Added UnknownStrategyError class. Raised by NLToIRStrategyFactory when nl_to_ir_strategy value does not match any registered strategy.

- src/core/constants.py             ← new in 1.6 (log stage constants only)
                                    ← updated in 2.1 (all 12 error code constants added)
                                    ← V2. Added UNKNOWN_PROVIDER error code constant.
                                    ← TO UPDATE in Story 3.5: V3 — add UNKNOWN_STRATEGY error
                                      code constant. Also update log stage constants:
                                      remove LLM_INTENT_OUTPUT + LLM_SCHEMA_MAPPING_OUTPUT,
                                      add INTENT_GUARD_RESULT + LLM_OUTPUT.
                                    ← V3. Replaced LLM_INTENT_OUTPUT + LLM_SCHEMA_MAPPING_OUTPUT
                                      with INTENT_GUARD_RESULT + LLM_OUTPUT.
                                      Added UNKNOWN_STRATEGY error code constant.

- src/core/models.py                ← new in 2.1 (QueryContext + StructuredQuery + sub-models)
                                    KEY CONSTRAINTS discovered in 2.5:
                                      QueryContext.app_id: str = ""  — NOT Optional.
                                        Pydantic rejects None. Use "" for "not yet populated".
                                      QueryContext.app_schema_version: str = ""  — same rule.
                                      QueryContext.nl_query_original: str  — required, no default.
                                      StructuredQuery.app_id: str  — required, no default.
                                        Must pass app_id= when constructing: StructuredQuery(app_id="ABC_app")
                                    ← V1. Removed intent_output + mapping_output fields.
                                      Added single llm_output: Optional[dict[str, Any]] = None.
                                      Added total_latency_ms: int = 0 field.
                                      Holds full simplified IR from NL-to-IR Strategy.

- src/core/logging/log_models.py    ← new in 1.6
- src/core/logging/logger.py        ← new in 1.6

- src/api/app.py                    ← new in 1.5
                                    ← updated in 1.6 (log_dir path fixed)
                                    ← V1 in 2.5 (registered feedback_tool router)
                                    ← V1. Registered query_router with prefix="/v1".

- src/api/health.py                 ← new in 1.5
                                    ← updated in 1.6 (log_dir path fixed)
- src/api/auth.py                   ← new in 2.4 (require_client_key, require_foundry_key)
- src/api/models/request.py         ← new in 2.3
- src/api/models/response.py        ← new in 2.3

- src/api/tools/context_validator.py  ← new in 2.5
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
                                      ← V1. Removed SchemMapperRequirements.
                                        Renamed IntentExtractorRequirements → NLToIRRequirements (stage: "nl-to-ir").
                                        Updated ValidatorRequirements: requires llm_output instead of intent_output + mapping_output.
                                        Registry now has 5 stages.

- src/api/tools/feedback_tool.py    ← new in 2.5
                                        TODO Phase 3 placeholder only.
                                        POST /v1/tools/feedback → HTTP 501 Not Implemented.
                                        Router registered in app.py with prefix="/v1/tools".

- src/api/v1/query.py               ← NEW V0. POST /v1/query skeleton.
                                      Builds QueryContext, calls run_app_identifier(),
                                      returns QueryResponse with app in meta.
                                      sql=None until pipeline wired (Story 5.4).
                                      Business errors → HTTP 200 with errors[].
                                      Internal errors → HTTP 500.
                                    ← TO UPDATE in Story 3.7: V1 — call orchestrator
                                      instead of run_app_identifier() directly.
                                      Returns temporary full QueryContext response shape.
                                      TODO marker added — Story 5.4 replaces with final
                                      QueryResponse shape.
                                    ← TO UPDATE in Story 5.4: V2 — replace temporary
                                      QueryContext response with final QueryResponse shape.
                                      Remove TODO marker.

- src/validator/app_identifier.py   ← new in 2.2
                                      V1. Bug fix: logger.log() now receives
                                      LogEntry(...) object, not keyword arguments.
                                    ← V2. Bug fix (reverted): get_all_schemas()
                                      returns list[AppSchema] in the real codebase.
                                      Reverted to list iteration pattern manually.
                                      Final state: list-based iteration kept throughout.

- src/llm/base.py                   ← NEW V0. LLMProvider ABC.
                                      Two abstract methods: complete() and provider_name().
                                      All providers are synchronous (def, not async def).
                                      Pipeline stages call complete() only — never know
                                      which provider is active.

- src/llm/mock_provider.py          ← NEW V0. MockLLMProvider.
                                      Used in ALL tests — zero real API calls.
                                      Accepts responses: list[str] at construction time.
                                      Each complete() call returns next string in order.
                                      NOTE: Originally described as two-step (intent → mapping)
                                      but now used for single-call simplified IR response.
                                      In tests, responses[0] = canned simplified IR JSON string.
                                      Empty list → ValueError at construction.
                                      More calls than responses → ValueError at call time.

- src/llm/factory.py                ← NEW V0. LLMProviderFactory.
                                      Static method: LLMProviderFactory.create(settings)
                                      Reads settings.llm.provider to select provider.
                                      Mock imported at module level — always available.
                                      Real providers (openai, azure_openai, anthropic)
                                      imported lazily inside create() — missing files
                                      do not break imports during early development.
                                      Unknown provider → UnknownProviderError.

- src/llm/openai_provider.py        ← NEW V0. OpenAIProvider.
                                      Implements LLMProvider ABC. Synchronous — httpx.Client.
                                      Model: gpt-4o-mini. Retry + exponential backoff.
                                      Raises ValueError at construction if openai_api_key missing.

- src/llm/azure_openai_provider.py  ← NEW V0. AzureOpenAIProvider.
                                      Implements LLMProvider ABC. Synchronous — httpx.Client.

- src/llm/anthropic_provider.py     ← NEW V0. AnthropicProvider.
                                      Implements LLMProvider ABC. Synchronous — httpx.Client.

- src/pipeline/schema_summary.py    ← NEW V0. build_schema_summary(schema: AppSchema) -> str.
                                      Compresses AppSchema into plain-text for LLM prompt.
                                      Junction tables excluded entirely.
                                      Table format: table: Major.Customer [synonym1, synonym2]
                                      Column format with synonyms: CustomerCID [Customer id, Customer cid]
                                      Column format without synonyms: CustomerID (plain name)
                                      Column types, business rules, versioning excluded.
                                      Token budget: under 4,800 characters (~1,200 tokens).
                                      Output is deterministic — same input, same output.

- src/pipeline/strategies/__init__.py  ← NEW V0. Story 3.5
- src/pipeline/strategies/base.py      ← NEW V0. Story 3.5 NLToIRStrategy ABC. Two abstract methods: execute() and strategy_name().
                                          Mirrors LLMProvider ABC pattern exactly.
- src/pipeline/strategies/factory.py   ← NEW V0. NLToIRStrategyFactory. Lazy imports SingleCallStrategy (not yet built).
                                          Unknown strategy → UnknownStrategyError. registered_strategies() helper for health checks.
- src/pipeline/strategies/single_call.py ← TO CREATE in Story 3.6
- src/pipeline/prompt_builder.py        ← TO CREATE in Story 3.6
- src/pipeline/intent_guard.py          ← TO CREATE in Story 3.7
- src/pipeline/orchestrator.py          ← TO CREATE in Story 3.7 (V0 — partial)
                                        ← TO UPDATE in Story 5.4 (V1 — final)

### Tests
- tests/config/test_settings.py             ← new in 1.2 (33 tests)
                                             ← updated in 1.6 (log_dir assertion fixed)
                                             ← TO UPDATE in Story 3.6: V2 — test prompts.yaml loading
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
                                            ← V1. Added C1-C5 for llm_output field.Removed all intent_output/mapping_output refs.
- tests/core/test_constants.py              ← new in 2.1
- tests/core/test_exceptions.py             ← new in 2.1
- tests/validator/test_app_identifier.py    ← new in 2.2
- tests/api/test_models.py                  ← new in 2.3
- tests/api/test_auth.py                    ← new in 2.4 (A1-A5, B1-B5, C1-C3, D1-D2)
- tests/api/v1/test_query.py                ← NEW V0. 15 tests: A1-A3 auth, B1-B5 validation,
                                              C1-C4 success, D1-D2 business errors, E1 internal.
                                            ← TO UPDATE in Story 3.7: V1 — updated for orchestrator
                                            ← TO UPDATE in Story 5.4: V2 — final response shape

- tests/api/tools/test_context_validator.py ← new in 2.5
                                              Groups: A1-A6, B1-B5, C1-C2, D1-D4, E1-E2, F1-F4
                                              + StageRequirements direct unit tests. All passing.
                                            ← V1. Replaced intent-extractor/schema-mapper
                                               tests with nl-to-ir tests. Updated validator tests for llm_output. Registry count: 6 → 5 stages.

- tests/api/tools/test_feedback_tool.py     ← new in 2.5. 2 tests: 501 + Phase 3 message.

- tests/llm/test_base.py                    ← NEW V0. 3 tests: A1-A3.
- tests/llm/test_mock_provider.py           ← NEW V0. 6 tests: B1-B6.
- tests/llm/test_factory.py                 ← NEW V0. 9 tests: C1-C7 (all passing after V2).
- tests/llm/test_openai_provider.py         ← NEW V0. 8 tests: D1-D8.
- tests/llm/test_azure_openai_provider.py   ← NEW V0. 11 tests: E1-E11.
- tests/llm/test_anthropic_provider.py      ← NEW V0. 8 tests: F1-F8.
- tests/pipeline/test_schema_summary.py     ← NEW V0. 10 tests: A1-A6, B1, C1-C4.

- tests/pipeline/strategies/__init__.py       ← NEW V0. in Story 3.5
- tests/pipeline/strategies/test_base.py      ← NEW V0. in Story 3.5 5 tests: A1-A4 + A2 extended.
- tests/pipeline/strategies/test_factory.py   ← NEW V0. in Story 3.5 5 tests: B1-B4 + B1 extended.
- tests/pipeline/test_prompt_builder.py       ← TO CREATE in Story 3.6
- tests/pipeline/strategies/test_single_call.py ← TO CREATE in Story 3.6
- tests/pipeline/test_intent_guard.py         ← TO CREATE in Story 3.7
- tests/pipeline/test_orchestrator.py         ← TO CREATE in Story 3.7

### Init Files
- All __init__.py files (25 total) ← created in 1.1
- tests/pipeline/strategies/__init__.py ← TO CREATE in Story 3.5

---

## Pre-Implementation Design Decisions (LLM)

All decisions below were made before Story 3.5 implementation began.
Full detail in architecture document v1.6 (Sections 2, 6, 7, 8, 10, 12, 13, 16).
These bullets move to Key Decisions Made as each story completes.

- QueryContext: intent_output + mapping_output removed → single llm_output field (Story 3.5)
- NLToIRStrategy ABC + NLToIRStrategyFactory — Strategy pattern mirrors LLMProviderFactory (Story 3.5)
- UnknownStrategyError + UNKNOWN_STRATEGY error code added (Story 3.5)
- context_validator.py refactored — SchemMapperRequirements deleted, IntentExtractorRequirements
  renamed to NLToIRRequirements, ValidatorRequirements updated to require llm_output (Story 3.5)
- SingleCallStrategy — single LLM call, simplified IR, built once at construction (Story 3.6)
- prompts.yaml — sectioned structure assembled by PromptBuilder at startup (Story 3.6)
- PromptBuilder — validate() + build_system_prompt() + render_user_prompt() (Story 3.6)
- settings.base.yaml: new keys llm.nl_to_ir_strategy + llm.prompt_example_set (Story 3.6)
- Simplified IR shape: tables/columns/filters each with source field + limit/aggregation/sort (Story 3.6)
  aggregation and sort captured in Phase 1 but NOT executed until Phase 2
- Intent Guard — deterministic keyword check before any LLM call (Story 3.7)
  Called from every endpoint accepting nl_query_original — single function, multiple callers
- Partial orchestrator wired: App Identifier → Intent Guard → NL-to-IR Strategy (Story 3.7)
- Source-driven hierarchy role assignment — LLM never produces roles, validator derives from
  source field matched against schema hierarchy synonyms (Story 4.3 Join Resolver)
- Foundry endpoints: /v1/tools/intent-extractor + /v1/tools/schema-mapper removed,
  /v1/tools/nl-to-ir added (Story 4.1)
- Log stages: INTENT_GUARD_RESULT + LLM_OUTPUT replace LLM_INTENT_OUTPUT + LLM_SCHEMA_MAPPING_OUTPUT
- Story restructure: 3.5, 3.6, 3.7 (new) + Sprint 4 renumbered 4.1-4.6
  (see architecture document Section 16.2 for full story definitions)

---

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
- MissingContextFieldsError carries missing_fields: list[str] — inspect directly
- feedback_tool.py Phase 3 placeholder — 501. Router registered in app.py.
- Architecture document updated to version 1.4

### Query Endpoint (2.6)
- POST /v1/query uses require_client_key auth dependency
- QueryContext built from QueryRequest at route entry
- run_app_identifier() is the only pipeline stage called in this story
- Business errors (APP_NOT_DETERMINED, MULTIPLE_APPS_MATCHED) → HTTP 200
- Internal errors (schema_repo=None, unexpected) → HTTP 500
- sql=None and total_tokens_used=0 until pipeline stages wired in later sprints
- REQUEST_RECEIVED log emitted immediately on entry with caller="user"

### Logger Tech Debt (flagged 2.6)
- StructuredLogger has no Strategy pattern — switching log destination requires a code change
- Should be refactored to LogWriter ABC + factory + config key before Phase 2
- Tracked as tech debt — not blocking Phase 1

### LLM Base & Factory (3.1)
- LLMProvider is an ABC — cannot be instantiated directly
- All providers are synchronous — def not async def. uvicorn handles concurrency.
- MockLLMProvider uses a responses list — call order determines which response returned.
- Tests construct MockLLMProvider directly with specific responses.
- Factory-created mock uses a single placeholder response ["mock_response"] —
  only used when provider=mock in config, not in tests.
- Real providers use lazy imports inside create() — provider files can be absent
  during early stories without breaking any existing imports or tests.
- UnknownProviderError added to exceptions.py (V3) and UNKNOWN_PROVIDER
  added to constants.py (V2).

### OpenAI Provider (3.2)
- httpx.Client used for all HTTP calls — sync, consistent with architecture decision 44
- respx==0.23.1 added to requirements.txt — standard mock library for httpx
- _call() separated from complete() — HTTP layer isolated, retry loop stays clean
- retry_backoff_seconds set to 0 in tests — prevents time.sleep() from slowing test suite
- _OPENAI_API_URL and _MODEL defined as module-level constants — imported in tests
  so URL is never duplicated between source and test files
- Missing openai_api_key raises ValueError at construction — fails fast before any API call
- Factory _make_settings() helper updated to carry openai_api_key for C3 test

### Azure OpenAI + Anthropic Provider (3.3)
- AzureOpenAIProvider URL built at construction time from 3 parts:
    endpoint + deployment_name + api_version. Stored as self._url — one build, reused per call.
- Azure auth uses api-key header — not Bearer token like OpenAI.
- All 4 Azure credentials validated at construction — single ValueError lists all missing fields.
- AnthropicProvider model string is module-level constant _MODEL = "claude-sonnet-4-5".
    Flagged as tech debt — future story should move to settings.llm.anthropic_model.
- Anthropic API shape differs from OpenAI — system is top-level, response at content[0].text.
- Both providers follow identical retry loop pattern as OpenAIProvider.
- test_factory.py _make_settings() now carries all provider credentials.

### Schema Summary Builder (3.4)
- build_schema_summary() is a pure helper function — not a pipeline stage.
  Called inside SingleCallStrategy.execute() (Story 3.6), not directly by the orchestrator.
- Junction tables excluded from summary — LLM must never propose them.
- Table format: table: Major.Customer [synonym1, synonym2]
- Column format with synonyms: CustomerCID [Customer id, Customer cid]
- Column format without synonyms: CustomerID (plain name, no brackets)
- Table with no synonyms: table: Major.SomeTable [] (empty brackets)
- Column types, business rules, versioning config excluded from summary.
- is_identifier and is_default_text flags NOT included — flagged for Phase 2.
- Token budget: output under 4,800 characters (~1,200 tokens at ~4 chars/token).
- Output is deterministic — same input always produces same output.

### NL-to-IR Strategy Scaffold (3.5)
- NLToIRStrategy ABC mirrors LLMProvider ABC exactly — same pattern, same rationale
- NLToIRStrategyFactory uses lazy imports for SingleCallStrategy — same pattern as LLMProviderFactory. Strategy files can be absent during    early stories without breaking imports.
- Factory in this story has an empty registry until Story 3.6 adds SingleCallStrategy. registered_strategies() returns [] until then — this is correct and tested (B4).
- _PatchedFactory test pattern used in test_factory.py — injects a stub strategy to test the factory mechanism without needing SingleCallStrategy to exist.
context_validator.py now has exactly 5 stages: app-identifier, nl-to-ir, validator, sql-builder, query.
- intent-extractor and schema-mapper stage names are gone — any agent sending those names will receive a ValueError (programming error, not a pipeline error).
- total_latency_ms: int = 0 added to QueryContext in this story — was in the architecture doc but missing from V0 models.py.
- QueryContext: intent_output + mapping_output removed → single llm_output field ✅
- NLToIRStrategy ABC + NLToIRStrategyFactory — Strategy pattern mirrors LLMProviderFactory ✅
- UnknownStrategyError + UNKNOWN_STRATEGY error code added ✅
- context_validator.py refactored — SchemMapperRequirements deleted, IntentExtractorRequirements renamed to NLToIRRequirements, ValidatorRequirements updated to require llm_output ✅

### Bug Fix (schema_repository.py — 2.4)
- SchemaLoadError calls fixed from SchemaLoadError(code=..., message=...)
  to SchemaLoadError(message=...) — code auto-injected from constants

---

## Architecture Document Updates Made

### Story 1.6
- Section 2 row 19: Log rotation updated to on-write with Phase 3 scheduler note
- Section 12: Rotation behaviour documented
- Section 17 Phase 3: Background scheduler rotation added

### Story 2.5 (Architecture v1.4)
- Section 6.4: Required fields table corrected — request_id removed from all stages
- Section 10.1: POST /v1/tools/feedback added as TODO Phase 3 (returns 501)
- Section 3.1: feedback_tool.py and test_feedback_tool.py added to file tree
- Section 2.2: New subsection — Design Patterns
- Section 17 Phase 3: Foundry feedback endpoint added to scope
- Change log: version 1.4 row added

### Story 2.6 (Architecture v1.5)
- Added sub-section 2.3 Tech Debt under section 2 Technical Decisions.

### Pre-Story 3.5 (Architecture v1.6)
- Full LLM layer redesign documented across all sections
- See architecture document v1.6 (consolidated from PART1 + PART2 + PART3 md files)
- Key sections changed: 2, 3.1, 4, 6, 7, 8, 10, 12, 13, 14, 16, 17

