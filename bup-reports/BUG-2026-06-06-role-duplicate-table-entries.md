# Bug Report: Role-duplicate table entries cause Acc to join 4 times

- **Date:** 2026-06-06
- **Story / area:** table_column_validator — `src/validator/table_column_validator.py`
- **Status:** Fixed / Tests passing

## 1. What went wrong (the symptom)

For the query:

> "give me top customername, customercid, top acc name, top acc key, sub acc name,
> sub acc key for subaccount with Platform Indicator is CoreFI in ABC"

The generated SQL contained four JOIN clauses for `Major.Acc` instead of two. The
query returned a massive cross-product result instead of the expected two hierarchy
levels (one top-Acc row and one sub-Acc row per customer).

## 2. Root cause (why it happened)

The LLM emitted one `tables` entry per column rather than one per logical role:

```json
{"table": "Major.Acc", "source": "top acc name"},
{"table": "Major.Acc", "source": "top acc key"},
{"table": "Major.Acc", "source": "sub acc name"},
{"table": "Major.Acc", "source": "sub acc key"}
```

The existing `_drop_phantom_duplicates` function only drops entries whose source
matches **nothing** in the schema. All four entries above match the hierarchy
synonyms (`top acc` matches `top_Acc`; `sub acc` matches `sub_Acc`), so all four
were kept. The function had no concept of "same role already represented."

**Key Python concept:** The function used a `matches` boolean check — `True` or
`False`. Once `True`, the entry was accepted with no further questioning. What was
missing was a second guard: "has a previous entry already claimed this role?"

## 3. The fix (what I changed)

Added `seen_roles: dict[str, set]` tracking inside `_drop_phantom_duplicates`.

- Before any entry is appended to `cleaned`, its hierarchy role is looked up.
- If a role was already recorded for this table (i.e. a previous entry mapped to
  the same role), the current entry is dropped and a warning is appended.
- If the entry has no hierarchy role (matches only via table display name / table
  synonym), it is kept as before — this guard only fires on role-matched entries.

This means two entries for `top_Acc` → only the first is kept. Two entries for
`sub_Acc` → only the first is kept. Result: 2 entries from 4 (correct).

## 4. Files changed

| File | Version | What changed |
|------|---------|--------------|
| `src/validator/table_column_validator.py` | V2 → V3 | Added `seen_roles` tracking in `_drop_phantom_duplicates` |
| `tests/validator/test_table_column_validator.py` | V2 → V3 | Added `TestRoleDuplicateTables` (P7–P12) |
| `config/prompts.yaml` | V1 → V2 | Added "one entry per logical role" to tables rules |

## 5. Before / after (key lines)

```diff
  cleaned: list[dict] = []
+ seen_roles: dict[str, set] = {}
  for entry in proposed_tables:
      ...
      if matches:
+         role = match_hierarchy_role(source, t_schema) if t_schema is not None else None
+         if role is not None:
+             if t_name not in seen_roles:
+                 seen_roles[t_name] = set()
+             if role in seen_roles[t_name]:
+                 context.warnings.append(
+                     f"Dropped duplicate table entry '{t_name}' (source "
+                     f"'{source}') — hierarchy role '{role}' already represented. "
+                     f"LLM listed the same logical instance multiple times."
+                 )
+                 continue
+             seen_roles[t_name].add(role)
          cleaned.append(entry)
          kept_any[t_name] = True
          continue
```

## 6. How it was verified

New tests P7–P12 in `tests/validator/test_table_column_validator.py`:

- P7: 4 Acc entries (2 per role) → deduped to 2 entries
- P8: 2 Acc entries with distinct roles → both kept (regression guard)
- P9: 2 Acc entries with same role → 1 kept
- P10: Warning appended for each dropped role-duplicate
- P11: All 4 columns survive in resolved_columns after table dedup
- P12: Single-instance table not scrutinised — no dedup applied

Full suite: `pytest --tb=no -q` → 803 passed, 1 pre-existing failure (unrelated).

## 7. Anything to watch out for later

- This fix resolves the table deduplication problem. The SQL output for the
  original query still needs further fixes:
  - `output_alias` deduplication in `structured_query_builder.py` — both
    AccName columns get `AS AccName`; need role prefix (e.g. `AS subAccName`).
  - `CustomerName` filter may be assigned to the wrong table — prompt example
    needed in `config/prompts.yaml`.
- Defense-in-depth: the prompt rule (V2) tells the LLM not to repeat the pattern;
  the validator fix (V3) catches it silently if the LLM ignores the rule.
