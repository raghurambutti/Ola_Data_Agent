"""
Central configuration for the Data Agent.

Everything you might want to change lives here or in the `.env` file:
  * Claude model IDs (one per tier)
  * PostgreSQL connection details
  * Folder paths

Secrets (the Anthropic API key, the database password) are ONLY read from
the environment / `.env` file and are never hard-coded.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root = the folder that contains `.env`, `main.py` and `data/`
# (this file lives at <root>/src/data_agent/config.py).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

load_dotenv(PROJECT_ROOT / ".env")


# --------------------------------------------------------------------------
# Claude models
# --------------------------------------------------------------------------
# The tutorial picks a model per "level" of task. Override any of these in
# `.env` without touching code, e.g.  CLAUDE_MODEL_HIGH=claude-sonnet-5-5
#
#   low    -> cheap/fast work: curating the question, writing the final answer
#   medium -> SQL generation, the "LLM as a judge" safety check, routing
#   high   -> the ETL ReAct agent and the Pandas code it writes
DEFAULT_MODELS = {
    "low": "claude-haiku-5-5",
    "medium": "claude-sonnet-5-5",
    "high": "claude-opus-5-5",
}

MODELS = {
    "low": os.getenv("CLAUDE_MODEL_LOW") or DEFAULT_MODELS["low"],
    "medium": os.getenv("CLAUDE_MODEL_MEDIUM") or DEFAULT_MODELS["medium"],
    "high": os.getenv("CLAUDE_MODEL_HIGH") or DEFAULT_MODELS["high"],
}

MAX_TOKENS = {
    "low": 2048,
    "medium": 4096,
    "high": 8192,
}

# Seconds to wait for a single Claude request, and automatic retries
# (the SDK retries rate limits, overloads and connection errors itself).
LLM_TIMEOUT_SECONDS = float(os.getenv("CLAUDE_TIMEOUT_SECONDS") or 120)
LLM_MAX_RETRIES = int(os.getenv("CLAUDE_MAX_RETRIES") or 2)


# --------------------------------------------------------------------------
# Anthropic API key
# --------------------------------------------------------------------------
MISSING_KEY_MESSAGE = (
    "ANTHROPIC_API_KEY is missing. Please add your Anthropic API key to the .env file."
)


def get_api_key() -> str:
    """Return the Anthropic API key or raise a clear error if it is not set."""
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        raise ValueError(MISSING_KEY_MESSAGE)
    return api_key


# --------------------------------------------------------------------------
# PostgreSQL
# --------------------------------------------------------------------------
def get_db_config() -> dict:
    """Connection settings for psycopg2, read from `.env`."""
    return {
        "host": os.getenv("DB_HOST") or "localhost",
        "port": int(os.getenv("DB_PORT") or 5432),
        "user": os.getenv("DB_USER") or "postgres",
        "password": os.getenv("DB_PASSWORD") or "",
        "dbname": os.getenv("DB_NAME") or "postgres",
    }


DB_SCHEMA = os.getenv("DB_SCHEMA") or "public"

# Max rows returned to Claude from a query, and max seconds a query may run.
SQL_MAX_ROWS = int(os.getenv("SQL_MAX_ROWS") or 50)
SQL_STATEMENT_TIMEOUT_MS = int(os.getenv("SQL_STATEMENT_TIMEOUT_MS") or 15000)
