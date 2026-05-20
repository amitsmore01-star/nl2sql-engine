# SESSION_CONTEXT.md

## Completed Stories (all tests passing)
- 1.1 ✅ Project Scaffold
- 1.2 ✅ Configuration
- 1.3 ✅ Schema Models
- 1.4 ✅ Schema Repository & Validator

## Current Sprint
Sprint 1 — Foundation

## Current Story
1.5 — Health Check API

## Files Built So Far

### Project Root
- main.py
- requirements.txt
- .env.example
- .gitignore
- README.md

### Config
- config/settings.base.yaml        ← updated in 1.2 (added llm.provider to base)
- config/settings.dev.yaml
- config/settings.prod.yaml

### Schemas
- schemas/ABC_app.json

### Source
- src/config/settings.py           ← new in 1.2
- src/schema/schema_models.py      ← new in 1.3 (43 tests, all passing)
- src/schema/schema_repository.py
- src/schema/schema_validator.py
- src/core/exceptions.py          ← SchemaLoadError only — rest added in 2.1


### Tests
- tests/config/test_settings.py    ← new in 1.2 (33 tests, all passing)
- tests/schema/test_schema_models.py ← new in 1.3 (43 tests, all passing)
- tests/config/test_settings.py
- tests/schema/test_schema_models.py
- tests/schema/test_schema_repository.py
- tests/schema/test_schema_validator.py

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
