<!-- CLAUDE.md -->
<!-- V0 - Initial implementation (story workflow + bug handling combined) -->

# CLAUDE.md — Working Instructions for Claude Code

This file is read automatically at the start of every Claude Code session.
**I am new to Python — explain key concepts clearly when introducing new concepts or patterns.**

You are helping me build a Python NL2SQL system called `nl2sql-engine` from scratch.

---

## Project Context
- Architecture document, schema (Acme_app.json) and SESSION_CONTEXT.md are uploaded to this project
- SESSION_CONTEXT.md is the source of truth for what has been built and what decisions were made
- Always read SESSION_CONTEXT.md before starting any story to understand current state
- The real schema reference is Acme_app.json — used for all development and tests

## Working Rules — follow these in every chat, every story
- Nothing hardcoded — all config in YAML files, secrets in .env only
- Never assume — always ask for clarification before proceeding
- Confirm file name and purpose before writing any code
- Agree all test scenarios before writing any test code
- Never start coding until I say "start coding"
- Ask if a file from a previous story is needed and not in context — never recreate from memory
- One story at a time — complete and test before moving to next
- Every file must have its relative path and filename as a comment on line 1
- Every new file gets # V0 - Initial implementation on line 2
- When updating a file, increment version (V1, V2...) and append what changed — never replace old version comment
- Tests must pass before moving to next story
- Never move to next story with failing tests

## How Each Story Works
1. I will say which story I am starting (e.g. "Starting Story 3.1")
2. You confirm the files to be built and their purpose — do NOT start coding yet
3. You list the test scenarios for my approval
4. I confirm or adjust the test scenarios
5. I say "start coding"
6. You write the source file first, then the test file
7. I copy files into VS Code and run pytest
8. I paste any errors back — you fix
9. All tests green — story done
10. You provide the exact updated portion of SESSION_CONTEXT.md
    (only the changed sections (Current Story, Next Story, Files Built So Far (1-2 liner), Key Decisions Made, Bug Fix (if any), Architecture Document Updates Made (if any), clearly marked) so I can copy-paste
    and update the file, then commit to GitHub
11. If any design decision made during this story requires an update
    to the architecture document, flag it explicitly at the end with:
    ARCHITECTURE UPDATE NEEDED — state which section and what changes

## Code Standards
- Database: SQL Server
- Framework: FastAPI (API), Typer (CLI)
- All pipeline stage functions are def not async def (sync only)
- LLM HTTP calls use httpx.Client (sync) — never requests, never AsyncClient
- No os.getenv() outside src/config/settings.py
- No hardcoded table names, column names, joins, or business rules anywhere in code
- Tests use MockLLMProvider only — zero real API calls in test suite
- Every src/ file must have a matching test file

## When I Paste Test Errors
- Read the full error carefully before responding
- Fix only what is failing — do not rewrite unrelated code
- Explain what caused the error in plain English
- Show only the changed lines unless a full rewrite is needed

---

# Bug Handling & Bug Reports

> Use this section when the task is fixing a bug (not building a story).
> All Working Rules and Code Standards above still apply in full — sync only,
> zero hardcoding, file path + version headers, MockLLMProvider in tests,
> never recreate a missing file from memory.

## Bug-Fix Loop
1. **Read SESSION_CONTEXT.md first** to know the current state.
2. **Reproduce / locate** — read the failing test output or reported behaviour
   fully before touching anything.
3. **Find the root cause** — the real underlying reason, not the symptom.
4. **State the plan** — before editing, explain in plain English what is broken,
   why, and exactly which file(s) and line(s) will change.
5. **Fix only what is failing.** Do not rewrite or "tidy" unrelated code.
6. **Version the file header** — increment the version on every edited file and
   append a note (e.g. `# V3 (bug fix) - <what changed>`). Never overwrite old
   version comments.
7. **Run the tests.** A bug is done only when the relevant tests are green.
   Never weaken or delete a test to make it pass.
8. **Write a bug report** (below) — required for EVERY bug fixed.

If the cause is unclear or there are multiple valid fixes, **ask — do not assume.**

## Bug Report — required for every bug
- **Where:** `bug-reports/` at the repo root, one file per bug.
- **Filename:** `BUG-YYYY-MM-DD-short-slug.md`
  (e.g. `BUG-2026-06-05-duplicate-join-condition.md`)
- **Language:** plain English — assume the reader is new to Python.
- Also append a one-line row to `bug-reports/INDEX.md` (create it if missing),
  newest entry at the top.

Use this exact template:

```markdown
# Bug Report: <short title>

- **Date:** YYYY-MM-DD
- **Story / area:** <e.g. Story 5.8, join_resolver>
- **Status:** Fixed / Tests passing

## 1. What went wrong (the symptom)
<Plain English: what the user or test saw. No jargon.>

## 2. Root cause (why it happened)
<The real underlying reason, explained simply. If a Python or Pydantic
concept caused it, explain that concept in one or two sentences.>

## 3. The fix (what I changed)
<What I changed and why it solves the root cause.>

## 4. Files changed
| File | Version | What changed |
|------|---------|--------------|
| src/.../file.py | V0 -> V1 | <one line> |

## 5. Before / after (key lines)
```diff
- old line
+ new line
```

## 6. How it was verified
<Which tests now pass, command run, result.>

## 7. Anything to watch out for later
<Side effects, follow-ups, or "none".>
```

If a fix changes a design decision in the architecture doc, end the report with:
`ARCHITECTURE UPDATE NEEDED — <section> — <what changes>`
