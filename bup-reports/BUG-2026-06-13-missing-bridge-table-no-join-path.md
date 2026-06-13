# Bug Report: NoJoinPathError when LLM omits a required bridge table

- **Date:** 2026-06-13
- **Story / area:** Join Resolver — `src/validator/join_resolver.py`
- **Status:** Fixed / Tests passing

## 1. What went wrong (the symptom)

The query `get customer name top account name, sub account name for top account with platform name is CCF in ACME` returned an error instead of SQL:

```
No join path found between 'Major.Acc' and any of ['Major.CustomerDemographics'].
Check schema relationships.
```

The LLM correctly identified all the tables needed for the requested columns and filters,
but did not include `Major.Customer` — the table that sits between `CustomerDemographics`
and `Acc` in the schema.

## 2. Root cause (why it happened)

The schema has no direct relationship between `Major.CustomerDemographics` and `Major.Acc`.
They can only be joined through `Major.Customer`, which holds the shared `CustomerID` key:

```
Major.CustomerDemographics ──CustomerID──> Major.Customer <──CustomerID── Major.Acc
                                                                    │
                                                                    └──PlatformID──> Config.EPInd
```

The LLM returned: `[CustomerDemographics, Acc(top), Acc(sub), EPInd]` — Customer entirely absent.

The existing V6 deferred-join algorithm (Bug 1 fix) handles the case where tables are
**present but in the wrong order** by deferring and retrying. It cannot help when a table
is **completely absent** — after every pass produces zero progress, it raises `NoJoinPathError`.

This is a different failure mode from Bug 1:

| Bug 1 (V6 fix) | This bug (V7 fix) |
|---|---|
| Customer IS in the list, wrong order | Customer is NOT in the list at all |
| Deferred retry solves it | No ordering change can solve it |

## 3. The fix (what I changed)

Added a **pre-flight connectivity check** (`_inject_bridge_tables`) that runs before alias
assignment in `run_join_resolver`.

**How it works:**

1. Build the set of distinct table names currently proposed.
2. Check connectivity using BFS: two table names are "directly connected" if either
   table's schema has a non-self relationship to the other.
3. If the set splits into more than one disconnected component, search the full schema
   for a non-junction table that has direct relationships to tables in **two or more**
   components simultaneously — that is a bridge candidate.
4. Inject the bridge table into `table_instances` with `source="auto-bridge"` and add
   a warning to `context.warnings`.
5. Repeat until fully connected or no bridge is found (letting the existing
   `NoJoinPathError` fire for genuinely disconnected sets).

**Why non-junction only:**
Junction tables (e.g. `Major.PackagePlan`) are excluded. They are already handled by
the `_try_join_instance` junction-bridge path and must not appear in `resolved_tables`.

**Why inject into `resolved_tables`:**
The auto-bridge table (e.g. `Major.Customer`) is a real data table with business rules
(`DeletedFlag`, `VoidedDate IS NULL`). Adding it to `resolved_tables` means
`rule_applicator` correctly applies those rules — which is the right behaviour.
Silently joining through it without adding it would produce SQL missing the active-record
filters for that table.

## 4. Files changed

| File | Version | What changed |
|------|---------|--------------|
| `src/validator/join_resolver.py` | V6 → V7 | Added `_inject_bridge_tables` function and call site in `run_join_resolver` before `table_name_counts` computation |
| `tests/validator/test_join_resolver.py` | V4 → V5 | Added `TestMissingBridgeInjection` (K1–K4) |

## 5. Before / after (key lines)

```diff
+ # In run_join_resolver, before table_name_counts:
+ _inject_bridge_tables(table_instances, table_lookup, app_schema, context.warnings)
+
+ def _inject_bridge_tables(table_instances, table_lookup, app_schema, warnings):
+     # BFS connectivity check on distinct_names
+     # If components > 1: find non-junction bridge that spans 2+ components
+     # Append {"table": bridge_name, "source": "auto-bridge"} to table_instances
+     # Append warning. Repeat until connected or no bridge found.
```

## 6. How it was verified

New tests K1–K4 in `tests/validator/test_join_resolver.py`:

- **K1**: `[CustomerDemographics, Acc(top), Acc(sub), EPInd]` — Customer absent → auto-injected, 4 joins, status=success
- **K2**: Same setup → Customer entry has `source="auto-bridge"`, alias="c", warning in `context.warnings`
- **K3**: Regression — Customer already present → no auto-injection, no bridge warning, 4 joins
- **K4**: Regression — `[Plan, CustomerDemographics]` genuinely disconnected → `NoJoinPathError` still raised

Run: `pytest tests/validator/test_join_resolver.py -v`
Full suite: `pytest tests/` → **812 passed, 1 skipped**

## 7. Anything to watch out for later

- The bridge injection selects the **first** candidate found in `table_lookup` iteration order.
  If two different tables could each serve as a bridge, the one encountered first is injected.
  In the Acme schema this is deterministic (only `Major.Customer` fits), but schemas with
  multiple valid bridges might inject an unexpected one. A future improvement could score
  candidates (e.g. prefer the table with the fewest columns, or the one with the most
  relationships to the disconnected components).
- The injected bridge table gets a warning and `source="auto-bridge"` — both are visible
  in the pipeline logs. If the LLM starts missing bridge tables frequently, the system
  prompt should be updated with an example showing that bridge tables must be included
  even when the user did not explicitly ask for their columns.
- Multi-hop gaps (e.g. A→B→C→D where both B and C are missing) are handled by the
  iterative round loop, but only if a single bridge spans two existing components each
  round. Extremely long missing chains may not be fully repaired.
