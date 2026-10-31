# Verification report

Tested on 2026-10-31 with Python 3.14.6, PostgreSQL 16 (password `1234`, port 5432), and the
exact package versions in `uv.lock` (anthropic 2.3.0, langchain-anthropic 1.7.7, langgraph 1.2.18, streamlit 1.66.1).

## Verified

| Check | Result |
|---|---|
| `uv sync` installs everything on Python 3.14 | Pass |
| `pip install -r requirements.txt` + `pip install -e . --no-deps` | Pass |
| All compiled packages have Windows (cp314 win_amd64 or abi3) wheels in `uv.lock` | Pass |
| All Python files compile; no hard-coded keys; no OpenAI code | Pass |
| Blank `ANTHROPIC_API_KEY` -> "ANTHROPIC_API_KEY is missing. Please add your Anthropic API key to the .env file." | Pass |
| Wrong DB password -> clear PostgreSQL connection message | Pass |
| `data-agent-load-db` creates tables and loads 61,073 rows; second run does not wipe data | Pass |
| Real request to api.anthropic.com with an invalid key -> friendly "authentication failed" message | Pass |
| Unreachable API -> friendly network error | Pass |
| Empty Claude reply -> friendly "empty response" message | Pass |
| Full SQL flow (router -> curate -> schema -> SQL -> judge -> execute -> answer) | Pass: result matched a direct `psql` query |
| Unsafe SQL (`DROP TABLE users`) blocked by the judge | Pass |
| Unsafe SQL sent straight to the database is refused by the read-only transaction | Pass |
| Long-running query stopped by the 15 s statement timeout | Pass |
| ETL extract (API -> `data/extract/extracted_data.csv`) | Pass |
| ETL transform (Claude-written Pandas code executed -> `data/transform/*.csv`) | Pass |
| Interactive loop (`python main.py`, blank lines, `exit`) | Pass |
| Streamlit app: setup panel, chat, SQL expander, example buttons, ETL file downloads | Pass (AppTest + real browser) |
| Streamlit app with no key / DB down: clear errors, chat input disabled | Pass |
| `uv run pytest`: 28 tests (Claude mocked, real PostgreSQL) | Pass |
| Requests use the intended model per step, native structured output for router/judge, no unsupported parameters | Pass |

The SQL and ETL flows above ran through the real Anthropic SDK and LangGraph, pointed at a
local stand-in API that returned scripted Claude replies, because no real key was available.

## Not verified (needs your key)

- The quality of real Claude answers and SQL against your own database.
- Whether your Anthropic account has access to all three default models
  (`claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`). If one is not available,
  set a different model in `.env`.
- Running on Windows itself (tested on Linux with the same Python and packages).
