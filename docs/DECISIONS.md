# Key Decisions

A log of the significant engineering decisions made while building nl2sql-engine,
organised by component (story number in parentheses). Each entry records what was
decided and why.

---

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
- StageRequirements Acme + @final validate() — subclasses define fields, never logic
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
- Should be refactored to LogWriter Acme + factory + config key before Phase 2
- Tracked as tech debt — not blocking Phase 1

### LLM Base & Factory (3.1)
- LLMProvider is an Acme — cannot be instantiated directly
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
- NLToIRStrategy Acme mirrors LLMProvider Acme exactly — same pattern, same rationale
- NLToIRStrategyFactory uses lazy imports for SingleCallStrategy — same pattern as LLMProviderFactory. Strategy files can be absent during    early stories without breaking imports.
- Factory in this story has an empty registry until Story 3.6 adds SingleCallStrategy. registered_strategies() returns [] until then — this is correct and tested (B4).
- _PatchedFactory test pattern used in test_factory.py — injects a stub strategy to test the factory mechanism without needing SingleCallStrategy to exist.
context_validator.py now has exactly 5 stages: app-identifier, nl-to-ir, validator, sql-builder, query.
- intent-extractor and schema-mapper stage names are gone — any agent sending those names will receive a ValueError (programming error, not a pipeline error).
- total_latency_ms: int = 0 added to QueryContext in this story — was in the architecture doc but missing from V0 models.py.
- QueryContext: intent_output + mapping_output removed → single llm_output field ✅
- NLToIRStrategy Acme + NLToIRStrategyFactory — Strategy pattern mirrors LLMProviderFactory ✅
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
- New test cases need NO code change — add a mock_responses.json entry with user_input, llm_response, final_sql (and app_id if no "in Acme" in query).
- Root tests/conftest.py required — tests/api/conftest.py scope is tests/api/** only.
  E2E lives at tests/ root and was returning 401 until root conftest added.
- LOG_DIR must be set via monkeypatch BEFORE create_app() — load_settings() reads
  LOG_DIR inside lifespan when the TestClient block opens. Setting it after = too late.
- Validator chain emits VALIDATION_RESULT three times (table/column validator,
  join resolver, rule applicator) — expected stage list must account for all three.
- A2 reads SQL from data["context"]["sql"] (ToolResponse shape); A1 reads from
  data["data"]["sql"] (QueryResponse shape). Same SQL, different envelope per endpoint.

### Key Decisions Made —  (5.9)
- DD-1: Column-first table derivation — REJECTED. Confirmed against the real IR: the COUNT target table lives ONLY in llm_output.tables (see prompts.yaml aggregation_with_limit example), so deriving tables from columns+filters loses it; also loses filter-only and junction/bridge tables. Evidence-based rejection.
- DD-2: Aggregation-switch derivation (use LLM list only when aggregation present) — REJECTED. Two code paths, fixes only the COUNT hole, branches on a signal that doesn't predict when the LLM list is needed; collapses into Path A anyway.
- DD-3: Table source-of-truth = trust the LLM tables list and CLEAN it (Path A). It is the only structure carrying column-tables, filter-only tables, and COUNT-target tables. Permanent design, not a stopgap.
- DD-4: Matching logic lives in ONE shared module (synonym_matching.py), used by both join_resolver and table_column_validator. So the Phase-2 fused-word upgrade happens in one place and stays generic across app schemas.
- Filter validation strictness (Bug #15): a filter referencing a column/table not in the proposed set raises NoRelevantColumnsError (same hard-fail as columns).
- Bug #16 handling: keep loud failure (no silent guessing). Deferred to the LLM-Reliability story.

### Known Issues / Deferred
- Bug #14 (partial) — fused forms "topacc", "topaccs", "subacc", "subaccs" now added to
  Acme_app.json as explicit synonyms (both table-level and hierarchy level). "subaccount" /
  "topaccount" still deferred — would require updating the negative_strict_synonym prompt
  example which currently treats them as negative examples.
- Bug #16 — LLM omits or misroutes the filter table (drops Major.Customer, or forces the
  customer filter onto Major.Acc.CustomerID) → causes correct loud failure. Prompt example
  customer_name_filter_table added (prompts.yaml V3) as prevention. DEFERRED if LLM ignores it.
- KI-6 — mitigated: matching logic centralised in synonym_matching.py (single upgrade point).

### Feedback Endpoint Response Shape (6.1)
- POST /v1/feedback returns {request_id, status, errors} only — no data/meta blocks.
- data/meta describe a SQL result (sql, app_id, tokens, latency) — none of those
  fields apply to feedback submission. Using them would require inventing meaningless
  values or making fields Optional when they are required everywhere else.
- A dedicated FeedbackResponse model is deferred to Story 6.4 (Response Consistency
  audit) — if one is needed it will be decided there.
- user_id="" in the logged LogEntry — FeedbackRequest carries no user_id. Empty string
  follows the same "not populated" convention as QueryContext.app_id = "".

### Global Exception Handler (6.2)
- register_exception_handlers(app) called in create_app() immediately after
  FastAPI() instantiation, before all routers — ensures handlers are in place
  before any route can raise.
- HTTPException and RequestValidationError explicitly delegated back to FastAPI's
  built-in handlers inside _handle_unhandled_exception. Without this guard,
  registering an Exception handler intercepts all FastAPI-internal exceptions
  including auth 401s and Pydantic 422s.
- MissingContextFieldsError response uses exc.message (curated, includes missing
  field names) — architecture Section 13.1 says response body must list missing
  fields so agent can fix its call.
- Exception (500) response uses a fixed safe generic message — raw error detail
  goes to log only, never to caller.
- _try_log() wraps StructuredLogger in try/except — logging failure can never
  prevent the structured error response from being returned.
- Middleware only fires when exception escapes a route handler. Properly handled
  business errors (caught inside pipeline/route) are logged by the route handler
  — no double-logging, no missed logging.
- Test-only throw routes added via app.add_api_route() inside tests — standard
  FastAPI pattern, keeps production code clean.

### Apps Endpoint Response Shape (6.3)
- GET /v1/apps returns {request_id, status, data: {apps: [...]}, errors}.
  No meta block — no SQL result, token count, or latency to report.
- Each app entry: {app_id, version}. AppSchema.appId (camelCase from JSON)
  normalised to snake_case app_id in the response — consistent with the
  convention used everywhere else in the API (QueryContext, QueryResponse).
- request_id generated fresh per call — GET has no body to read one from.
- schema_repo None handled by raising RuntimeError, caught by global
  exception handler (Story 6.2) → HTTP 500. Consistent with query.py's
  same broken-startup guard pattern.  

### API Response Consistency Audit (6.4)
Audit results:
- query.py V2: final QueryResponse shape confirmed, Story 3.7 TODO removed. ✅
- feedback.py V0: {request_id, status, errors} — correct minimal envelope. ✅
- apps.py V0: {request_id, status, data, errors} — correct. ✅
- All 5 tool endpoints: ToolResponse shape on success/business-error paths. ✅
- feedback_tool.py: 501 placeholder — intentionally minimal, Phase 3 concern. ✅

One inconsistency fixed:
- All 5 tool endpoints had a route-level except MissingContextFieldsError block
  that returned {status, errors, missing_fields} — missing request_id, non-standard
  top-level key.
- Fix: removed the route-level catch from all 5 files. MissingContextFieldsError
  now propagates to global exception handler (middleware.py, Story 6.2) which
  returns the correct {request_id, status, errors} envelope.

middleware.py V1 — missing_fields inside errors[0]:
- After removing route-level catches, structured missing_fields list was only
  available in exc.message as text.
- Architecture Section 13.1: response body must list exactly which fields are
  missing so agent can fix its call.
- Decision: expose exc.missing_fields as a structured list INSIDE errors[0]
  (not at top level). Top-level envelope stays clean. Agent gets machine-readable
  field list. No non-standard top-level keys.
  Response shape: {request_id, status,
                   errors: [{code, message, missing_fields: [...]}]}

### Foundry Tool Integration Tests (6.5)
- A1 is one comprehensive test method with four sequential steps. Error
  messages include step number so failures are immediately diagnosable.
- E2 (nl-to-ir Intent Guard test) pre-populates app_id and app_schema_version
  so ContextValidator passes first — Intent Guard then fires as expected.
  Without pre-population, validator would return 400 before Intent Guard runs.
- D1 confirms: when app_id is pre-populated in the context, run_pipeline()
  inside tools/query uses it correctly — the pipeline does not blindly reset
  fields that are already set.
- No new source files created or modified — Story 6.5 is test-only.
- No tools-specific conftest needed — tests/api/conftest.py (autouse env vars)
  covers all tests/api/** including tests/api/tools/ via pytest scope rules.

### Full API Integration Test (6.6)
- Story 6.6 is a sweep test — confirms breadth across the entire API, not
  depth. Deep testing is handled by endpoint-specific test files.
- All test key values (test-client-key-12345, test-foundry-key-67890) are
  mock-only values already present in tests/api/conftest.py — safe for
  public GitHub. Real secrets live in .env (gitignored) and are never
  read by the test suite.
- No source files created or modified — Story 6.6 is test-only.
- pytest tests/api/ passes as a full suite — test isolation confirmed,
  no env var leakage between tests.
  
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

### Bug Fix (join_resolver.py V6 — deferred join)
- Strict sequential for-loop raised NoJoinPathError immediately when a table could
  not join the current anchor set, even when a valid path existed via a table that
  appeared later in the LLM output (e.g. CustomerDemographics before Customer).
  Fixed: replaced for-loop with a multi-pass deferred algorithm (Kahn-style topological
  resolution). Each pass defers unjoinable tables to a pending list; they are retried
  after each successful anchor. NoJoinPathError raised only after a full pass produces
  zero progress — genuine no-path detection without false positives.
  Extracted _try_join_instance helper (self-join / direct / junction bridge strategies).
  All join logic remains fully schema-driven — zero hardcoding. No behaviour change for
  tables that were already joinable in order (all existing tests unaffected).
  35/35 join resolver tests pass.
  Bug report: bup-reports/BUG-2026-06-06-deferred-join-out-of-order-tables.md


### Bug Fixes — Story 5.9
- Bug #7  — single-instance hierarchy role not stamped on table entry → fixed (join_resolver V3)
- Bug #8/#9 — strict synonym prompt reinforcement + negative example → fixed (prompts.yaml V1)
- Bug #10 — temperature not configurable → fixed (settings + 4 providers)
- Bug #11 — second prompt example → fixed
- Bug #12 — single-instance hierarchy column/filter alias unresolved (empty ".AccName") → fixed (structured_query_builder V1 single-instance fallback)
- Bug #13 — phantom DUPLICATE table entries (LLM emits a table twice, second is a column ref like "accKey") → fixed (table_column_validator V1, drop phantom duplicates via shared matcher)
- Bug #15 — user filters never copied into resolved_filters (silently lost, never reached WHERE) → fixed (table_column_validator V2, Stage 3 filter validation + pass-through)

### Bug Fix (table_column_validator.py V3 — role-duplicate table entries)
- LLM emitted one Major.Acc table entry per column (4 entries for 2 columns × 2 roles),
  all passing phantom-drop because all matched hierarchy synonyms. Result: 4 JOIN clauses
  instead of 2. Fixed by adding seen_roles tracking in _drop_phantom_duplicates: once a
  hierarchy role is represented, any later entry for the same role is dropped with a warning.
  Column entries are unaffected — all columns still appear in resolved_columns.
  28/28 validator tests pass. Full suite: 808 passed, 0 failed.
  Bug report: bup-reports/BUG-2026-06-06-role-duplicate-table-entries.md

### Bug Fix (structured_query_builder.py V2 — output_alias dedup)
- Both AccName columns from top_Acc and sub_Acc previously emitted AS AccName in the SELECT
  clause — ambiguous SQL. Fixed: for columns on a self-join table with a known role,
  output_alias = role.split("_")[0] + column_name (e.g. topAccName, subAccName).
  Non-self-join and single-instance columns are unaffected.
  21/21 structured_query_builder tests pass. E2E golden SQL updated to reflect new aliases.
  Full suite: 808 passed, 0 failed.

### Bug Fix (schemas/Acme_app.json + prompts.yaml V3 — fused synonyms + CustomerName filter)
- Added fused synonym forms topacc, topaccs, subacc, subaccs to Major.Acc table-level and
  hierarchy level synonyms in Acme_app.json. Enables LLM to match fused-word user terms
  to the correct hierarchy role without relying on whole-word multi-token matching.
- Added customer_name_filter_table example to prompts.yaml V3. Demonstrates CustomerName
  lives on Major.CustomerDemographics, not Major.Customer — prevents LLM from assigning
  the filter to the wrong table.
- Pre-existing test_a5 failure resolved: test_schema_summary.py V1 updated assertion to
  match current schema (CustomerName [Customer name, customername]).
  Full suite: 808 passed, 0 failed.


### Bug Fix (prompts.yaml V4 — column table exact match)
- LLM was emitting an inconsistent tables array: for a source phrase like "top customername",
  it put Major.Customer in the tables array but correctly identified the column CustomerName
  as belonging to Major.CustomerDemographics in the columns array. The self-verification rule
  at columns line 85 already said "add it if missing" but the LLM treated Major.Customer as
  a substitute because the names share a word — it never added Major.CustomerDemographics.
  Fixed: split the single columns rule into two bullets. First bullet: EXACT table name match
  required. Second bullet: a related table with a similar name is NOT a substitute — add the
  column's actual table if missing, even if another table is already present for the same phrase.
  Added column_table_exact_match example showing the incorrect pattern (Major.Customer in tables,
  Major.CustomerDemographics in columns) and why it is wrong. No source code changed — prompt only.
  Registered in both default and minimal example_sets.
  Bug report: bug-reports/BUG-2026-06-06-column-table-mismatch.md

### Azure AI Foundry Provider (Adhoc added)
- Static api-key header used — same pattern as all other providers
- URL pattern: {endpoint}/chat/completions — no deployment name in URL
- Model name goes in request body as "model" field — key difference from azure_openai
- No api-version query param needed — Foundry endpoint does not require it
- 3 credentials only (vs 4 for azure_openai — no api_version)
- Response shape identical to OpenAI: choices[0].message.content
- To activate: set LLM_PROVIDER=azure_foundry in .env
