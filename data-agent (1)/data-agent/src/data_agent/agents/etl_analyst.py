"""
ETL Analyst agent (LangGraph ReAct loop with tools).

  START -> llm_node -> (tool calls?) tool_node -> llm_node ... -> END

Tools:
  * extract_load_tool   - pull JSON from an API and save it as csv/json/parquet
  * transform_load_tool - have Claude write Pandas code for a transformation
                          and run it on a data file

Unlike the tutorial (which pasted the whole chat history into one string),
the conversation is passed to Claude as real messages, so tool calls and
tool results are paired correctly by the Messages API.
"""

from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph

from data_agent.config import DATA_DIR, PROJECT_ROOT
from data_agent.llm import invoke_text, pick_llm, strip_code_fences
from data_agent.schemas import ETLAgentSchema
from data_agent.utils.etl_tools import ETLTools, resolve_path

MAX_TOOL_ROUNDS = 6


# ------------------------------- Tools -------------------------------------
@tool
def extract_load_tool(url: str, output_folder: str, format: str) -> str:
    """
    Extract data from an API endpoint (url) and save it in output_folder.

    Args:
        url: The API endpoint to extract data from.
        output_folder: Folder to save into, e.g. "data/extract" (relative to the project root).
        format: File format to save: "csv", "json" or "parquet".
    """
    return ETLTools().extract_load(url, output_folder, format)


@tool
def transform_load_tool(
    input_file_path: str, output_folder: str, output_format: str, user_question: str
) -> str:
    """
    Transform the data in input_file_path as the user asked, and save the result
    to output_folder in output_format.

    Args:
        input_file_path: Data file to transform, e.g. "data/extract/extracted_data.csv".
        output_folder: Folder to save the transformed file in, e.g. "data/transform".
        output_format: "csv", "json" or "parquet".
        user_question: The user's description of the transformation to perform.
    """
    etl = ETLTools()
    input_path = resolve_path(input_file_path)
    output_path = resolve_path(output_folder)

    context = etl.transform_load_context(str(input_path))
    if context.startswith(("File not found", "Unsupported file format")):
        return context

    prompt = f"""
You are a Python Data Analyst who uses Pandas to analyze data.
Write only the Pandas code that performs the ETL operation the user asked for on the data
stored in the file: {input_path}
Do not provide any explanation or comments - only code that can run as-is in a Python
environment with Pandas installed.

Read the file into a DataFrame, apply the transformation, then save the result as
{output_format} inside the folder {output_path} (create the folder with
os.makedirs(..., exist_ok=True) if needed). Use a descriptive file name.
Use the absolute paths exactly as given above. Import everything you use.
Finally print() the full path of the saved file and the number of rows saved.

User's request: {user_question}

Context about the data:
{context}
"""
    pandas_code = strip_code_fences(invoke_text("high", prompt))
    result = etl.execute_code(pandas_code)

    return (
        f"Requested output: {output_path} ({output_format}).\n\n"
        f"Pandas code executed:\n{pandas_code}\n\nExecution result:\n{result}"
    )


TOOLS = [extract_load_tool, transform_load_tool]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

SYSTEM_PROMPT = f"""
You are a Python Data Analyst with tools that can extract and load data from APIs, and
transform and load data files. Perform the ETL operations the user asks for by calling
the tools. Relative paths are relative to the project folder {PROJECT_ROOT}
(its data folder is {DATA_DIR}). When the operation is done, tell the user briefly what
was done and where the output was saved, then stop. If a tool reports an error, explain it.
"""


# ------------------------------- Nodes -------------------------------------
def llm_node(state: ETLAgentSchema) -> dict:
    llm = pick_llm("high").bind_tools(TOOLS)

    # Stop looping forever if Claude keeps calling tools.
    tool_rounds = sum(1 for m in state.messages if isinstance(m, ToolMessage))
    if tool_rounds >= MAX_TOOL_ROUNDS:
        return {
            "messages": [
                AIMessage(content="Stopped after too many tool calls. Please simplify the request.")
            ]
        }

    reply = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), *state.messages])
    return {"messages": [reply]}


def tool_node(state: ETLAgentSchema) -> dict:
    results = []
    for call in state.messages[-1].tool_calls:
        selected = TOOLS_BY_NAME.get(call["name"])
        if selected is None:
            observation = f"Unknown tool: {call['name']}"
        else:
            try:
                observation = selected.invoke(call["args"])
            except Exception as e:  # report tool failures back to Claude
                observation = f"Tool error: {type(e).__name__}: {e}"
        results.append(ToolMessage(content=str(observation), tool_call_id=call["id"]))
    return {"messages": results}


def is_tool_call(state: ETLAgentSchema) -> str:
    last = state.messages[-1]
    return "tool_node" if getattr(last, "tool_calls", None) else "end"


# ------------------------------- Graph -------------------------------------
def build_etl_analyst():
    graph = StateGraph(ETLAgentSchema)
    graph.add_node("llm_node", llm_node)
    graph.add_node("tool_node", tool_node)
    graph.add_edge(START, "llm_node")
    graph.add_conditional_edges("llm_node", is_tool_call, {"tool_node": "tool_node", "end": END})
    graph.add_edge("tool_node", "llm_node")
    return graph.compile()


etl_analyst = build_etl_analyst()


if __name__ == "__main__":
    out = etl_analyst.invoke(
        {
            "messages": [
                HumanMessage(
                    content="Extract the data from 'https://pokeapi.co/api/v2/pokemon' "
                    "and save it to the data/extract folder as csv"
                )
            ]
        }
    )
    print(out["messages"][-1].text)
    print("Files:", [p.name for p in Path(DATA_DIR / "extract").iterdir()])
