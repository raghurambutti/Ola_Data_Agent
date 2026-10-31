"""
Command-line interface for the Data Agent.

  uv run data-agent                       interactive mode
  uv run data-agent "How many rides were completed?"   one question
  uv run data-agent --check               check the API key and database only
"""

import argparse
import sys

from data_agent.config import MODELS, get_api_key
from data_agent.errors import friendly_error

BANNER = """
==============================================================
  Ola AI Data Agent  (Claude + LangGraph + PostgreSQL)
==============================================================
Ask a question about the ride-sharing database, for example:
  - How many rides were completed in total?
  - Which 5 drivers have the highest average rating?
  - What is the total revenue by payment method?
Or ask for an ETL job, for example:
  - Extract https://pokeapi.co/api/v2/pokemon and save it to data/extract as csv
  - Transform data/extract/extracted_data.csv to keep only names starting
    with 'b' and save it to data/transform as csv
Type 'exit' to quit.
"""


def preflight(require_db: bool = True) -> bool:
    """Check the API key and database before taking questions."""
    try:
        get_api_key()
    except ValueError as e:
        print(f"\n[ERROR] {e}\n")
        return False

    if not require_db:
        return True

    from data_agent.utils.database import DatabaseUtil

    try:
        db = DatabaseUtil()
        db.test_connection()
        schema = db.schema_details()
    except Exception as e:
        print(f"\n[ERROR] {friendly_error(e)}\n")
        return False

    if "(No tables found" in schema:
        print(
            "\n[WARNING] Connected to PostgreSQL, but no tables were found. "
            "Load the sample data with:  uv run data-agent-load-db\n"
        )
    return True


def answer(question: str) -> None:
    from data_agent.agents.data_agent import ask

    print("\nThinking...")
    try:
        result = ask(question)
    except Exception as e:
        print(f"\n[ERROR] {friendly_error(e)}\n")
        return

    route = result.get("route_response", "")
    print(f"\n[Route: {route.upper() or '?'}] {result.get('route_comments', '')}")
    if result.get("generated_sql_query"):
        print("\nSQL used:\n" + result["generated_sql_query"])
    print("\nAnswer:\n" + (result.get("final_answer") or "(no answer)") + "\n")


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="data-agent", description="Ola AI Data Agent")
    parser.add_argument("question", nargs="*", help="Ask one question and exit")
    parser.add_argument(
        "--check", action="store_true", help="Check the API key and database, then exit"
    )
    args = parser.parse_args(argv)

    if not preflight():
        return 1

    print(
        f"Models -> low: {MODELS['low']} | medium: {MODELS['medium']} | high: {MODELS['high']}"
    )

    if args.check:
        print("Setup OK: API key is set and PostgreSQL is reachable.")
        return 0

    if args.question:
        answer(" ".join(args.question))
        return 0

    print(BANNER)
    while True:
        try:
            question = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            return 0
        if not question:
            continue
        if question.lower() in {"exit", "quit", "q"}:
            print("Goodbye!")
            return 0
        answer(question)


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
