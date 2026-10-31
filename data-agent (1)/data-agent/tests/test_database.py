"""
Integration tests against a real PostgreSQL (uses the DB_* settings in .env
or the environment). Skipped automatically when the database isn't reachable.
"""

import pytest

from data_agent.errors import DatabaseConnectionError
from data_agent.utils.database import DatabaseUtil


@pytest.fixture(scope="module")
def db():
    util = DatabaseUtil()
    try:
        util.test_connection()
    except DatabaseConnectionError as e:
        pytest.skip(f"PostgreSQL not available: {e}")
    if "Table: rides" not in util.schema_details():
        pytest.skip("Sample tables not loaded (run data-agent-load-db)")
    return util


def test_schema_lists_tables_columns_and_samples(db):
    schema = db.schema_details()
    for table in ("users", "rides", "payments", "ratings", "vehicles"):
        assert f"Table: {table}" in schema
    assert "Column: fare, Data Type: numeric" in schema
    assert "Sample Data:" in schema


def test_select_returns_columns_and_rows(db):
    result = db.execute_sql("SELECT status, COUNT(*) AS n FROM rides GROUP BY status ORDER BY n DESC")
    assert result.startswith("Columns: ['status', 'n']")
    assert "completed" in result


def test_writes_are_refused_by_read_only_transaction(db):
    before = db.execute_sql("SELECT COUNT(*) FROM users")
    result = db.execute_sql("DELETE FROM users")
    assert "read-only transaction" in result
    assert db.execute_sql("SELECT COUNT(*) FROM users") == before


def test_wrong_password_gives_clear_error():
    from data_agent.config import get_db_config

    cfg = get_db_config() | {"password": "definitely-wrong-password"}
    with pytest.raises(DatabaseConnectionError) as exc:
        DatabaseUtil(cfg).test_connection()
    assert "Could not connect to PostgreSQL" in str(exc.value)
