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
- 3.6 ✅ Single-Call Strategy + Prompt Assembly
- 3.7 ✅ Partial Pipeline Wire-up + Intent Guard
- 4.1 ✅ NL-to-IR Tool Endpoint (all tests passing)
- 4.2 ✅ Table & Column Validator (all tests passing)
- 4.3 ✅ Join Resolver
- 4.4 ✅ Rule Applicator
- 4.5 ✅ Structured Query Builder 
- 4.6 ✅ Validator Tool Endpoint 
- 5.1 ✅ Select Builder (all tests passing)
- 5.2 ✅ Join Builder (all tests passing)
- 5.3 ✅ Where Builder (all tests passing)
- 5.4 ✅ SQL Orchestrator & Final Pipeline Wire-up (all tests passing)
- 5.5 ✅ SQL Builder Tool Endpoint
- 5.6 ✅ App Identifier Tool Endpoint (all tests passing)
- 5.7 ✅ Full Pipeline Tool Endpoint (tools/query)
- 5.8 ✅ Golden E2E Test (all tests passing — Part A exact match, Part B data-driven, Diagnostic)
- 5.9 ✅ Tech Debt Closure + Hierarchy/Filter Fixes — COMPLETE

## Completed Sprints
Sprint 1 — Foundation ✅ COMPLETE
Sprint 2 — Core Models, Auth & App Identifier ✅ COMPLETE
Sprint 3 — LLM Layer ✅ COMPLETE
Sprint 4 — Schema Mapping & Validation ✅ COMPLETE


## Current Sprint
Sprint 5 — SQL Builder 

## Current Story
Story 5.9 — Tech Debt Closure + Hierarchy/Filter Fixes ✅ COMPLETE

## Next Story
Story 5.10 (TBD) — confirm from architecture doc before starting.
NOTE: A dedicated LLM-reliability story is queued (see "Future Story — LLM Reliability" below).
Decide whether it runs as the last Phase 1 story or moves to Phase 2.


## Files Built So Far

### Project Root
- main.py
- requirements.txt                  ← added respx==0.23.1
- .env.example                      ← V2. Added AZURE_FOUNDRY_ENDPOINT,AZURE_FOUNDRY_API_KEY,AZURE_FOUNDRY_DEPLOYMENT_NAME. 
                                      entries under new "Azure AI Foundry" section. LLM_PROVIDER comment updated to include azure_foundry. 
- .gitignore
- README.md

### Config
- config/settings.base.yaml         ← updated in 1.2 (added llm.provider to base)
                                    ← updated in 1.6 (log_dir, log_archive_dir moved under logging:)
                                    ← V2. Removed step1_token_target + step2_token_target.
                                      Added nl_to_ir_strategy: single_call and
                                      prompt_example_set: default under llm: section.
                                    ← V3 (Story 5.9). Added llm.temperature: 0 (deterministic output).

- config/settings.dev.yaml
- config/settings.prod.yaml
- config/prompts.yaml               ← NEW V0. Sectioned prompt definitions.Three examples: hierarchy_with_filter,
                                      filter_only_customer, aggregation_with_limit.example_sets: default (3 examples) + minimal (1).
                                      user_template contains <SCHEMA_SUMMARY> + <USER_QUERY>.
                                     ← TO UPDATE. Add strict synonym matching rule to rules.tables section. Add strict_synonym_matching
                                      example. Add to default example_set.
                                    ← V1 (Story 5.9). Added negative_strict_synonym example ("topaccount" must NOT
                                      match "top acc"). Added fused-word prohibition to rules.tables. Added the example
                                      to both default and minimal example_sets.
- config/mock_responses.json        ← NEW V0. Mock LLM responses for JSON mode.
                                      Each entry has user_input (exact match string) and llm_response (IR JSON string). First entry:
                                      "give me topaccount name for customer ASA".
                                    ← V1 (Story 5.8). Added app_id field to entries without "in ABC" (App Identifier needs explicit app_id when query has no app synonym). Added final_sql field to each entry — populated by scripts/generate_mock_sql.py, used by Part B data-driven E2E assertions.

### Schemas
- schemas/ABC_app.json

### Source
- src/config/settings.py            ← new in 1.2
                                    ← updated in 1.6 (log_dir, log_archive_dir moved into LoggingSettings)
                                    ← V1 in 2.4 (replaced api_key with client_api_key + foundry_api_key,
                                            added prod validator, fixed log_dir/log_archive_dir into
                                            merged["logging"] section)
                                    ← V2. Replaced step1_token_target + step2_token_target
                                              with nl_to_ir_strategy + prompt_example_set in
                                              LLMSettings. Added _load_prompts() and _remap_example_schema_keys() helpers. prompts.yaml
                                              loaded independently and attached as settings.prompts.Service refuses to start if prompts.yaml missing.
                                    ← V3. Added azure_foundry_endpoint,
                                       azure_foundry_api_key, azure_foundry_deployment_name
                                       Optional fields. Injected via _optional_llm_secrets
                                       list in load_settings().
                                    ← V4 (Story 5.9). Added temperature: float = 0.0 to LLMSettings.

- src/config/prompts_models.py      ← NEW V0/V1. Pydantic models for prompts.yaml structure.
                                      PromptExample, PromptRules, StrategyPromptSpec,
                                      PromptsConfig. schema_ field (not schema) to avoid
                                      Pydantic reserved name collision.
                                      V1: Fixed duplicate model_config + inner Config class
                                      on PromptExample — Pydantic v2 rejects both together.

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
                                    ← V3.AddedUnknownProviderError class.RaisedbyLLMProviderFactory when provider string does not match any known provider.
                                    ← V4. Added UnknownStrategyError class. Raised by NLToIRStrategyFactory when nl_to_ir_strategy value does not match any registered strategy.
                                    ← V5. Added StructuredQueryBuildError for self-join alias resolution failures

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
                                    ← V4. Added STRUCTURED_QUERY_BUILD_ERROR error code  

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
                                    ← V2. Changed resolved_tables, resolved_columns,
                                      resolved_filters from list[str] to list[dict].
                                      Each entry preserves full dict from llm_output
                                      (including source field) so join resolver and
                                      rule applicator have full context.
                                      resolved_joins remains list[str] for now.
                                     ← V3. Changed resolved_joins from list[str] to list[dict] with on_conditions: list[dict] shape. Updated resolved_tables comment to document alias and role enrichment.
                                     ← V4. ResolvedJoin — replaced on_left/on_right with on_conditions: list[dict] to support multi-condition joins
                                     ← V5. Added connector: str = "AND" to ResolvedFilter. Defaults to "AND" so all existing callers are unaffected.
                                       Enables OR conditions in WHERE clause.build_where() reads connector to emit AND or OR between filters.      

- src/core/logging/log_models.py    ← new in 1.6
- src/core/logging/logger.py        ← new in 1.6

- src/api/app.py                    ← new in 1.5
                                    ← updated in 1.6 (log_dir path fixed)
                                    ← V1 in 2.5 (registered feedback_tool router)
                                    ← V1. Registered query_router with prefix="/v1".
                                    ← V2. Added Step 5 — LLM provider initialisation
                                      via LLMProviderFactory. app.state.llm_provider and
                                      app.state.llm_provider_ok now set at startup.
                                    ← V3. Registered nl_to_ir_tool router
                                      under prefix="/v1/tools".
                                    ← V4. Registered validator_tool router under /v1/tools
                                    ← V5. Registered sql_builder_tool router under prefix="/v1/tools".
                                     ← V6. Registered app_identifier_tool router under prefix="/v1/tools".
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

- src/api/tools/nl_to_ir_tool.py    ← NEW V0. POST /v1/tools/nl-to-ir.
                                      Validates context fields (nl_query_original,
                                      app_id, app_schema_version) via ContextValidator.
                                      Runs Intent Guard then NL-to-IR Strategy.
                                      Returns ToolResponse with updated QueryContext.
                                      Auth via Depends(require_foundry_key).  

src/api/tools/validator_tool.py     ← NEW V0. endpoint — mirrors nl_to_ir_tool.py pattern exactly
                                    ← V1. POST /v1/tools/validator — runs full validator chain, returns StructuredQuery
src/api/tools/sql_builder_tool.py   ← NEW V0. POST /v1/tools/sql-builder.
                                      Validates structured_query present (stage "sql-builder"),
                                      calls run_sql_builder(context, logger, settings),
                                      returns ToolResponse with context.sql populated.
                                      require_foundry_key auth. HTTP 400 on missing fields,
                                      HTTP 500 on unexpected error, HTTP 200 on success.
- src/api/tools/app_identifier_tool.py  ← NEW V0. POST /v1/tools/app-identifier.
                                          Validates nl_query_original via ContextValidator(stage "app-identifier"). Runs Intent Guard then run_app_identifier(). Returns ToolResponse with app_id and app_schema_version populated.
                                          Sets context.status="success" on success.
                                          Business errors (APP_NOT_DETERMINED, MULTIPLE_APPS_MATCHED) → HTTP 200 with error
                                          in context. HTTP 400 on missing fields.
                                          HTTP 500 on unexpected error. require_foundry_key auth.
src/api/tools/query_tool.py         ← POST /v1/tools/query — Foundry one-shot full pipeline
                                      endpoint. Accepts QueryContext with nl_query_original,
                                      calls run_pipeline(), returns ToolResponse with fully
                                      populated QueryContext including sql.

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
                                    ← V1. Replaced direct run_app_identifier() call with
                                      run_pipeline() (orchestrator). Reads llm_provider
                                      from app.state. Response is now full QueryContext dict
                                      (temporary shape). REQUEST_RECEIVED log now emitted
                                      inside orchestrator — removed duplicate emit from V0.
                                      Business error except blocks removed — orchestrator
                                      handles them internally.
                                    ← V2. Replaced temporary QueryContext response with final
                                      QueryResponse shape (Section 10.3). TODO marker removed.
                                      Top-level keys: request_id, status, data, meta, errors.
                                      data.sql populated from context.sql on success.
                                      errors[] list replaces context.error dict for business errors.
                                      Emits RESPONSE_SENT log after pipeline completes.
                                      _build_response() helper extracted for 500 and 200 paths.

  - src/validator/app_identifier.py       ← new in 2.2
                                            V1. Bug fix: logger.log() now receives
                                            LogEntry(...) object, not keyword arguments.
                                          ← V2. Bug fix (reverted): get_all_schemas()
                                            returns list[AppSchema] in the real codebase.
                                            Reverted to list iteration pattern manually.
                                            Final state: list-based iteration kept throughout.
- src/validator/table_column_validator.py ← NEW V0.
                                            run_table_column_validator(context, schema_repo, logger).
                                            Validates llm_output.tables and llm_output.columns
                                            against schema. Junction tables rejected even if in
                                            schema. Table check runs first — failure stops column
                                            check. Populates resolved_tables and resolved_columns
                                            with full dicts (source preserved). Emits
                                            VALIDATION_RESULT log on success.                                      
src/validator/join_resolver.py            ← NEW V0. run_join_resolver(context, schema_repo, logger). Schema-driven alias generation,
                                            hierarchy role assignment, self-join detection, junction auto-bridging. Emits VALIDATION_RESULT log.
                                          ← V1. Stamps role on resolved_columns and resolved_filters entries for self-join tables.
                                            Tech debt comments added on raise sites
                                          ← V2 (Story 5.8). Fixed duplicate join condition in self-join additional conditions.  
                                            Forward + reverse relationship lookups both ran unconditionally, adding c.CustomerID = a_sub.CustomerID twice. Reverse lookup now runs only as fallback (if/else) when no forward relationship exists.
                                          ← V3 (Story 5.9, Bug #7). Stamps hierarchy role on single-instance hierarchy tables (not just self-join); warns when source matches no level.
                                          ← V4 (Story 5.9, Bug #12). Stamps role on columns/filters for single-instance hierarchy tables too (not just self-join).
                                          ← V5 (Story 5.9, Bug #13/DD-4). Extracted _match_hierarchy_role + _table_has_hierarchy into shared synonym_matching module; imports them now (pure refactor, no behaviour change).
src/validator/rule_applicator.py          ← NEW V0. run_rule_applicator(context, schema_repo, logger). 
                                            Applies active_record, versioning, hierarchy conditions with alias prefix. Suppress token check. Deduplication. Emits VALIDATION_RESULT log.
src/validator/structured_query_builder.py       ← V0. Translates enriched QueryContext dicts into typed StructuredQuery model. 
                                                  Logs error before raising on self-join alias ambiguity
                                                 ← V1 (Story 5.9, Bug #12). Single-instance alias fallback: when a column/filter (table, role) lookup misses on a single-instance table, resolves to that table's one alias + records a warning. Self-join tables still raise StructuredQueryBuildError on role=None.
src/validator/synonym_matching.py         ← NEW V0 (Story 5.9, Bug #13/DD-4). Single source of truth for source→synonym matching.
                                            Three pure functions: match_table_reference, match_hierarchy_role, table_has_hierarchy.
                                            Whole-word, case-insensitive. Used by join_resolver and table_column_validator.
src/validator/rule_applicator.py          ← NEW V0. run_rule_applicator(context, schema_repo, logger).
                                            Applies active_record, versioning, hierarchy conditions with alias prefix. Suppress token check. Deduplication. Emits VALIDATION_RESULT log.

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
                                    ← V1. Added JSON file mode alongside existing list mode.
                                      Constructor now accepts optional responses= list (old mode,
                                      unchanged) or no argument (new mode — loads from
                                      config/mock_responses.json). JSON mode extracts user query
                                      by splitting user_prompt on "User query:" label, matches
                                      exactly against user_input entries in JSON file.
                                      No match → ValueError. File missing/invalid → ValueError
                                      at construction time.

- src/llm/factory.py                ← NEW V0. LLMProviderFactory.
                                      Static method: LLMProviderFactory.create(settings)
                                      Reads settings.llm.provider to select provider.
                                      Mock imported at module level — always available.
                                      Real providers (openai, azure_openai, anthropic)
                                      imported lazily inside create() — missing files
                                      do not break imports during early development.
                                      Unknown provider → UnknownProviderError.
                                     ← V1. Added azure_foundry provider entry.
                                       Error message updated to list all 5 valid providers.

- src/llm/openai_provider.py        ← NEW V0. OpenAIProvider.
                                      Implements LLMProvider ABC. Synchronous — httpx.Client.
                                      Model: gpt-4o-mini. Retry + exponential backoff.
                                      Raises ValueError at construction if openai_api_key missing.
                                    ← V1 (Story 5.9, Bug #10). Reads settings.llm.temperature, sends it in request body.

- src/llm/azure_openai_provider.py  ← NEW V0. AzureOpenAIProvider.
                                      Implements LLMProvider ABC. Synchronous — httpx.Client.
                                    ← V1 (Story 5.9, Bug #10). Sends temperature in request body.

- src/llm/azure_foundry_provider.py  ← NEW V0. AzureFoundryProvider.
                                       Implements LLMProvider ABC. Synchronous — httpx.Client.
                                       URL: {endpoint}/chat/completions (no deployment in URL).
                                       Model name sent in request body as "model" field.
                                       3 credentials: AZURE_FOUNDRY_ENDPOINT,
                                       AZURE_FOUNDRY_API_KEY, AZURE_FOUNDRY_DEPLOYMENT_NAME.
                                       No api-version needed.
                                     ← V1 (Story 5.9, Bug #10). Sends temperature in request body.

- src/llm/anthropic_provider.py     ← NEW V0. AnthropicProvider.
                                      Implements LLMProvider ABC. Synchronous — httpx.Client.
                                     ← V1 (Story 5.9, Bug #10). Sends temperature in request body.

- src/pipeline/schema_summary.py    ← NEW V0. build_schema_summary(schema: AppSchema) -> str.
                                      Compresses AppSchema into plain-text for LLM prompt.
                                      Junction tables excluded entirely.
                                      Table format: table: Major.Customer [synonym1, synonym2]
                                      Column format with synonyms: CustomerCID [Customer id, Customer cid]
                                      Column format without synonyms: CustomerID (plain name)
                                      Column types, business rules, versioning excluded.
                                      Token budget: under 4,800 characters (~1,200 tokens).
                                      Output is deterministic — same input, same output.
- src/pipeline/intent_guard.py      ← NEW V0. run_intent_guard(context, logger).
                                      Whole-word case-insensitive keyword scan.
                                      Blocked keywords: DELETE, DROP, UPDATE,INSERT,TRUNCATE, ALTER, CREATE.
                                      Sets context.status="failed" + context.error on block.
                                      Emits INTENT_GUARD_RESULT log (passed + keywords_detected).
                                      Does not raise — always returns context. 

- src/pipeline/strategies/__init__.py ← NEW V0. Story 3.5
- src/pipeline/strategies/base.py     ← NEW V0. Story 3.5 NLToIRStrategy ABC. Two abstract methods: execute() and strategy_name().
                                          Mirrors LLMProvider ABC pattern exactly.
- src/pipeline/strategies/factory.py  ← NEW V0. NLToIRStrategyFactory. Lazy imports SingleCallStrategy (not yet built).
                                          Unknown strategy → UnknownStrategyError. registered_strategies() helper for health checks.
                                      ← V1. Registered SingleCallStrategy. Registry was empty in V0.
- src/pipeline/strategies/single_call.py← NEW V0. SingleCallStrategy.
                                            System prompt built once at construction.
                                            User prompt rendered per request.
                                            One LLM call per execute(). Parses simplified
                                            IR JSON. Writes to context.llm_output.
                                            Sets context.status = "success" on clean exit.
- src/pipeline/prompt_builder.py        ← NEW V0. PromptBuilder — three static methods:
                                          validate(), build_system_prompt(), render_user_prompt().
                                          Fixed rule assembly order: output → tables → columns →
                                          filters → source → limit → aggregation → sort.
                                          validate() checks: broken example set references,
                                          missing placeholders, incorrect/why_wrong pairing.
- src/pipeline/intent_guard.py          ← TO CREATE in Story 3.7
- src/pipeline/orchestrator.py          ← NEW V0. run_pipeline(context, schema_repo,
                                          llm_provider, logger, settings).
                                          Chains: App Identifier → Intent Guard → NL-to-IR Strategy.
                                          AppNotDeterminedError + MultipleAppsMatchedError caught
                                          here and converted to context failures.
                                          schema_repo.get_schema() failure caught defensively.
                                          Stops early if any stage sets context.status="failed".
                                          Emits REQUEST_RECEIVED log with caller="user".
                                          TODO (Story 5.4): add validator + SQL builder stages.
                                         ← V1. Added full validator chain (run_table_column_validator → run_join_resolver →       run_rule_applicator→ run_structured_query_builder) and run_sql_builder() after
                                            NL-to-IR stage. NL2SQLBaseError caught from validator chain
                                            and converted to context failure. Removed TODO marker.
                                            Pipeline now complete end-to-end (5 stages).
                                            Note: no src/validator/validator.py exists — four sub-stages
                                            chained directly, same pattern as validator_tool.py.

src/sql/select_builder.py   ← NEW V0. build_select(structured_query, default_top_rows) -> str.
                            Builds SELECT TOP N clause from StructuredQuery.columns.
                            Pads alias.ColumnName to max width so AS keywords align.
                            top_rows=0 or default_top_rows=0 → omits TOP clause.
                            Pure function — no logging, no LLM, no schema lookups.
src/sql/join_builder.py     ← NEW V0. build_join(structured_query) -> str.
                            Builds FROM {table} {alias} line from tables[0].
                            One INNER JOIN block per ResolvedJoin in joins list.
                            Single-condition: ON left = right.
                            Multi-condition (self-join): ON left = right / AND left = right.
                            Join order preserved exactly as given.
                            Empty tables list → returns "".
                            Pure function — no logging, no LLM, no schema lookups.
src/sql/where_builder.py    ← NEW V0. build_where(structured_query) -> str.
                              Builds WHERE clause from StructuredQuery.filters and applied_rules.
                              Filters rendered first (connectors respected: AND | OR).
                              Applied rules always appended after filters, always AND.
                              IS NULL / IS NOT NULL operators: value field ignored, no quotes.
                              All lhs padded with ljust(max_width) so operators align vertically.
                              _split_rule() extracts lhs from rule strings using ordered operator
                              list — handles ISNULL(c.DeletedFlag, 0) = 0 correctly.
                              Empty filters + empty rules → returns "".
                              Pure function — no logging, no LLM, no schema lookups.     
src/sql/sql_builder.py          ← NEW V0. run_sql_builder(context, logger, settings) -> QueryContext.
                                  Assembles SELECT + FROM/JOIN + WHERE into final SQL string.
                                  Calls build_select(), build_join(), build_where() in sequence.
                                  Stitches clauses with newline, appends semicolon.
                                  Reads settings.sql.default_top_rows as TOP fallback.
                                  structured_query=None → status="failed", SQL_BUILD_ERROR, no raise.
                                  Emits SQL_BUILT log on success.
                                  Pure assembly — no LLM, no schema lookups.                                                   

### Tests
- scripts/generate_mock_sql.py      ← NEW V0 (Story 5.8). Standalone helper (not a test).
                                      Runs each mock_responses.json entry through the full
                                      pipeline via TestClient + MockLLMProvider (JSON mode),
                                      prints resulting SQL to paste back as final_sql.
                                      Reads app_id from entry when present.

- test_e2e.py                 ← NEW V0 (Story 5.8). Golden E2E suite. TestGoldenExactMatch (Part A): golden query via
                                /v1/query + /v1/tools/query, exact SQL match, 8 log stages verified (VALIDATION_RESULT x3).
                                TestDataDriven (Part B): each mock_responses.json entry with final_sql asserted exactly.
                                TestDiagnostic: prints SQL per entry, no assertions.
                                ← V1. Root conftest.py fixes 401. LOG_DIR via monkeypatch before create_app() fixes empty log stages.
                                ← V2. _GOLDEN_SQL updated to actual output. A4 expects VALIDATION_RESULT x3 (one per validator sub-stage).
                                ← V3. _GOLDEN_SQL updated after join_resolver V2 fix — a_sub join now has single c.CustomerID condition.

- tests/conftest.py                 ← NEW V0 (Story 5.8). Root-level autouse fixture
                                      injects ENV, CLIENT_API_KEY, FOUNDRY_API_KEY,
                                      LLM_PROVIDER for all tests. tests/api/conftest.py
                                      only covered tests/api/** — test_e2e.py at root
                                      was getting 401. Same env vars, project-wide scope.
- tests/config/test_settings.py             ← new in 1.2 (33 tests)
                                            ← updated in 1.6 (log_dir assertion fixed)
                                            ← V2. Replaced step1/step2 token target refs.
                                              Updated _write_valid_base() helper to use
                                              nl_to_ir_strategy + prompt_example_set.
                                              Helper now also writes minimal prompts.yaml
                                              to tmp_path (Scenario 9 tests use tmp_path
                                              which has no real prompts.yaml).
                                              Added Scenario P (P1-P9): prompts.yaml loading.

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
- tests/validator/conftest.py               ← NEW V0. Fixtures: abc_schema_repo (session-scoped,
                                                loads real ABC_app.json), capturing_logger
                                                (in-memory CapturingLogger for log assertions),
                                                test_logger (real StructuredLogger writing to
                                                tmp_path — never touches project logs/).
- tests/validator/test_table_column_validator.py ← NEW V0. 13 tests:
                                                  A1-A4 table happy path, B1-B3 table failure,
                                                  C1-C3 column happy path, D1-D3 column failure,
                                                  E1-E3 ordering and logging.
                                                ← V1 (Story 5.9, Bug #13). Added TestPhantomDuplicateTables (P1–P6).
                                                ← V2 (Story 5.9, Bug #15). Added TestFilterValidation (F1–F6); extended make_context with filters=.
- tests/validator/test_structured_query_builder.py ← NNW V0 11 scenarios covering happy path, self-join alias resolution, error logging
                                                  ← V1 (Story 5.9, Bug #12). Added TestSingleInstanceFallback (SB-1–SB-5).
- tests/validator/test_join_resolver.py            ← NEW V0. 16 tests.
                                                  ← V2 (Story 5.9). Added TestSingleInstanceHierarchy (JR-S1–S4).
                                                   ← V3 (Story 5.9). Added JR-S5–S8 (role stamping on columns/filters for single-instance).
                                                    bridge, E1 no join path, F1-F4 alias generation, G1 logging.
                                                  ← V1 Added class H — 3 scenarios for role stamping on columns and filters
- tests/validator/test_rule_applicator.py         ← NEW V0. 19 tests: A1-A3 active record, B1-B2 versioning, C1-C3 hierarchy, D1-D3 suppress tokens,
                                                    E1 deduplication, F1 logging, plus TestQualifyCondition unit tests.
- tests/validator/test_synonym_matching.py  ← NEW V0 (Story 5.9). 8 scenarios: HM-1/2/3 hierarchy role match, HM-4 fused-word miss (documents Bug #14), HM-5 table_has_hierarchy, HM-6/7/8 table-reference matching.

- tests/api/test_models.py                  ← new in 2.3
- tests/api/test_auth.py                    ← new in 2.4 (A1-A5, B1-B5, C1-C3, D1-D2)
- tests/api/v1/test_query.py                ← NEW V0. 15 tests: A1-A3 auth, B1-B5 validation,
                                              C1-C4 success, D1-D2 business errors, E1 internal.
                                            ← V1. Groups A+B unchanged. Groups C, D, E
                                              rewritten for QueryContext response shape.
                                              MockLLMProvider injected into app.state after
                                              lifespan startup for success-path tests.
                                              D3 added: UNSUPPORTED_INTENT test.
                                            ← V2. Groups C, D, E rewritten for final QueryResponse shape.
                                              C1 correct top-level keys, C2 data.sql populated,
                                              C3 meta.app_id correct, C4 request_id echoed, C5 status=success.
                                              D1-D3 errors[] list (not context.error dict).
                                              E1 HTTP 500 errors[0].code=INTERNAL_ERROR.

- tests/api/tools/test_context_validator.py ← new in 2.5
                                              Groups: A1-A6, B1-B5, C1-C2, D1-D4, E1-E2, F1-F4
                                              + StageRequirements direct unit tests. All passing.
                                            ← V1. Replaced intent-extractor/schema-mapper
                                               tests with nl-to-ir tests. Updated validator tests for llm_output. Registry count: 6 → 5 stages.

- tests/api/tools/test_feedback_tool.py     ← new in 2.5. 2 tests: 501 + Phase 3 message.
- tests/api/tools/test_nl_to_ir_tool.py     ← NEW V0. 13 tests:
                                              A1-A4 auth, B1-B4 context validation,
                                              C1-C2 intent guard, D1-D3 success,
                                              E1 schema not found.

-tests/api/tools/test_validator_tool.py      ← NEW V0. New test file — mirrors test_nl_to_ir_tool.py pattern
                                            ← V1. 13 scenarios covering auth, field validation, business errors, success path, schema errors
-tests/api/tools/test_sql_builder_tool.py  ← NEW V0. 9 tests:
                                            A1 missing key → 401,
                                            A2 wrong key → 401,
                                            A3 client key on tool endpoint → 401,
                                            A4 correct foundry key passes auth,
                                            B1 structured_query=None → 400 MISSING_CONTEXT_FIELDS,
                                            D1 valid context → 200 sql populated contains SELECT,
                                            D2 response matches ToolResponse shape,
                                            D3 request_id echoed unchanged,
                                            D4 context.status="success".                                          
- tests/api/tools/test_query_tool.py  ← 19 tests across 5 groups (Auth, Context Validation,
                                      Intent Guard, Success, APP_NOT_DETERMINED). Group D
                                      overrides app.state.llm_provider inside the TestClient
                                      with block after lifespan runs.

- tests/llm/test_base.py                    ← NEW V0. 3 tests: A1-A3.
- tests/llm/test_mock_provider.py           ← NEW V0. 6 tests: B1-B6.
                                            ← V1. Added J1-J6 JSON mode scenarios alongside existing B1-B6 list mode tests. J tests use
                                              monkeypatch to redirect _MOCK_RESPONSES_PATH to tmp_path — never touch real config/mock_responses.json.
- tests/llm/test_factory.py                 ← NEW V0. 9 tests: C1-C7 (all passing after V2).
- tests/llm/test_openai_provider.py         ← NEW V0. 8 tests: D1-D8.
- tests/llm/test_azure_openai_provider.py   ← NEW V0. 11 tests: E1-E11.
- tests/llm/test_anthropic_provider.py      ← NEW V0. 8 tests: F1-F8.
- tests/llm/test_azure_foundry_provider.py  ← NEW V0. 11 tests: F1-F11. F11 is unique — verifies "model" field in request body (key Foundry difference).
- tests/pipeline/test_schema_summary.py     ← NEW V0. 10 tests: A1-A6, B1, C1-C4.
- tests/pipeline/strategies/__init__.py       ← NEW V0. in Story 3.5
- tests/pipeline/strategies/test_base.py      ← NEW V0. in Story 3.5 5 tests: A1-A4 + A2 extended.
- tests/pipeline/strategies/test_factory.py   ← NEW V0. in Story 3.5 5 tests: B1-B4 + B1 extended.
- tests/pipeline/test_prompt_builder.py       ← NEW V0. 16 tests: A1, B1-B5, C1-C5, D1-D3.
- tests/pipeline/strategies/test_single_call.py← NEW V0. 13 tests: A1-A3, B1-B7, C1-C3.
- tests/pipeline/test_intent_guard.py         ← NEW V0. 16 tests: pass-through (A1, A9, A10 +
                                                partial-word variants), block (A2-A8 + case variants),
                                                logging (A11 pass + block + request_id).
- tests/pipeline/test_orchestrator.py         ← NEW V0. 5 tests: B1 all three stages run,
                                                B2 non-select stops at Intent Guard,
                                                B3 unknown app stops at App Identifier,
                                                B4 status=success on clean run,
                                                B5 app_id populated after valid run.
                                              ← V1. Added B6-B9 to existing B1-B5.
                                                B6 full pipeline produces sql, B7 status=success with sql,
                                                B8 non-select sql=None, B9 unknown app sql=None.

tests/sql/test_select_builder.py    ← NEW V0. 8 tests: single column, multiple columns,
                                      user top_rows override, zero TOP (default and user),
                                      empty columns, AS alignment, golden Section 9.3 clause.
tests/sql/test_sql_builder.py           ← NEW V0. 7 tests: S1 sql populated, S2 SELECT TOP present
                                          (sets default_top_rows=10000 explicitly — not config-dependent),
                                          S3 FROM present, S4 INNER JOIN present, S5 WHERE present,
                                          S6 status=success, S7 missing structured_query → failed + SQL_BUILD_ERROR.

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

### Single-Call Strategy + Prompt Assembly (3.6)
- prompts.yaml is the single source of truth for all prompt text — nothing hardcoded in code
- YAML key 'schema' inside each example remapped to 'schema_' by _remap_example_schema_keys()
  in settings.py before Pydantic sees it — avoids collision with Pydantic's reserved attribute
- PromptExample uses model_config = ConfigDict(extra="forbid", populate_by_name=True) only —
  no inner class Config. Pydantic v2 rejects both model_config and class Config on same class.
- settings.prompts typed as Optional[Any] on Settings — Pydantic does not re-validate it.
  PromptsConfig already validated structure during _load_prompts().
- System prompt built once at SingleCallStrategy construction — reused across all requests.
  User prompt rendered per request (schema summary + user query substitution only).
- _parse_ir() strips markdown code fences before json.loads() — defensive against LLM wrapping
- context.status = "success" must be explicitly set by each stage on clean exit —
  QueryContext defaults to "pending", nothing sets it automatically.
- _REQUIRED_IR_KEYS = {tables, columns, filters, limit, aggregation, sort} —
  all six must be present in LLM response or LLMOutputParseError is raised.
- aggregation and sort captured in IR but NOT executed by SQL builder in Phase 1 — Phase 2.
- factory.py V1: SingleCallStrategy now registered. registered_strategies() returns
  ["single_call"]. Was empty list in V0.


### Partial Pipeline Wire-up + Intent Guard (3.7)
- Intent Guard: whole-word \b regex, case-insensitive, does not raise — sets
  context.status="failed" and returns. Emits INTENT_GUARD_RESULT always.
- Blocked keywords: DELETE, DROP, UPDATE, INSERT, TRUNCATE, ALTER, CREATE.
  REMOVE and CANCEL excluded — not SQL keywords, would cause false positives.
- Partial words (deleted, updates, created) correctly pass — \b boundary handles this.
- Orchestrator catches AppNotDeterminedError + MultipleAppsMatchedError from
  run_app_identifier() and converts to context failures. Callers never see raw
  business exceptions — always receive a context object.
- run_pipeline() signature: (context, schema_repo, llm_provider, logger, settings).
  settings required by NLToIRStrategyFactory to select strategy and example set.
- REQUEST_RECEIVED log emitted inside run_pipeline() with caller="user".
  query.py V0 duplicate emit removed in V1.
- app.state.llm_provider set at startup in app.py V2 via LLMProviderFactory.
  Tests inject MockLLMProvider into app.state after lifespan startup fires.
- query.py response shape: temporary full QueryContext dict. Final QueryResponse
  shape wired in Story 5.4. TODO marker in query.py flags this explicitly.
- Business errors return HTTP 200 with context.status="failed" and context.error
  dict (code + message). Not errors[] list — that is the final QueryResponse shape.
- HTTP 500 only for unexpected exceptions (RuntimeError etc.) that escape run_pipeline().

### Mock Provider JSON Mode (between 3.6 and 3.7)
- Option B chosen — both modes coexist. responses=[] → list mode (unchanged).
  No argument → JSON file mode (new).
- JSON file hardcoded at config/mock_responses.json — single location, always known.
- Matching is exact and case-sensitive — "clients" never matches synonym "customer".
- Extraction splits user_prompt on "User query:" label (fixed text from user_template
  in prompts.yaml). maxsplit=1 ensures only first occurrence used.
- File missing or invalid JSON → ValueError at construction time — fails fast.
- No match found → ValueError at complete() time — same behaviour as list mode exhaustion.
- _MOCK_RESPONSES_PATH and _USER_QUERY_LABEL are module-level constants — monkeypatched
  in tests so real file is never touched by test suite.
- prompts.yaml: strict synonym matching rule needed in rules.tables — LLM must only
  match user terms against display name or synonyms[], never semantic similarity.
  Negative example added: "clients" must not map to Major.Customer.
  Example name: strict_synonym_matching. Added to default example_set.

### NL-to-IR Tool Endpoint (4.1)
- Auth uses Depends(require_foundry_key) in route signature — NOT called
  manually in the handler body. FastAPI resolves the nested
  Depends(_api_key_header) automatically. Manual call would bypass header
  extraction and break auth entirely.
- ContextValidator instance created once at module level (_context_validator)
  — reused across all requests. Same pattern will apply to all tool endpoints.
- Intent Guard failure → HTTP 200 with ToolResponse (business error rule).
- Schema not found → HTTP 500 with ToolResponse (unexpected internal error).
- REQUEST_RECEIVED log emitted with caller="foundry" — distinguishes tool
  endpoint calls from user-facing /v1/query calls in the log file.

### Table & Column Validator (4.2)
- resolved_tables and resolved_columns changed from list[str] to list[dict]
  in models.py V2. Stores full llm_output entry dicts including source field.
  list[str] would have lost source, breaking hierarchy role assignment in
  Story 4.3 (join resolver matches source against schema hierarchy synonyms).
- resolved_filters also changed to list[dict] in same V2 update — same
  reasoning, avoids a breaking change mid-Story 4.4.
- Table matching is exact name only (e.g. "Major.Customer") — not synonyms.
  LLM sees real table names in schema summary and echoes them back.
  Synonyms are for App Identifier only (free-form user text → app).
- Junction tables rejected even if name is valid in schema. LLM must never
  propose them — join resolver auto-bridges them in Story 4.3.
- Table validation runs before column validation. Any invalid table raises
  NoRelevantTablesError immediately — column check never runs.
- Self-join duplicates (Major.Acc twice) preserved in resolved_tables —
  both entries kept so join resolver can read source for role assignment.
- CapturingLogger pattern introduced in tests/validator/conftest.py —
  in-memory logger for asserting log stage and payload without file I/O.
  Will be reused in all subsequent validator test stories.

### Join Resolver  (4.3)
- Resolved_joins shape: list[dict] with consistent on_conditions: list[dict] for all joins (single or multi-condition). SQL builder renders AND between multiple conditions. on_left/on_right flat fields rejected — cannot represent multi-condition self-joins.
- Self-join second instance collects ALL conditions into one join dict: primary self-relationship (a_top.AccID = a_sub.ParentAccID) plus additional direct relationships from all other anchored tables (c.CustomerID = a_sub.CustomerID). Single INNER JOIN Major.Acc a_sub ON ... AND ... in output.
- Alias generation fully schema-driven — no hardcoding. Priority: _ split → starts uppercase (CamelCase initials) → all lowercase (first 3 chars). Single-word uppercase names (Customer → c, Acc → a) correctly handled by checking display_name[0].isupper() not "has uppercase after char 0".
- Hierarchy role assigned by matching source field against schema hierarchy synonyms (case-insensitive whole-word). Role written back into resolved_tables entry as "role" key alongside "alias" key. No match → warning logged, alias auto-generated (a, a_2), no error raised.
- Junction auto-bridging: junction table appears in resolved_joins only — never added to resolved_tables.
- Single table query: alias assigned, resolved_joins = [], no error.

### Rule Applicator  (4.4)
- Applied_rules: list[str] kept — simple SQL strings, SQL builder drops them directly into WHERE. No rule_type dict — complexity not justified since all rules go into WHERE regardless of type.
- Suppress tokens checked per-table against nl_query_original (case-insensitive substring). Only active_record rules suppressed — versioning and hierarchy conditions always applied.
- _qualify_condition() scans all uppercase-starting tokens, skips known SQL keywords/functions using word.upper() in _SQL_KEYWORDS (case-insensitive), prefixes only the first non-keyword token (the column). Handles ISNULL, isnull, Isnull correctly.
- Deduplication via seen: set[str] — exact string match. c.VersionTermDate IS NULL appearing in both active_record and versioning.active_condition - correctly deduplicated to one entry.
- Rule applicator depends on aliases already set by join resolver — must run after 4.3 in pipeline.

### Structured Query Builder (4.5)
- (table, role) composite key used for alias lookup in structured query builder. Non-self-join tables use (table, None) — same pattern handles both cases uniformly.
- Role stamped in join_resolver (not query builder) — single source of truth. Same _match_hierarchy_role() function used for tables, columns, and filters.
- Fail fast on ambiguous self-join — StructuredQueryBuildError raised if a column or filter on a self-join table has role=None. Silent wrong SQL is worse than a clear error.
- output_alias defaults to column name in Phase 1. Phase 3 extension point for user-specified aliases ("name as Name").
- Error logged before raising in structured_query_builder — STRUCTURED_QUERY_BUILT log stage emitted with status: failed before exception propagates to orchestrator.

### Validator Tool Endpoint (4.6)
- SchemaLoadError caught separately before NL2SQLBaseError — infrastructure error returns HTTP 500. Business errors return HTTP 200. Order of except blocks matters: specific before general.
- SCHEMA_LOAD_ERROR returned on unknown app_id — more informative than generic INTERNAL_ERROR. Test corrected to match.
- Single NL2SQLBaseError handler for all business errors — covers all four validator stages. Tech debt comment added for future split if HTTP codes diverge.

### Select Builder (5.1)
- build_select() trusts output_alias exactly as given — no defaulting logic here.
  Defaulting output_alias to column_name is structured_query_builder.py's responsibility (4.5).
- TOP logic: structured_query.top_rows takes precedence over default_top_rows.
  Effective value of 0 (either source) → TOP clause omitted entirely.
- Alignment: all alias.ColumnName parts padded with ljust(max_width) so AS keywords
  align vertically — matches golden SQL formatting in architecture Section 9.3.
- Trailing comma on every column line except the last.
- Empty columns list → returns header only, no crash.
- Returns SELECT clause string only — FROM/JOIN/WHERE assembled by sql_builder.py (Story 5.4).

### Join Builder (5.2)
- build_join() reads tables[0] as the FROM table — order is the contract, not a name match.
- Multi-condition joins handled by iterating on_conditions: idx==0 → ON, idx>0 → AND.
  No special self-join branching — the on_conditions list length drives the output naturally.
- join_type field drives the JOIN keyword — "INNER JOIN" is the only value in Phase 1.
  Phase 2+ can pass a different join_type without any code change.
- Empty tables list → empty string, no crash. Caller (sql_builder.py, Story 5.4)
  is responsible for ensuring tables is non-empty before calling.
- Junction table test confirms PackagePlan appears in JOIN output but not in FROM —
  consistent with junction auto-bridging rule: junction tables live in joins only.

### Where Builder (5.3)
- connector: str = "AND" added to ResolvedFilter — default "AND" so zero impact on
  existing code. First filter in list never emits a connector regardless of its value.
- Applied rules are always AND — business rules are never ORed. Connector field
  exists only on ResolvedFilter, not on applied_rules strings.
- IS NULL / IS NOT NULL: value field silently ignored. No quotes rendered.
  _VALUELESS_OPERATORS set used for the check.
- _split_rule() uses ordered _RULE_SPLIT_OPERATORS list to find lhs boundary.
  "IS NOT NULL" must come before "IS NULL" in the list — longer operators first
  to avoid partial matches. Same principle as regex alternation ordering.
- Alignment: lhs padded with ljust(max_width) where max_width = widest lhs across
  all conditions (filters + rules). ISNULL(c.DeletedFlag, 0) = 24 chars drives
  the max in the golden query.
- T11 alignment assertion removed — ljust() padding produces consecutive spaces
  indistinguishable from the separator by string search. Alignment verified by
  dry-run; test covers correctness of conditions and connectors instead.
  
### SQL Orchestrator & Final Pipeline Wire-up (5.4)
- No src/validator/validator.py exists — four validator sub-stages chained directly
  in orchestrator, same pattern as validator_tool.py. Architecture doc describes
  run_validator() as logical behaviour, not a file name.
- NL2SQLBaseError used as single catch in orchestrator validator chain — covers
  NoRelevantTablesError, NoJoinPathError, StructuredQueryBuildError and all other
  business errors from the four sub-stages.
- settings.sql.default_top_rows = 0 in dev config — TOP clause omitted when 0.
  Tests that assert SELECT TOP must set default_top_rows=10000 explicitly and never
  rely on config value.
- _build_response() extracted as private helper in query.py — used by both the
  success path (HTTP 200) and the internal error path (HTTP 500) to ensure the
  Section 10.3 envelope shape is consistent in all responses.
- RESPONSE_SENT log emitted at end of query.py after pipeline completes.
- errors[] in QueryResponse is populated from context.error dict (set by orchestrator).
  Single error entry on failure, empty list on success.

### SQL Builder Tool Endpoint (5.5)
- stage_name in ContextValidator registry uses hyphens ("sql-builder") — must match exactly. Underscore variant ("sql_builder") raises ValueError → 500. Hyphen isthe convention for all stage slugs matching URL path segments.
- _GOLDEN_STRUCTURED_QUERY in tests must use exact Pydantic field names: table_name (not name) for ResolvedTable and ResolvedJoin.422 is the signal that field names in the test payload don't match the model.
- No Group C (business error) tests — run_sql_builder() has only one pre-condition guard (structured_query is None) which is already covered by B1 at the HTTP layer. Internal SQL builder logic is tested in tests/sql/test_sql_builder.py.

### App Identifier Tool Endpoint (5.6)
- nl_query_original is str (required, no default, not Optional) on QueryContext.
  Sending None → Pydantic 422 before handler runs. Cannot reach ContextValidator.
  Test B1 asserts 422 — that is the correct protection, just enforced by Pydantic.
  Empty string "" → passes Pydantic, caught by ContextValidator → 400.
- run_app_identifier() does not set context.status="success" — endpoint is
  responsible for marking the final outcome after successful return.
- Intent Guard runs before app identifier — non-select queries blocked before
  any schema matching occurs. app_id remains "" on UNSUPPORTED_INTENT.
- Business errors (APP_NOT_DETERMINED, MULTIPLE_APPS_MATCHED) → HTTP 200 with
  error in context. Never HTTP 4xx for business logic failures.

### Full Pipeline Tool Endpoint (tools/query) (5.7)
- Story 5.7: Why tools/query exists alongside /v1/query — Both call run_pipeline(). The difference is auth key (FOUNDRY_API_KEY vs CLIENT_API_KEY) and response shape (ToolResponse with full QueryContext vs QueryResponse with clean SQL-focused shape). Foundry agent needs the full context to inspect every field.
- Story 5.7: LLM override timing in tests — app.state.llm_provider must be overridden INSIDE the with TestClient(app) as client: block, on the line after it opens. Lifespan runs when the block opens and overwrites any pre-open override. Setting it after open means lifespan is done and the override sticks.
- Story 5.7: Individual tool endpoints vs tools/query — Foundry agent has two modes: call stages one-by-one (fine-grained inspection) or call tools/query for one-shot full pipeline. Both patterns are supported.

### Golden E2E Test (5.8)
- E2E suite split into three classes: Part A (exact SQL + log stage verification, must never fail), Part B (data-driven from mock_responses.json with final_sql), Diagnostic (print-only, no assertions, run with pytest -s).
- New test cases need NO code change — add a mock_responses.json entry with user_input, llm_response, final_sql (and app_id if no "in ABC" in query).
- Root tests/conftest.py required — tests/api/conftest.py scope is tests/api/** only.
  E2E lives at tests/ root and was returning 401 until root conftest added.
- LOG_DIR must be set via monkeypatch BEFORE create_app() — load_settings() reads
  LOG_DIR inside lifespan when the TestClient block opens. Setting it after = too late.
- Validator chain emits VALIDATION_RESULT three times (table/column validator,
  join resolver, rule applicator) — expected stage list must account for all three.
- A2 reads SQL from data["context"]["sql"] (ToolResponse shape); A1 reads from
  data["data"]["sql"] (QueryResponse shape). Same SQL, different envelope per endpoint.

### Key Decisions Made — Story 5.9
- DD-1: Column-first table derivation — REJECTED. Confirmed against the real IR: the COUNT target table lives ONLY in llm_output.tables (see prompts.yaml aggregation_with_limit example), so deriving tables from columns+filters loses it; also loses filter-only and junction/bridge tables. Evidence-based rejection.
- DD-2: Aggregation-switch derivation (use LLM list only when aggregation present) — REJECTED. Two code paths, fixes only the COUNT hole, branches on a signal that doesn't predict when the LLM list is needed; collapses into Path A anyway.
- DD-3: Table source-of-truth = trust the LLM tables list and CLEAN it (Path A). It is the only structure carrying column-tables, filter-only tables, and COUNT-target tables. Permanent design, not a stopgap.
- DD-4: Matching logic lives in ONE shared module (synonym_matching.py), used by both join_resolver and table_column_validator. So the Phase-2 fused-word upgrade happens in one place and stays generic across app schemas.
- Filter validation strictness (Bug #15): a filter referencing a column/table not in the proposed set raises NoRelevantColumnsError (same hard-fail as columns).
- Bug #16 handling: keep loud failure (no silent guessing). Deferred to the LLM-Reliability story.

### Known Issues / Deferred
- Bug #14 — fused hierarchy words ("subaccount", "topaccount") don't match a role under whole-word matching → DEFERRED to LLM-Reliability story.
- Bug #16 — LLM omits or misroutes the filter table (drops Major.Customer, or forces the customer filter onto Major.Acc.CustomerID) → causes correct loud failure (Stage 3 reject, or self-join ambiguity guard). DEFERRED to LLM-Reliability story.
- KI-2 — Bug #13 may silently drop a legitimate fused-word duplicate. Resolved once Bug #14 lands.
- KI-6 — mitigated: matching logic centralised in synonym_matching.py (single upgrade point).


### Working Rule Reminder (3.7)
- Before writing any code, ask for ALL files the new code depends on that have
  not been seen this session. One upload request upfront. No exceptions.

### Bug Fix (schema_repository.py — 2.4)
- SchemaLoadError calls fixed from SchemaLoadError(code=..., message=...)
  to SchemaLoadError(message=...) — code auto-injected from constants
### Bug Fix (prompts_models.py — 3.6)
- PromptExample had duplicate model_config declarations and an inner class Config block
  (Pydantic v1 style). Pydantic v2 raises PydanticUserError: "Config" and "model_config"
  cannot be used together. Fixed in V1 — single model_config = ConfigDict(...) only.

### Bug Fix (single_call.py — 3.6)
- context.status was never set to "success" after clean execute(). QueryContext defaults
  to "pending". Added context.status = "success" before the log emit and return.

### Bug Fix (test_query_tool.py — 3.6)
- Story 5.7: Factory MockLLMProvider placeholder — LLMProviderFactory.create() returns MockLLMProvider(responses=["mock_response"]) — a placeholder string, not valid IR JSON. Success tests that reach the LLM stage must override app.state.llm_provider with MockLLMProvider(responses=[_GOLDEN_IR]) inside the TestClient block. Tests that stop before the LLM (auth, validation, intent guard, app-not-determined) use the factory default unchanged.

### Bug Fix (join_resolver.py — 5.8)
- Self-join additional-conditions block ran forward (a_schema→t_name) and reverse
  (t_schema→a_name) relationship lookups unconditionally. When the same relationship
  exists on both sides of the schema (Customer↔Acc CustomerID), both lookups matched
  and c.CustomerID = a_sub.CustomerID was added twice. Fixed: reverse lookup is now
  an else-branch fallback, runs only when forward lookup returns nothing. Surfaced by
  golden E2E test A1/A2 — duplicate AND line in the a_sub INNER JOIN ON clause.


### Bug Fixes — Story 5.9
- Bug #7  — single-instance hierarchy role not stamped on table entry → fixed (join_resolver V3)
- Bug #8/#9 — strict synonym prompt reinforcement + negative example → fixed (prompts.yaml V1)
- Bug #10 — temperature not configurable → fixed (settings + 4 providers)
- Bug #11 — second prompt example → fixed
- Bug #12 — single-instance hierarchy column/filter alias unresolved (empty ".AccName") → fixed (structured_query_builder V1 single-instance fallback)
- Bug #13 — phantom DUPLICATE table entries (LLM emits a table twice, second is a column ref like "accKey") → fixed (table_column_validator V1, drop phantom duplicates via shared matcher)
- Bug #15 — user filters never copied into resolved_filters (silently lost, never reached WHERE) → fixed (table_column_validator V2, Stage 3 filter validation + pass-through)


### Azure AI Foundry Provider (Adhoc added)
- Static api-key header used — same pattern as all other providers
- URL pattern: {endpoint}/chat/completions — no deployment name in URL
- Model name goes in request body as "model" field — key difference from azure_openai
- No api-version query param needed — Foundry endpoint does not require it
- 3 credentials only (vs 4 for azure_openai — no api_version)
- Response shape identical to OpenAI: choices[0].message.content
- To activate: set LLM_PROVIDER=azure_foundry in .env
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

### Story  (Architecture v1.7)
- Updated Section 6.3 — QueryContext field descriptions

### Story 4.5 (Architecture v1.8)
-Updated Section 2.3 Tech Debt Added pt 3 -6.

---

### Story 5.8 (Architecture v1.9)
- Section 2.3 Tech Debt — added items 7–11 (single-instance hierarchy, schema
  vocabulary gap, LLM semantic matching, temperature config, second prompt example).
- Section 9.3 — verified golden SQL matches actual pipeline output (no TOP 10000,
  AS AccName aliases, a_sub includes c.CustomerID condition, per-Acc TermDate).