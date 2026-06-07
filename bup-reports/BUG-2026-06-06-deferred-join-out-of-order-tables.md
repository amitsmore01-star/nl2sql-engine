# Bug Report: NoJoinPathError for out-of-order LLM table output

- **Date:** 2026-06-06
- **Story / area:** Join Resolver — `src/validator/join_resolver.py`
- **Status:** Fixed / Tests passing

## 1. What went wrong (the symptom)

When the LLM returned tables in an order where an intermediate table appeared
before the table it connects through, the pipeline raised a hard error:

```
No join path found between 'Major.CustomerDemographics' and any of ['Major.Acc'].
Check schema relationships.
```

Example query: "give me topacc name, subacc name, customername, customercid for
subaccount with EPInd is PlatformA in Acme"

LLM output table order: `[Acc, CustomerDemographics, Customer, EPInd]`

`CustomerDemographics` has no direct relationship to `Acc` — it connects through
`Customer`. But `Customer` appeared later in the LLM list, so when the join resolver
tried to join `CustomerDemographics` to `[Acc]`, it failed immediately.

## 2. Root cause (why it happened)

The join resolver used a strict sequential `for` loop:

```python
for instance in table_instances[1:]:
    ...
    if not joined:
        raise NoJoinPathError(...)   # ← raised immediately, no retry
    anchored_instances.append(instance)
```

This means: if table number 2 (CustomerDemographics) cannot join the current
anchor set (just Acc), the error is raised right away — even if table number 3
(Customer) would have bridged the gap. The algorithm had no ability to defer a
table and retry it later.

**Why this matters:** The LLM is not required to return tables in join order.
It returns the tables most relevant to the query, in the order it reasons about
them. A strict sequential algorithm treats any ordering that isn't join-compatible
as an error, even when a valid join path exists.

## 3. The fix (what I changed)

Replaced the strict for-loop with a **multi-pass deferred algorithm** — the same
pattern used in build systems (Make, Webpack) for dependency resolution:

```
pending = all tables except the anchor (FROM table)

while pending is not empty:
    progress = False
    for each table in pending:
        if it CAN join the current anchor set:
            anchor it immediately
            progress = True
        else:
            keep it in still_pending
    if progress == False:
        raise NoJoinPathError   ← only raised when truly stuck
    pending = still_pending
```

Key guarantees:
- A table that is deferred in pass 1 is retried in pass 2 (and beyond) as new
  tables are anchored, expanding the set of possible join paths.
- `NoJoinPathError` is raised **only** after a full pass where zero tables were
  anchored — meaning no ordering change could ever fix it. Genuinely disconnected
  tables still fail correctly.
- Each join strategy (self-join, direct, junction bridge) is extracted into a
  helper `_try_join_instance` so the while-loop body is clean.

Trace for the failing query:

```
Pass 1:
  CustomerDemographics vs [Acc]        → no path   → DEFERRED
  Customer vs [Acc]                    → Acc.CustomerID = c.CustomerID ✓ anchored
  EPInd vs [Acc, c]  → Acc.PlatformID ✓ anchored

Pass 2:
  CustomerDemographics vs [Acc, c, epi] → c.CustomerID = cd.CustomerID ✓ anchored

Done — 3 joins produced, no error.
```

## 4. Files changed

| File | Version | What changed |
|------|---------|--------------|
| `src/validator/join_resolver.py` | V5 → V6 | Extracted `_try_join_instance` helper; replaced for-loop in `_resolve_joins_for_tables` with multi-pass while-loop |
| `tests/validator/test_join_resolver.py` | V3 → V4 | Added `TestDeferredJoin` (J1–J8): deferred resolution tests + regression guards |

## 5. Before / after (key lines)

```diff
- for instance in table_instances[1:]:
-     ...
-     if not joined:
-         raise NoJoinPathError(...)
-     anchored_instances.append(instance)
+ pending = list(table_instances[1:])
+ while pending:
+     progress = False
+     still_pending = []
+     for instance in pending:
+         join_dicts, joined = _try_join_instance(instance, anchored_instances, ...)
+         if joined:
+             joins.extend(join_dicts)
+             anchored_instances.append(instance)
+             progress = True
+         else:
+             still_pending.append(instance)
+     if not progress:
+         raise NoJoinPathError(...)
+     pending = still_pending
```

## 6. How it was verified

New tests J1–J8 in `tests/validator/test_join_resolver.py`:
- J1: `[Acc, CustomerDemographics, Customer]` → 2 joins, resolves in 2 passes
- J2: `[Acc, CustomerDemographics, Customer, EPInd]` → 3 joins
- J3: `[Acc, Package]` → `NoJoinPathError` (genuinely disconnected)
- J4: `[CustomerDemographics, EPInd]` → `NoJoinPathError`
- J5: Regression — direct join `[Customer, Acc]` still works
- J6: Regression — ordered join `[Customer, CD, Acc]` still works
- J7: Regression — self-join `[Customer, Acc top, Acc sub]` — a_sub still gets both conditions
- J8: Regression — junction bridge `[Package, Plan]` still produces 2 joins

Run: `pytest tests/validator/test_join_resolver.py -v`

## 7. Anything to watch out for later

- The self-join **additional conditions** (e.g. `c.CustomerID = a_sub.CustomerID`) are
  collected at the moment `a_sub` is processed. If `Customer` is not yet anchored when
  `a_sub` is processed (because both are in the same pending list), `a_sub` will receive
  only the primary condition (`a_top.AccID = a_sub.ParentAccID`). The SQL is still
  **functionally correct** — the missing condition is implied by the chain of other joins —
  but it is a weaker hint for the SQL Server optimizer. This is identical behaviour to V5
  for the same ordering and is not a new regression.
- This fix resolves the join ordering error only. The full failing query still produces
  incomplete SQL because the fused synonym "subacc"/"topacc" causes `_drop_phantom_duplicates`
  to remove the second `Major.Acc` entry before the join resolver runs. Bug A (fused synonym
  phantom drop) must be fixed separately.
