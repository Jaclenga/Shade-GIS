#!/usr/bin/env python
"""Initialize Postgres database and populate `stops` table from local `stops.txt`.

Usage:
  python scripts/init_db.py

It reads DB connection info from environment variables with sensible defaults.
"""
import os
import psycopg2
from psycopg2.extras import execute_values
from pathlib import Path
import csv

DB_HOST = os.environ.get("PGHOST", "localhost")
DB_PORT = int(os.environ.get("PGPORT", 5432))
DB_NAME = os.environ.get("PGDATABASE", "tampa_shade")
DB_USER = os.environ.get("PGUSER", "postgres")
DB_PASS = os.environ.get("PGPASSWORD", "postgres")

HERE = Path(__file__).parent.parent
STOPS_FILE = HERE / "stops.txt"

SCHEMA = "public"


def connect():
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)


def load_stops_csv(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append((r["stop_id"], r.get("stop_code"), r.get("stop_name"), float(r.get("stop_lat")), float(r.get("stop_lon"))))
    return rows


def main():
    if not STOPS_FILE.exists():
        print("stops.txt not found at", STOPS_FILE)
        return

    rows = load_stops_csv(STOPS_FILE)
    if not rows:
        print("No stops found in stops.txt")
        return

    with connect() as conn:
        with conn.cursor() as cur:
            # ensure schema (tables) exist; schema.sql is executed by docker init, but double-check
            cur.execute(open(HERE / "sql" / "schema.sql", "r").read())

            # upsert stops
            sql = (
                "INSERT INTO stops (stop_id, stop_code, stop_name, stop_lat, stop_lon) VALUES %s "
                "ON CONFLICT (stop_id) DO UPDATE SET stop_code = EXCLUDED.stop_code, stop_name = EXCLUDED.stop_name, stop_lat = EXCLUDED.stop_lat, stop_lon = EXCLUDED.stop_lon"
            )
            execute_values(cur, sql, rows)
        conn.commit()
    print(f"Inserted/updated {len(rows)} stops into {DB_NAME}.")


if __name__ == '__main__':
    main()
