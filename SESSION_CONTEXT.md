# SESSION_CONTEXT.md

## Completed Stories (all tests passing)
- 1.1 ✅ Project Scaffold
- 1.2 ✅ Configuration

## Current Sprint
Sprint 1 — Foundation

## Current Story
1.3 — Schema Models

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

### Tests
- tests/config/test_settings.py    ← new in 1.2 (33 tests, all passing)

### Init Files
- All __init__.py files (25 total) ← created in 1.1

## Key Decisions Made
- ENV is case-sensitive — must be exactly `dev` or `prod` (not `DEV`)
- settings.base.yaml owns all keys — dev/prod only override values, never introduce new keys
- Unknown YAML keys not in Pydantic model raise ValueError at startup (extra=forbid)
- LLM_PROVIDER in .env overrides whatever YAML says
- settings.py is the only file allowed to call os.getenv() / os.environ
