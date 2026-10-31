"""The LangGraph agents, run end to end with a fake Claude and a fake database."""

from langchain_core.messages import AIMessage, ToolMessage

from data_agent.schemas import JudgeSchema, RouterSchema

SAFE_SQL = "SELECT payment_method, COUNT(*) AS n FROM payments GROUP BY 1;"


def sql_script(sql=SAFE_SQL, verdict="Yes", route="sql"):
    def script(kind, prompt):
        if kind is RouterSchema:
            return RouterSchema(answer=route, comments="test route")
        if kind is JudgeSchema:
            return JudgeSchema(answer=verdict, comments="judge says " + verdict)
        text = prompt if isinstance(prompt, str) else str(prompt)
        if "Rewrite the following question" in text:
            return "How many payments per payment method?"
        if "PostgreSQL query" in text:
            return f"```sql\n{sql}\n```"
        if "Execution result" in text:
            return "Google Pay leads with 3,317 payments."
        return "ok"

    return script


def test_sql_analyst_safe_query_runs(fake_llm, fake_db):
    from data_agent.agents.sql_analyst import sql_analyst

    fake_llm(sql_script())
    result = sql_analyst.invoke({"user_question": "payments per method?"})

    assert result["generated_sql_query"] == SAFE_SQL  # code fence stripped
    assert fake_db.executed == [SAFE_SQL]
    assert result["final_answer"] == "Google Pay leads with 3,317 payments."
    # each message added once (the tutorial version duplicated them)
    assert [m.content for m in result["messages"]] == [
        "How many payments per payment method?",
        "Google Pay leads with 3,317 payments.",
    ]


def test_sql_analyst_unsafe_query_is_not_executed(fake_llm, fake_db):
    from data_agent.agents.sql_analyst import sql_analyst

    fake_llm(sql_script(sql="DROP TABLE users;", verdict="No"))
    result = sql_analyst.invoke({"user_question": "delete all users"})

    assert fake_db.executed == []
    assert "unsafe" in result["final_answer"]
    assert "judge says No" in result["final_answer"]


def test_router_sends_database_questions_to_sql(fake_llm, fake_db):
    from data_agent.agents.data_agent import ask

    fake_llm(sql_script(route="sql"))
    result = ask("How many payments per method?")

    assert result["route_response"] == "sql"
    assert result["generated_sql_query"] == SAFE_SQL
    assert result["final_answer"].startswith("Google Pay")


def test_router_sends_etl_requests_to_etl_agent(fake_llm, monkeypatch):
    import data_agent.agents.etl_analyst as etl
    from data_agent.agents.data_agent import ask

    calls = []
    monkeypatch.setattr(
        etl.ETLTools,
        "extract_load",
        lambda self, url, folder, fmt: calls.append((url, folder, fmt)) or "saved 4 rows",
    )

    def script(kind, prompt):
        if kind is RouterSchema:
            return RouterSchema(answer="etl", comments="api extract")
        last = prompt[-1]
        if isinstance(last, ToolMessage):
            return AIMessage(content=f"Done: {last.content}")
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "extract_load_tool",
                    "args": {"url": "https://example.com/api", "output_folder": "data/extract", "format": "csv"},
                    "id": "toolu_1",
                }
            ],
        )

    fake_llm(script)
    result = ask("Extract https://example.com/api to data/extract as csv")

    assert result["route_response"] == "etl"
    assert calls == [("https://example.com/api", "data/extract", "csv")]
    assert result["final_answer"] == "Done: saved 4 rows"
