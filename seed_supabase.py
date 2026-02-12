"""
Seed Supabase from .temp/ SQL INSERT files.

Parses the SQL INSERT statements, converts them to Python dicts,
and upserts into Supabase via the PostgREST API (service role key bypasses RLS).

Insertion order respects foreign keys: users -> forums -> questions -> answers
"""

import re
import sys
from supabase import create_client
from app.config import settings


def parse_sql_inserts(sql_text: str) -> tuple[list[str], list[dict]]:
    """Parse a SQL INSERT statement into column names and list of row dicts.

    Handles:
    - Multi-line values
    - Escaped single quotes ('')
    - String, integer, boolean, and NULL values
    """
    # Extract column names
    col_match = re.search(r'\(([^)]+)\)\s*VALUES', sql_text, re.IGNORECASE)
    if not col_match:
        raise ValueError("Could not find column names in SQL")

    columns = [c.strip().strip('"') for c in col_match.group(1).split(',')]

    # Extract the VALUES portion (everything after "VALUES " until the final ";")
    values_start = sql_text.index('VALUES') + len('VALUES')
    values_text = sql_text[values_start:].strip()
    if values_text.endswith(';'):
        values_text = values_text[:-1].strip()

    # Parse rows using a state machine
    rows = []
    current_row_values = []
    current_value = []
    in_string = False
    i = 0
    depth = 0  # parentheses depth

    while i < len(values_text):
        char = values_text[i]

        if not in_string:
            if char == '(':
                depth += 1
                if depth == 1:
                    # Start of a new row
                    current_row_values = []
                    current_value = []
                    i += 1
                    continue
                else:
                    current_value.append(char)
            elif char == ')':
                depth -= 1
                if depth == 0:
                    # End of a row - save the last value
                    val_str = ''.join(current_value).strip()
                    current_row_values.append(val_str)

                    # Build dict for this row
                    if len(current_row_values) == len(columns):
                        row = {}
                        for col, val in zip(columns, current_row_values):
                            row[col] = parse_value(val)
                        rows.append(row)
                    else:
                        print(f"WARNING: Row has {len(current_row_values)} values but expected {len(columns)}")
                        print(f"  Values: {current_row_values[:3]}...")

                    current_value = []
                else:
                    current_value.append(char)
            elif char == ',' and depth == 1:
                # Column separator within a row
                val_str = ''.join(current_value).strip()
                current_row_values.append(val_str)
                current_value = []
            elif char == "'":
                in_string = True
                current_value.append(char)
            else:
                current_value.append(char)
        else:
            # Inside a string
            if char == "'" and i + 1 < len(values_text) and values_text[i + 1] == "'":
                # Escaped single quote
                current_value.append("''")
                i += 1
            elif char == "'":
                # End of string
                in_string = False
                current_value.append(char)
            else:
                current_value.append(char)

        i += 1

    return columns, rows


def parse_value(val_str: str):
    """Convert a SQL value string to a Python value."""
    if val_str.upper() == 'NULL':
        return None

    # String value (single-quoted)
    if val_str.startswith("'") and val_str.endswith("'"):
        # Remove outer quotes and unescape inner quotes
        inner = val_str[1:-1].replace("''", "'")

        # Check for boolean-like strings
        if inner == 'true':
            return True
        if inner == 'false':
            return False

        return inner

    # Boolean
    if val_str.lower() == 'true':
        return True
    if val_str.lower() == 'false':
        return False

    # Integer
    try:
        return int(val_str)
    except ValueError:
        pass

    # Float
    try:
        return float(val_str)
    except ValueError:
        pass

    return val_str


def upsert_table(supabase, table_name: str, rows: list[dict], conflict_column: str = "id"):
    """Upsert rows into a Supabase table."""
    if not rows:
        print(f"  No rows to upsert for {table_name}")
        return

    # Upsert in batches of 50 to avoid request size limits
    batch_size = 50
    total = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        try:
            result = supabase.table(table_name).upsert(
                batch,
                on_conflict=conflict_column
            ).execute()
            total += len(batch)
            print(f"  Upserted batch {i // batch_size + 1}: {len(batch)} rows")
        except Exception as e:
            print(f"  ERROR upserting batch {i // batch_size + 1} into {table_name}: {e}")
            # Try one-by-one for this batch to identify problematic rows
            for j, row in enumerate(batch):
                try:
                    supabase.table(table_name).upsert(
                        row,
                        on_conflict=conflict_column
                    ).execute()
                    total += 1
                except Exception as e2:
                    row_id = row.get('id', row.get('username', f'row_{i+j}'))
                    print(f"    FAILED row {row_id}: {e2}")

    print(f"  Total upserted into {table_name}: {total}/{len(rows)}")


def main():
    print("Connecting to Supabase...")
    print(f"  URL: {settings.supabase_url}")
    supabase = create_client(settings.supabase_url, settings.supabase_service_key)

    # Define tables in FK dependency order
    tables = [
        ("users", ".temp/users_rows.sql", "id"),
        ("forums", ".temp/forums_rows.sql", "id"),
        ("questions", ".temp/questions_rows.sql", "id"),
        ("answers", ".temp/answers_rows.sql", "id"),
    ]

    for table_name, sql_file, conflict_col in tables:
        print(f"\n{'='*60}")
        print(f"Processing: {table_name} ({sql_file})")
        print(f"{'='*60}")

        try:
            with open(sql_file, 'r') as f:
                sql_text = f.read()
        except FileNotFoundError:
            print(f"  File not found: {sql_file}, skipping")
            continue

        columns, rows = parse_sql_inserts(sql_text)
        print(f"  Parsed {len(rows)} rows with columns: {columns}")

        if rows:
            print(f"  Sample row: {list(rows[0].items())[:3]}...")

        upsert_table(supabase, table_name, rows, conflict_col)

    print(f"\n{'='*60}")
    print("Done!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
