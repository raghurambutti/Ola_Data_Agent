"""
Data Agent - the orchestrator / router (LangGraph).

  START -> router_node -> (sql) sql_node -> END
                       -> (etl) etl_node -> END

Claude classifies each request with structured output (RouterSchema) and the
request is handed to the SQL Analyst or the ETL Analyst sub-graph.
"""

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from data_agent.agents.etl_analyst import etl_analyst
from data_agent.agents.sql_analyst import sql_analyst
from data_agent.llm import message_text, pick_llm
from data_agent.schemas import DataAgentSchema, RouterSchema

ROUTER_PROMPT = """
You are the router of a data agent for a ride-sharing company (similar to Ola/Uber).
Decide which specialist should handle the user's request:

- "sql": questions answered by querying the company's PostgreSQL database
  (tables such as users, drivers/riders, rides, payments, ratings, vehicles), e.g.
  counts, totals, averages, top-N lists, trends.
- "etl": extracting data from an API or URL and saving it to files, or
  transforming/cleaning/filtering data files (csv, json, parquet).

User's request:
{request}
"""


def _last_user_text(state: DataAgentSchema) -> str:
    for message in reversed(state.messages):
        if isinstance(message, HumanMessage):
            return message.text
    return state.messages[-1].text if state.messages else ""


def router_node(state: DataAgentSchema) -> dict:
    router = pick_llm("medium").with_structured_output(RouterSchema, method="json_schema")
    decision = router.invoke(ROUTER_PROMPT.format(request=_last_user_text(state)))
    return {"route_response": decision.answer, "route_comments": decision.comments}


def sql_node(state: DataAgentSchema) -> dict:
    result = sql_analyst.invoke({"user_question": _last_user_text(state)})
    answer = result["final_answer"]
    return {
        "final_answer": answer,
        "generated_sql_query": result.get("generated_sql_query", ""),
        "messages": [AIMessage(content=answer)],
    }


def etl_node(state: DataAgentSchema) -> dict:
    result = etl_analyst.invoke({"messages": [HumanMessage(content=_last_user_text(state))]})
    answer = message_text(result["messages"][-1])
    return {"final_answer": answer, "messages": [AIMessage(content=answer)]}


def route_edge(state: DataAgentSchema) -> str:
    if state.route_response == "sql":
        return "sql_node"
    if state.route_response == "etl":
        return "etl_node"
    raise ValueError(f"Invalid route response: {state.route_response!r}")


def build_data_agent():
    graph = StateGraph(DataAgentSchema)
    graph.add_node("router_node", router_node)
    graph.add_node("sql_node", sql_node)
    graph.add_node("etl_node", etl_node)
    graph.add_edge(START, "router_node")
    graph.add_conditional_edges(
        "router_node", route_edge, {"sql_node": "sql_node", "etl_node": "etl_node"}
    )
    graph.add_edge("sql_node", END)
    graph.add_edge("etl_node", END)
    return graph.compile()


data_agent = build_data_agent()


def ask(question: str) -> dict:
    """Run one question through the Data Agent and return the final state."""
    return data_agent.invoke({"messages": [HumanMessage(content=question)]})
