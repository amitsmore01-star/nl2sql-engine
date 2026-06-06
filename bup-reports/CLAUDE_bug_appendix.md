<!-- Appendix to CLAUDE.md — paste at the end of your existing story-development CLAUDE.md -->

---

# Bug Handling & Bug Reports

> This section governs bug-fix work (e.g. via Claude Code). The same project rules
> above still apply in full — sync only, zero hardcoding, file path + version
> headers, MockLLMProvider in tests, never recreate a missing file from memory.

## Bug-Fix Loop

1. **Read `SESSION_CONTEXT.md` first** to know the current state.
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
