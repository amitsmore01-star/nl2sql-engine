# Bug Report: NoRelevantColumnsError when LLM omits a column's table from the tables array

- **Date:** 2026-06-13
- **Story / area:** Table & Column Validator — `src/validator/table_column_validator.py`
- **Status:** Fixed / Tests passing

## 1. What went wrong (the symptom)

The query `get customer name, sub acc key, top account key for customercid 1231231 in ACME`
returned an error:

```
LLM proposed column(s) not found in schema 'Acme_app':
["Major.CustomerDemographics.CustomerName
  (table 'Major.CustomerDemographics' was not in proposed tables)"]
```

## 2. Root cause (why it happened)

The LLM correctly identified that `CustomerName` lives on `Major.CustomerDemographics`
and put it in the columns array. But it forgot to add `Major.CustomerDemographics` to
the tables array:

```
tables:  [Major.Customer, Major.Acc(sub), Major.Acc(top)]   ← CustomerDemographics missing
columns: [Major.CustomerDemographics.CustomerName, ...]      ← references missing table
```

Stage 2 of `run_table_column_validator` checks:

```python
if col_table not in proposed_table_name_set:
    invalid_columns.append(...)   # hard fail — no recovery
```

There was no distinction between "valid schema table the LLM forgot to list" and
"table that does not exist in the schema at all." Both paths raised `NoRelevantColumnsError`.

**This is a different bug from the V7 bridge-injection fix:**

| V7 (join_resolver) | This bug (table_column_validator) |
|---|---|
| Table absent from tables list AND absent from columns | Table absent from tables list BUT present in columns |
| Fix was in join resolution step | Fix is in the earlier validation step |

## 3. The fix (what I changed)

In **Stage 2** of `run_table_column_validator`, when a column's table is not in
`proposed_table_name_set`, the code now checks whether `col_table` is a valid
non-junction schema table (`col_table in valid_table_names`):

- **Yes (valid schema table):** auto-inject `{"table": col_table, "source": col_source}`
  into `cleaned_tables` (which IS `context.resolved_tables`), add `col_table` to
  `proposed_table_name_set`, append a warning, and continue validating the column.
- **No (not in schema):** keep the existing hard-fail path (`invalid_columns.append`).

The injected entry uses the column's own source phrase (e.g. `"customer name"`), which
is the right semantic source for the table — the LLM derived both from the same user phrase.

## 4. Files changed

| File | Version | What changed |
|------|---------|--------------|
| `src/validator/table_column_validator.py` | V3 → V4 | Stage 2 auto-inject for valid schema tables missing from proposed list |
| `tests/validator/test_table_column_validator.py` | V3 → V4 | Updated D2 (now tests truly non-schema table); added `TestColumnTableAutoInject` (L1–L4) |

## 5. Before / after (key lines)

```diff
- if col_table not in proposed_table_name_set:
-     invalid_columns.append(
-         f"{col_table}.{col_name} (table '{col_table}' was not in proposed tables)"
-     )
-     continue

+ if col_table not in proposed_table_name_set:
+     if col_table in valid_table_names:
+         cleaned_tables.append({"table": col_table, "source": col_source})
+         proposed_table_name_set.add(col_table)
+         context.warnings.append(f"Auto-injected table '{col_table}' ...")
+     else:
+         invalid_columns.append(...)
+         continue
```

## 6. How it was verified

New tests L1–L4 in `tests/validator/test_table_column_validator.py`:

- **L1**: CustomerDemographics in columns only → auto-injected, success, all 3 columns resolved
- **L2**: Same → CustomerDemographics in resolved_tables with `source="customer name"`, warning present
- **L3**: Regression — column on `Major.Nonexistent` (not in schema) → `NoRelevantColumnsError` still raised
- **L4**: Regression — table already in proposed list → no injection, no warning

Updated **D2**: scenario changed from valid-schema table (now handled by L1/L2) to truly
non-schema table, keeping it as a hard-fail regression guard.

Run: `pytest tests/validator/test_table_column_validator.py -v`
Full suite: `pytest tests/` → **816 passed, 1 skipped**

## 7. Anything to watch out for later

- The injected table entry goes through the normal join_resolver pipeline. If the LLM omits
  both the table from tables AND it is needed as a join bridge, the V7 bridge-injection in
  join_resolver will fire as well — both fixes stack correctly.
- Junction tables are intentionally excluded from auto-inject (`col_table in valid_table_names`
  uses only non-junction names). If a column ever references a junction table, it still fails.
- Stage 3 (filter validation) has the same structural pattern. If a filter references a valid
  schema table not in the proposed list, it still raises today. This has not been observed in
  production — deferred until seen.
