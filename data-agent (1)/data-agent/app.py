"""
Streamlit web UI for the Ola AI Data Agent.

Run from the project folder:
    uv run streamlit run app.py
then open http://localhost:8501

All Claude and database calls happen here, in the Python server process.
Your API key is read from .env and is never sent to the browser.
"""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_agent.config import DATA_DIR, MODELS, get_api_key, get_db_config  # noqa: E402
from data_agent.errors import friendly_error  # noqa: E402

st.set_page_config(page_title="Ola AI Data Agent", page_icon="🚕", layout="wide")

EXAMPLES = [
    "How many rides were completed?",
    "Which 5 drivers have the highest average rating?",
    "What is the total revenue by payment method?",
    "Which cities have the most cancelled rides?",
    "Extract https://pokeapi.co/api/v2/pokemon and save it to data/extract as csv",
    "Transform data/extract/extracted_data.csv to keep only names starting with b "
    "and save it to data/transform as csv",
]


# --------------------------------------------------------------------------
# Setup checks (cached so they don't run on every click)
# --------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def check_setup() -> dict:
    status = {"key_ok": False, "key_msg": "", "db_ok": False, "db_msg": "", "tables": []}

    try:
        get_api_key()
        status["key_ok"] = True
        status["key_msg"] = "API key loaded from .env"
    except ValueError as e:
        status["key_msg"] = str(e)

    try:
        from data_agent.utils.database import DatabaseUtil

        db = DatabaseUtil()
        db.test_connection()
        schema = db.schema_details()
        status["tables"] = [
            line.split("Table: ", 1)[1].strip()
            for line in schema.splitlines()
            if line.startswith("Table: ")
        ]
        status["db_ok"] = True
        cfg = get_db_config()
        status["db_msg"] = f"Connected to {cfg['host']}:{cfg['port']}/{cfg['dbname']}"
    except Exception as e:
        status["db_msg"] = friendly_error(e)

    return status


def output_files() -> list[Path]:
    files = []
    for folder in ("extract", "transform"):
        d = DATA_DIR / folder
        if d.exists():
            files += [p for p in sorted(d.iterdir()) if p.is_file() and p.name != ".gitkeep"]
    return files


def run_agent(question: str) -> dict:
    """Run the Data Agent; return a result dict or an error dict."""
    try:
        from data_agent.agents.data_agent import ask

        result = ask(question)
        return {
            "route": result.get("route_response", ""),
            "route_comments": result.get("route_comments", ""),
            "sql": result.get("generated_sql_query", ""),
            "answer": result.get("final_answer") or "(no answer)",
        }
    except Exception as e:
        return {"error": friendly_error(e)}


def render_result(result: dict) -> None:
    if "error" in result:
        st.error(result["error"])
        return
    route = (result.get("route") or "?").upper()
    agent = {"SQL": "SQL Analyst", "ETL": "ETL Analyst"}.get(route, route)
    st.caption(f"Routed to **{agent}** - {result.get('route_comments', '')}")
    st.markdown(result["answer"])
    if result.get("sql"):
        with st.expander("SQL used"):
            st.code(result["sql"], language="sql")


# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------
status = check_setup()

with st.sidebar:
    st.header("Setup")
    (st.success if status["key_ok"] else st.error)(status["key_msg"])
    (st.success if status["db_ok"] else st.error)(status["db_msg"])
    if status["db_ok"]:
        if status["tables"]:
            st.caption("Tables: " + ", ".join(status["tables"]))
        else:
            st.warning("No tables found. Run `uv run data-agent-load-db` in the terminal.")
    if st.button("Re-check setup"):
        from dotenv import load_dotenv

        from data_agent.llm import pick_llm

        load_dotenv(PROJECT_ROOT / ".env", override=True)  # pick up a newly pasted key
        pick_llm.cache_clear()
        check_setup.clear()
        st.rerun()

    st.header("Models")
    st.caption(
        f"Low: `{MODELS['low']}`  \nMedium: `{MODELS['medium']}`  \nHigh: `{MODELS['high']}`"
    )

    st.header("Try an example")
    for i, example in enumerate(EXAMPLES):
        if st.button(example, key=f"ex{i}", use_container_width=True):
            st.session_state.pending_question = example

    files = output_files()
    if files:
        st.header("ETL output files")
        for path in files:
            st.download_button(
                f"{path.parent.name}/{path.name}",
                data=path.read_bytes(),
                file_name=path.name,
                key=f"dl-{path}",
                use_container_width=True,
            )

    if st.button("Clear chat"):
        st.session_state.history = []
        st.rerun()


# --------------------------------------------------------------------------
# Main chat
# --------------------------------------------------------------------------
st.title("🚕 Ola AI Data Agent")
st.caption(
    "Ask about the ride-sharing database (SQL Analyst) or ask for an ETL job "
    "(ETL Analyst). Powered by Claude, LangGraph and PostgreSQL."
)

if "history" not in st.session_state:
    st.session_state.history = []

for turn in st.session_state.history:
    with st.chat_message("user"):
        st.markdown(turn["question"])
    with st.chat_message("assistant"):
        render_result(turn["result"])

typed = st.chat_input("Ask a question...", disabled=not status["key_ok"])
question = typed or st.session_state.pop("pending_question", None)

if not status["key_ok"]:
    st.info(
        "Add your key to `.env` as `ANTHROPIC_API_KEY=sk-ant-...`, save the file, "
        "then click **Re-check setup** in the sidebar."
    )
elif question:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Claude is working on it..."):
            result = run_agent(question)
        render_result(result)
    st.session_state.history.append({"question": question, "result": result})
    if result.get("route", "").lower() == "etl":
        st.rerun()  # refresh the sidebar's output file list
