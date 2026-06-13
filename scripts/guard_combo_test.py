# scripts/guard_combo_test.py
# V0 - Initial implementation
# Simulates the post-LLM column-injection guard against all risky phrase
# combinations extracted from Acme_app.json, covering 2 and 3-level joins.

import json
import re
from pathlib import Path
from itertools import product

SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "Acme_app.json"


def load_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def build_index(schema):
    """
    Returns:
      table_synonyms: { "Major.Acc": ["acc", "top acc", ...], ... }
      col_synonyms:   { "Major.Acc": { "AccName": ["acc name"], "AccKey": ["acc key","acc id"] } }
      hierarchy_synonyms: { "Major.Acc": { "top_Acc": ["top","top acc",...], "sub_Acc": [...] } }
    """
    table_synonyms = {}
    col_synonyms = {}
    hierarchy_synonyms = {}

    for t in schema["tables"]:
        tname = t["name"]
        syns = [s.lower() for s in t.get("synonyms", [])]
        syns.append(t["display_name"].lower())
        table_synonyms[tname] = list(dict.fromkeys(syns))  # dedupe, preserve order

        col_synonyms[tname] = {}
        for col in t.get("columns", []):
            cname = col["name"]
            csyns = [s.lower() for s in col.get("synonyms", [])]
            # also treat the raw column name (lowercased, stripped of table prefix) as a match
            csyns.append(cname.lower())
            col_synonyms[tname][cname] = list(dict.fromkeys(csyns))

        # hierarchy role synonyms (only Acc has these currently)
        hier = t.get("business_rules", {}).get("hierarchy", {})
        if hier:
            hierarchy_synonyms[tname] = {}
            for role, rdata in hier.items():
                rsyns = [s.lower() for s in rdata.get("synonyms", [])]
                hierarchy_synonyms[tname][role] = rsyns

    return table_synonyms, col_synonyms, hierarchy_synonyms


# ---------------------------------------------------------------------------
# THE GUARD LOGIC
# ---------------------------------------------------------------------------

def run_guard(tables_list, columns_list, col_synonyms):
    """
    For every entry in tables_list, check if its source phrase contains
    a column synonym for that table.  If yes and the column is not already
    in columns_list → inject it.

    Returns (injected_columns, updated_columns_list)
    """
    injected = []
    existing = {(c["table"], c["column"]) for c in columns_list}

    for tentry in tables_list:
        tname = t_name = tentry["table"]
        source = tentry["source"].lower()

        for col_name, csyns in col_synonyms.get(tname, {}).items():
            for csyn in csyns:
                # skip trivial single-word column names to reduce noise
                if len(csyn.split()) < 2 and csyn == col_name.lower():
                    continue
                if csyn in source and (tname, col_name) not in existing:
                    injected.append({
                        "table": tname,
                        "column": col_name,
                        "source": tentry["source"],
                        "injected_by_guard": True,
                        "matched_synonym": csyn,
                    })
                    existing.add((tname, col_name))
                    break  # one synonym match is enough per column

    return injected, columns_list + injected


# ---------------------------------------------------------------------------
# COMBO GENERATION
# ---------------------------------------------------------------------------

def make_source_phrase(role_qualifier, col_syn):
    """Combine a role qualifier with a column synonym, e.g. 'top acc' + 'acc name' → 'top acc name'."""
    # If col_syn already starts with the role qualifier word, don't double up
    parts = role_qualifier.split() + col_syn.split()
    # deduplicate consecutive identical words
    deduped = [parts[0]]
    for w in parts[1:]:
        if w != deduped[-1]:
            deduped.append(w)
    return " ".join(deduped)


def generate_2level_combos(table_synonyms, col_synonyms, hierarchy_synonyms):
    """
    2-level join: Customer (anchor) + one other table.
    Risky pattern: user says '[role_qualifier] [col_synonym]' as a single phrase.
    """
    combos = []
    anchor = "Major.Customer"

    for tname, t_syns in table_synonyms.items():
        if tname == anchor or tname == "Major.PackagePlan":
            continue

        role_qualifiers = t_syns[:]  # table synonyms as qualifiers

        # also add hierarchy role synonyms if available
        for role, rsyns in hierarchy_synonyms.get(tname, {}).items():
            role_qualifiers.extend(rsyns)

        role_qualifiers = list(dict.fromkeys(role_qualifiers))

        for rq in role_qualifiers:
            for col_name, csyns in col_synonyms.get(tname, {}).items():
                for csyn in csyns:
                    if len(csyn.split()) < 2 and csyn == col_name.lower():
                        continue  # skip raw column-name-only synonyms
                    phrase = make_source_phrase(rq, csyn)
                    combos.append({
                        "join_depth": 2,
                        "tables": [anchor, tname],
                        "source_phrase": phrase,
                        "role_qualifier": rq,
                        "target_table": tname,
                        "target_col": col_name,
                        "col_synonym": csyn,
                    })

    return combos


def generate_3level_combos(table_synonyms, col_synonyms, hierarchy_synonyms):
    """
    3-level join: Customer → Acc → EPInd  (the only real 3-hop chain in Acme).
    Also covers Customer → CustomerDemographics + Acc (2 joins off the anchor).
    """
    combos = []

    # Chain 1: Customer → Acc → EPInd
    # User asks for something on EPInd using a phrase that starts with an Acc qualifier
    acc_qualifiers = table_synonyms.get("Major.Acc", [])[:]
    for role, rsyns in hierarchy_synonyms.get("Major.Acc", {}).items():
        acc_qualifiers.extend(rsyns)
    acc_qualifiers = list(dict.fromkeys(acc_qualifiers))

    epind_table = "Config.EPInd"
    for aq in acc_qualifiers:
        for col_name, csyns in col_synonyms.get(epind_table, {}).items():
            for csyn in csyns:
                if len(csyn.split()) < 2 and csyn == col_name.lower():
                    continue
                phrase = make_source_phrase(aq, csyn)
                combos.append({
                    "join_depth": 3,
                    "tables": ["Major.Customer", "Major.Acc", epind_table],
                    "source_phrase": phrase,
                    "role_qualifier": aq,
                    "target_table": epind_table,
                    "target_col": col_name,
                    "col_synonym": csyn,
                    "note": "acc qualifier leaks into EPInd column phrase",
                })

    # Chain 2: Customer + CustomerDemographics + Acc (2 separate 2-level phrases combined)
    # Already covered by generate_2level_combos for each table individually;
    # the 3-level risk here is the LLM seeing two phrases at once and dropping one column.
    # We enumerate the pair combinations.
    cd_table = "Major.CustomerDemographics"
    acc_table = "Major.Acc"
    cd_qualifiers = table_synonyms.get(cd_table, [])
    acc_qualifiers2 = list(dict.fromkeys(table_synonyms.get(acc_table, []) +
                           [s for rsyns in hierarchy_synonyms.get(acc_table, {}).values()
                            for s in rsyns]))

    for cdq in cd_qualifiers:
        for cd_col, cd_csyns in col_synonyms.get(cd_table, {}).items():
            for cd_csyn in cd_csyns:
                if len(cd_csyn.split()) < 2 and cd_csyn == cd_col.lower():
                    continue
                for aq in acc_qualifiers2:
                    for acc_col, acc_csyns in col_synonyms.get(acc_table, {}).items():
                        for acc_csyn in acc_csyns:
                            if len(acc_csyn.split()) < 2 and acc_csyn == acc_col.lower():
                                continue
                            combos.append({
                                "join_depth": 3,
                                "tables": ["Major.Customer", cd_table, acc_table],
                                "source_phrase": f"{make_source_phrase(cdq, cd_csyn)} + {make_source_phrase(aq, acc_csyn)}",
                                "role_qualifier": f"{cdq} / {aq}",
                                "target_table": f"{cd_table} + {acc_table}",
                                "target_col": f"{cd_col} + {acc_col}",
                                "col_synonym": f"{cd_csyn} / {acc_csyn}",
                            })

    return combos


# ---------------------------------------------------------------------------
# SIMULATE LLM DROP AND RUN GUARD
# ---------------------------------------------------------------------------

def simulate_and_guard(combo, col_synonyms):
    """
    Simulate the LLM greedy-match failure:
      - tables_list has an entry for the target table with the risky source phrase
      - columns_list is EMPTY for the target column (the drop we're testing)
    Then run the guard and report whether it recovers the missing column.
    """
    # For simplicity, only test the primary (first) target table in the combo
    if "+" in str(combo.get("target_table", "")):
        # 3-level pair combo — test both halves separately
        return None  # skip pair combos in simulation (they are enumerated separately)

    tname = combo["target_table"]
    col_name = combo["target_col"]
    source = combo["source_phrase"]

    tables_list = [{"table": tname, "source": source}]
    columns_list = []  # simulate LLM dropped the column

    injected, _ = run_guard(tables_list, columns_list, col_synonyms)
    recovered = any(i["column"] == col_name and i["table"] == tname for i in injected)

    return {
        "source_phrase": source,
        "table": tname,
        "column": col_name,
        "col_synonym": combo["col_synonym"],
        "guard_recovers": recovered,
        "join_depth": combo["join_depth"],
    }


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    schema = load_schema()
    table_synonyms, col_synonyms, hierarchy_synonyms = build_index(schema)

    combos_2 = generate_2level_combos(table_synonyms, col_synonyms, hierarchy_synonyms)
    combos_3 = generate_3level_combos(table_synonyms, col_synonyms, hierarchy_synonyms)
    all_combos = combos_2 + combos_3

    print(f"\nTotal combinations generated : {len(all_combos)}")
    print(f"  2-level join combos        : {len(combos_2)}")
    print(f"  3-level join combos        : {len(combos_3)}")

    results = []
    for c in all_combos:
        r = simulate_and_guard(c, col_synonyms)
        if r:
            results.append(r)

    recovered = [r for r in results if r["guard_recovers"]]
    missed    = [r for r in results if not r["guard_recovers"]]

    print(f"\nSimulation results (single-table phrases only): {len(results)} tested")
    print(f"  Guard RECOVERS : {len(recovered)}")
    print(f"  Guard MISSES   : {len(missed)}")

    if missed:
        print("\n--- GUARD MISSES (these would still produce wrong SQL) ---")
        for r in missed:
            print(f"  [{r['join_depth']}-level]  phrase='{r['source_phrase']}'  "
                  f"table={r['table'].split('.')[-1]}  col={r['column']}  "
                  f"col_syn='{r['col_synonym']}'")

    # Group by table for readability
    from collections import defaultdict
    by_table = defaultdict(list)
    for r in recovered:
        by_table[r["table"]].append(r)

    print("\n--- GUARD RECOVERS (grouped by table) ---")
    for tname, rows in sorted(by_table.items()):
        print(f"\n  Table: {tname}")
        for r in rows:
            print(f"    [{r['join_depth']}-level]  '{r['source_phrase']}'  -> {r['column']} (via syn '{r['col_synonym']}')")

    # ---- Highlight the known failing case ----
    print("\n--- KNOWN FAILING CASE FROM LOG ---")
    known = {"table": "Major.Acc", "source": "top acc name"}
    tables_list = [known]
    columns_list = []
    injected, _ = run_guard(tables_list, columns_list, col_synonyms)
    print(f"  Input tables entry : {known}")
    print(f"  Guard injected     : {injected}")

    # ---- 3-level pair summary (not simulated, just listed) ----
    pair_combos = [c for c in combos_3 if "+" in str(c.get("target_table", ""))]
    print(f"\n--- 3-LEVEL PAIR COMBOS (enumerated, not simulated: {len(pair_combos)}) ---")
    seen_pairs = set()
    for c in pair_combos[:10]:
        key = c["source_phrase"]
        if key not in seen_pairs:
            seen_pairs.add(key)
            print(f"  {c['source_phrase']}")
    if len(pair_combos) > 10:
        print(f"  ... and {len(pair_combos) - 10} more")


if __name__ == "__main__":
    main()
