"""
PostgreSQL helper (ported from the tutorial's `utils/database.py`).

Fixes compared with the tutorial version:
  * a fresh connection per operation (the original closed its only connection
    after the first call, so the second call always failed)
  * columns are filtered by schema and listed in table order
  * queries run inside a READ ONLY transaction with a timeout, as a second
    safety layer behind the "LLM as a judge" check
  * no hard-coded password and no code that runs on import
"""

import psycopg2
from psycopg2 import sql

from data_agent.config import (
    DB_SCHEMA,
    SQL_MAX_ROWS,
    SQL_STATEMENT_TIMEOUT_MS,
    get_db_config,
)
from data_agent.errors import DatabaseConnectionError


class DatabaseUtil:
    def __init__(self, db_config: dict | None = None):
        self.db_config = db_config or get_db_config()

    def _connect(self):
        try:
            return psycopg2.connect(connect_timeout=5, **self.db_config)
        except psycopg2.OperationalError as e:
            cfg = self.db_config
            raise DatabaseConnectionError(
                "Could not connect to PostgreSQL at "
                f"{cfg['host']}:{cfg['port']} (database '{cfg['dbname']}', user '{cfg['user']}'). "
                "Make sure PostgreSQL is running and DB_* values in .env are correct. "
                f"Details: {' '.join(str(e).split())}"
            ) from e

    def test_connection(self) -> None:
        """Raise DatabaseConnectionError if the database is unreachable."""
        conn = self._connect()
        conn.close()

    def schema_details(self, schema_name: str = DB_SCHEMA) -> str:
        """
        Describe every table in `schema_name`: columns, data types and five
        sample rows. This text is the context Claude uses to write SQL.
        """
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                context = f"Database Schema: {schema_name}\n"

                cursor.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_type = 'BASE TABLE' "
                    "ORDER BY table_name;",
                    (schema_name,),
                )
                tables = [row[0] for row in cursor.fetchall()]

                if not tables:
                    return context + "\n(No tables found in this schema.)\n"

                for table_name in tables:
                    context += f"\nTable: {table_name}\n"

                    cursor.execute(
                        "SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_schema = %s AND table_name = %s "
                        "ORDER BY ordinal_position;",
                        (schema_name, table_name),
                    )
                    for column_name, data_type in cursor.fetchall():
                        context += f"  Column: {column_name}, Data Type: {data_type}\n"

                    cursor.execute(
                        sql.SQL("SELECT * FROM {}.{} LIMIT 5;").format(
                            sql.Identifier(schema_name), sql.Identifier(table_name)
                        )
                    )
                    context += "  Sample Data:\n"
                    for row in cursor.fetchall():
                        context += f"    {row}\n"

                return context
        finally:
            conn.close()

    def execute_sql(self, query: str) -> str:
        """
        Run a query in a read-only transaction and return the result as text
        (column names + up to SQL_MAX_ROWS rows). Errors are returned as text
        so Claude can explain them to the user instead of crashing the graph.
        """
        conn = self._connect()
        try:
            conn.set_session(readonly=True)
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SET LOCAL statement_timeout = {}").format(
                        sql.Literal(SQL_STATEMENT_TIMEOUT_MS)
                    )
                )
                cursor.execute(query)

                if cursor.description is None:
                    return "Query executed. It returned no rows."

                columns = [col.name for col in cursor.description]
                rows = cursor.fetchmany(SQL_MAX_ROWS + 1)
                truncated = len(rows) > SQL_MAX_ROWS
                rows = rows[:SQL_MAX_ROWS]

                lines = [f"Columns: {columns}"]
                if not rows:
                    lines.append("(no rows)")
                lines.extend(str(row) for row in rows)
                if truncated:
                    lines.append(f"(output truncated to the first {SQL_MAX_ROWS} rows)")
                return "\n".join(lines)
        except psycopg2.Error as e:
            return f"Error executing query: {' '.join(str(e).split())}"
        finally:
            conn.rollback()
            conn.close()
