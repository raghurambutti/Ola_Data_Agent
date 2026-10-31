"""
Create the ride-sharing tables and load the sample CSVs from data/
(ported from the tutorial's `feed_db.py`).

  uv run data-agent-load-db           create tables if missing, load only into EMPTY tables
  uv run data-agent-load-db --reset   DELETE all rows in these 5 tables, then reload the CSVs

The tutorial version always truncated the tables. Here that only happens
with --reset, so an existing database is never wiped by accident.
"""

import argparse
import sys

import psycopg2
from psycopg2 import sql

from data_agent.config import DATA_DIR, DB_SCHEMA, get_db_config

CREATE_TABLES_SQL = """
CREATE SCHEMA IF NOT EXISTS {schema};

CREATE TABLE IF NOT EXISTS {schema}.users (
    user_id INTEGER PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(50),
    city VARCHAR(100),
    province VARCHAR(50),
    user_type VARCHAR(20) NOT NULL,
    signup_date DATE,
    is_active BOOLEAN
);

CREATE TABLE IF NOT EXISTS {schema}.vehicles (
    vehicle_id INTEGER PRIMARY KEY,
    driver_id INTEGER NOT NULL REFERENCES {schema}.users(user_id),
    make VARCHAR(50),
    model VARCHAR(50),
    year INTEGER,
    license_plate VARCHAR(20) UNIQUE,
    color VARCHAR(30),
    is_active BOOLEAN
);

CREATE TABLE IF NOT EXISTS {schema}.rides (
    ride_id INTEGER PRIMARY KEY,
    rider_id INTEGER NOT NULL REFERENCES {schema}.users(user_id),
    driver_id INTEGER NOT NULL REFERENCES {schema}.users(user_id),
    requested_at TIMESTAMP,
    pickup_time TIMESTAMP,
    dropoff_time TIMESTAMP,
    pickup_latitude NUMERIC(9, 6),
    pickup_longitude NUMERIC(9, 6),
    dropoff_latitude NUMERIC(9, 6),
    dropoff_longitude NUMERIC(9, 6),
    distance_km NUMERIC(10, 2),
    fare NUMERIC(10, 2),
    surge_multiplier NUMERIC(4, 2),
    status VARCHAR(30),
    cancellation_reason VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS {schema}.payments (
    payment_id INTEGER PRIMARY KEY,
    ride_id INTEGER NOT NULL REFERENCES {schema}.rides(ride_id),
    user_id INTEGER NOT NULL REFERENCES {schema}.users(user_id),
    amount NUMERIC(10, 2),
    payment_method VARCHAR(50),
    payment_status VARCHAR(30),
    transaction_id VARCHAR(100) UNIQUE,
    payment_time TIMESTAMP
);

CREATE TABLE IF NOT EXISTS {schema}.ratings (
    rating_id INTEGER PRIMARY KEY,
    ride_id INTEGER NOT NULL REFERENCES {schema}.rides(ride_id),
    rider_id INTEGER NOT NULL REFERENCES {schema}.users(user_id),
    driver_id INTEGER NOT NULL REFERENCES {schema}.users(user_id),
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    rated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vehicles_driver_id ON {schema}.vehicles(driver_id);
CREATE INDEX IF NOT EXISTS idx_rides_rider_id ON {schema}.rides(rider_id);
CREATE INDEX IF NOT EXISTS idx_rides_driver_id ON {schema}.rides(driver_id);
CREATE INDEX IF NOT EXISTS idx_rides_requested_at ON {schema}.rides(requested_at);
CREATE INDEX IF NOT EXISTS idx_rides_status ON {schema}.rides(status);
CREATE INDEX IF NOT EXISTS idx_payments_ride_id ON {schema}.payments(ride_id);
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON {schema}.payments(user_id);
CREATE INDEX IF NOT EXISTS idx_ratings_ride_id ON {schema}.ratings(ride_id);
CREATE INDEX IF NOT EXISTS idx_ratings_driver_id ON {schema}.ratings(driver_id);
"""

# Load order respects foreign keys. Column lists come from each CSV header.
TABLES = ["users", "vehicles", "rides", "payments", "ratings"]


def load_csv(cursor, table: str) -> None:
    path = DATA_DIR / f"{table}.csv"
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        columns = [c.strip() for c in f.readline().strip().split(",")]
        f.seek(0)
        copy_sql = sql.SQL(
            "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, DELIMITER ',', NULL '')"
        ).format(
            sql.Identifier(DB_SCHEMA, table),
            sql.SQL(", ").join(sql.Identifier(c) for c in columns),
        )
        cursor.copy_expert(copy_sql, f)
    print(f"  Loaded {path.name}")


def count(cursor, table: str) -> int:
    cursor.execute(
        sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(DB_SCHEMA, table))
    )
    return cursor.fetchone()[0]


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="data-agent-load-db", description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all rows in users, vehicles, rides, payments and ratings, then reload",
    )
    args = parser.parse_args(argv)

    cfg = get_db_config()
    try:
        conn = psycopg2.connect(connect_timeout=5, **cfg)
    except psycopg2.OperationalError as e:
        print(
            f"Could not connect to PostgreSQL at {cfg['host']}:{cfg['port']} "
            f"(database '{cfg['dbname']}', user '{cfg['user']}'). Check DB_* in .env.\n{e}"
        )
        return 1

    try:
        with conn, conn.cursor() as cursor:
            print(f"Connected to PostgreSQL ({cfg['host']}:{cfg['port']}/{cfg['dbname']})")
            cursor.execute(
                sql.SQL(CREATE_TABLES_SQL.replace("{schema}", "{s}")).format(
                    s=sql.Identifier(DB_SCHEMA)
                )
            )
            print("Tables ready.")

            if args.reset:
                cursor.execute(
                    sql.SQL("TRUNCATE TABLE {} CASCADE").format(
                        sql.SQL(", ").join(sql.Identifier(DB_SCHEMA, t) for t in TABLES)
                    )
                )
                print("Existing rows deleted (--reset).")

            non_empty = [t for t in TABLES if count(cursor, t) > 0]
            if non_empty:
                print(
                    f"Tables already contain data ({', '.join(non_empty)}). Nothing loaded.\n"
                    "Run with --reset to replace it with the sample CSVs."
                )
            else:
                print("Loading sample CSVs...")
                for table in TABLES:
                    load_csv(cursor, table)

            print("\nRecord counts:")
            for table in TABLES:
                print(f"  {table:<10} {count(cursor, table):>8,}")
        print("\nDone.")
        return 0
    except Exception as e:
        print(f"Loading failed, nothing was changed: {e}")
        return 1
    finally:
        conn.close()


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
