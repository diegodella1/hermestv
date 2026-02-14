#!/usr/bin/env python3
"""Initialize Hermes Radio SQLite database from schema.sql."""

import os
import sqlite3
import sys

def main():
    db_path = os.environ.get("HERMES_DB_PATH", "/opt/hermes/data/hermes.db")
    schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")

    if not os.path.exists(schema_path):
        schema_path = "/opt/hermes/schema.sql"

    print(f"DB path: {db_path}")
    print(f"Schema: {schema_path}")

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    with open(schema_path, "r") as f:
        schema = f.read()

    conn = sqlite3.connect(db_path)
    conn.executescript(schema)
    conn.close()

    print("Database initialized successfully.")


if __name__ == "__main__":
    main()
