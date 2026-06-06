<!-- bug-reports/INDEX.md -->
<!-- V0 - Initial implementation -->

# Bug Report Index

A running list of every bug fixed in `nl2sql-engine`. One line per bug.
Add a new row each time a bug is fixed, and link it to its full report file.

**Conventions**
- Report files live in this folder: `bug-reports/BUG-YYYY-MM-DD-short-slug.md`
- Newest entries go at the top.
- Keep the one-line summary in plain English.

| Date | Bug | Area / File | Status | Report |
|------|-----|-------------|--------|--------|
| 2026-06-06 | Role-duplicate table entries — LLM emits one table per column, causing Acc to join 4× instead of 2× | src/validator/table_column_validator.py | Fixed | [link](./BUG-2026-06-06-role-duplicate-table-entries.md) |
| 2026-06-06 | NoJoinPathError for out-of-order LLM table output (e.g. CustomerDemographics before Customer) | src/validator/join_resolver.py | Fixed | [link](./BUG-2026-06-06-deferred-join-out-of-order-tables.md) |
| _YYYY-MM-DD_ | _short description of the bug_ | _src/.../file.py_ | Fixed | [link](./BUG-YYYY-MM-DD-short-slug.md) |

<!--
EXAMPLE ROW (delete once you have a real one):
| 2026-06-05 | Duplicate AND condition in self-join ON clause | src/validator/join_resolver.py | Fixed | [link](./BUG-2026-06-05-duplicate-join-condition.md) |
-->
