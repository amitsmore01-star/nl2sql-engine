# src/pipeline/schema_summary.py
# V0 - Initial implementation
#
# Builds a compressed plain-text schema summary for LLM Step 2 (Schema Mapper).
#
# The LLM needs to know which tables and columns exist so it can map the user's
# intent to real schema elements. We cannot send the full schema JSON — it is too
# large and contains information the LLM does not need.
#
# build_schema_summary() produces a compact string with:
#   - Table name and synonyms in brackets (one line per table)
#   - Column names with their synonyms in brackets where defined (one line per table)
#
# Column synonym format:
#   - Column with synonyms:    AccName [acc name]
#   - Column without synonyms: AccID
#
# Junction tables are excluded entirely — the join resolver handles them
# automatically and the LLM must never propose them.
#
# Output target: under 1,200 tokens (~4,800 characters at ~4 chars/token).
#
# Phase 2 note: is_identifier and is_default_text column flags are not included
# in the summary yet. Revisit in Phase 2 if LLM mapping quality needs improvement.

from src.schema.schema_models import AppSchema, ColumnSchema


def _format_column(col: ColumnSchema) -> str:
    """
    Format a single column for the summary line.

    Columns with synonyms:    ColName [synonym one, synonym two]
    Columns without synonyms: ColName

    Args:
        col: A ColumnSchema object from the loaded schema.

    Returns:
        A formatted string representing the column.
    """
    if col.synonyms:
        synonyms_str = ", ".join(col.synonyms)
        return f"{col.name} [{synonyms_str}]"
    return col.name


def build_schema_summary(schema: AppSchema) -> str:
    """
    Build a compressed plain-text summary of the schema for LLM Step 2.

    Junction tables are excluded — the LLM must never propose them.
    Column synonyms are included in brackets to help the LLM map natural
    language field references to real column names.

    Args:
        schema: The loaded AppSchema object for the matched app.

    Returns:
        A plain-text string — one block per non-junction table.
        Each block has a table line (name + synonyms) and a cols line
        (column names, with synonyms in brackets where defined).

    Example output:
        table: Major.Customer [Customer, customer, organization, org]
          cols: CustomerID, CustomerCID [Customer id, Customer cid], CustomerName
        table: Major.Acc [Acc, Accs, top Acc, sub Acc]
          cols: AccID, AccName [Acc name], AccLevelConfig, ParentAccID
    """
    lines: list[str] = []

    for table in schema.tables:
        # Junction tables are never sent to the LLM.
        # The join resolver inserts them automatically when needed.
        if table.is_junction_table:
            continue

        # Table line: name followed by synonyms in brackets.
        # Empty brackets if the table has no synonyms (Option A agreed).
        synonyms_str = ", ".join(table.synonyms)
        table_line = f"table: {table.name} [{synonyms_str}]"

        # Cols line: each column formatted with its synonyms where defined.
        formatted_cols = [_format_column(col) for col in table.columns]
        cols_line = f"  cols: {', '.join(formatted_cols)}"

        lines.append(table_line)
        lines.append(cols_line)

    return "\n".join(lines)
