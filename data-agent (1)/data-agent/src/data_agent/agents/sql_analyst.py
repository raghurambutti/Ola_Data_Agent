"""
SQL Analyst agent (LangGraph).

  START -> curate_ques -> prompt_query_context -> generate_sql -> is_safe_sql
        -> (safe)   execute_sql -> represent_final_answer -> END
        -> (unsafe) canceled_sql -> END

Each node returns only the fields it changes. (The tutorial returned the
whole state, which duplicated messages because `messages` uses an `add`
reducer.)
"""

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from data_agent.config import DB_SCHEMA
from data_agent.llm import invoke_text, pick_llm, strip_code_fences
from data_agent.schemas import AgentSchema, JudgeSchema
from data_agent.utils.database import DatabaseUtil


# ------------------------------- Nodes -------------------------------------
def curate_ques(state: AgentSchema) -> dict:
    """Rewrite the user's question so it is clear and unambiguous."""
    prompt = (
        "Rewrite the following question about a ride-sharing company's database so it is "
        "clear, specific and unambiguous. Keep the user's intent and any numbers, dates or "
        "names exactly as given. Reply with the rewritten question only.\n\n"
        f"Question: {state.user_question}"
    )
    curated = invoke_text("low", prompt)
    return {"curated_ques": curated, "messages": [HumanMessage(content=curated)]}


def prompt_query_context(state: AgentSchema) -> dict:
    """Build the SQL-generation prompt with the live database schema."""
    schema_info = DatabaseUtil().schema_details(DB_SCHEMA)

    prompt = f"""
You are an SQL analyst agent. Your task is to convert the user's natural language
query into a PostgreSQL query that can be executed on the database. You are provided
with the user's query and the schema details of the database, including table names,
column names, data types and sample data for each table, so that you can understand
the structure of the database and generate an accurate SQL query.
Unless the user explicitly asks for a specific number of rows, always limit the output to 10 rows.
Only write read-only SELECT queries (WITH ... SELECT is fine).
Note - Just generate the SQL query without any explanation, comments or markdown,
because this query will be executed directly on the database.

User's Query: {state.curated_ques}

Database Schema Details:
{schema_info}
"""
    return {"prompt_query_context": prompt}


def generate_sql(state: AgentSchema) -> dict:
    sql_query = strip_code_fences(invoke_text("medium", state.prompt_query_context))
    return {"generated_sql_query": sql_query}


def is_safe_sql(state: AgentSchema) -> dict:
    """'LLM as a judge': only read-only queries may run."""
    # Native structured outputs: current Sonnet/Opus models don't support the
    # forced tool calling the tutorial's default relied on.
    judge = pick_llm("medium").with_structured_output(JudgeSchema, method="json_schema")

    prompt = f"""
You are an SQL Judge for data security. Your task is to determine whether the SQL query is
safe or not. The SQL query should only be used for data retrieval and must not modify the
database in any way. It must not contain any command that can change the structure or
content of the database, such as INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE,
GRANT, REVOKE, COPY or CALL. If the SQL query is safe, answer 'Yes', otherwise answer 'No',
and explain your decision in the comments.

Here's the SQL query to evaluate:
{state.generated_sql_query}
"""
    verdict = judge.invoke(prompt)
    return {"is_safe": verdict.answer, "comments": verdict.comments}


def canceled_sql(state: AgentSchema) -> dict:
    final = (
        "The generated SQL query was judged unsafe to execute, so it was not run. "
        f"Reason given by the judge: {state.comments}"
    )
    return {"final_answer": final, "messages": [AIMessage(content=final)]}


def execute_sql(state: AgentSchema) -> dict:
    result = DatabaseUtil().execute_sql(state.generated_sql_query)
    return {"sql_query_execution_result": result}


def represent_final_answer(state: AgentSchema) -> dict:
    prompt = f"""
You are an SQL analyst agent. Give the user a final answer based on the execution result of
the SQL query and the user's question. The answer should be concise, clear and directly
address the question. Do not include SQL code or technical details. Use a short list or
small table when there are several rows. If the execution result is empty, an error, or does
not answer the question, say so plainly.

Execution result:
{state.sql_query_execution_result}

User's question: {state.curated_ques}
"""
    answer = invoke_text("low", prompt)
    return {"final_answer": answer, "messages": [AIMessage(content=answer)]}


def is_safe_sql_edge(state: AgentSchema) -> str:
    return "execute_sql" if state.is_safe.lower() == "yes" else "canceled_sql"


# ------------------------------- Graph -------------------------------------
def build_sql_analyst():
    graph = StateGraph(AgentSchema)

    graph.add_node("curate_ques", curate_ques)
    graph.add_node("prompt_query_context", prompt_query_context)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("is_safe_sql", is_safe_sql)
    graph.add_node("canceled_sql", canceled_sql)
    graph.add_node("execute_sql", execute_sql)
    graph.add_node("represent_final_answer", represent_final_answer)

    graph.add_edge(START, "curate_ques")
    graph.add_edge("curate_ques", "prompt_query_context")
    graph.add_edge("prompt_query_context", "generate_sql")
    graph.add_edge("generate_sql", "is_safe_sql")
    graph.add_conditional_edges(
        "is_safe_sql",
        is_safe_sql_edge,
        {"execute_sql": "execute_sql", "canceled_sql": "canceled_sql"},
    )
    graph.add_edge("canceled_sql", END)
    graph.add_edge("execute_sql", "represent_final_answer")
    graph.add_edge("represent_final_answer", END)

    return graph.compile()


sql_analyst = build_sql_analyst()


if __name__ == "__main__":
    result = sql_analyst.invoke(
        {"user_question": "What are the different types of payment methods in our database?"}
    )
    print("SQL:", result["generated_sql_query"])
    print("Result:", result["sql_query_execution_result"])
    print("Answer:", result["final_answer"])
