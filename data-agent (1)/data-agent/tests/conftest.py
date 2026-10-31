"""
Shared test fixtures.

Tests never call the real Anthropic API: `fake_llm` replaces every Claude
model with a scripted fake, so the suite is free, fast and runs without a key.
"""

import os
import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Dummy key so code paths that require one can run; nothing is sent anywhere.
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test-not-a-real-key"


class FakeStructured:
    def __init__(self, llm, schema):
        self.llm, self.schema = llm, schema

    def invoke(self, prompt):
        self.llm.calls.append(("structured", self.schema.__name__, _text(prompt)))
        return self.llm.script(self.schema, _text(prompt))


class FakeLLM:
    """A stand-in for ChatAnthropic driven by a script function.

    script(kind, prompt) returns:
      * for kind == "text":  a str or an AIMessage
      * for kind == a Pydantic class (structured output): an instance of it
    """

    def __init__(self, script):
        self.script = script
        self.calls = []

    def invoke(self, prompt):
        self.calls.append(("text", None, _text(prompt)))
        out = self.script("text", prompt)
        return out if isinstance(out, AIMessage) else AIMessage(content=out)

    def with_structured_output(self, schema, **kwargs):
        return FakeStructured(self, schema)

    def bind_tools(self, tools, **kwargs):
        return self


def _text(prompt):
    if isinstance(prompt, str):
        return prompt
    return "\n".join(str(getattr(m, "content", m)) for m in prompt)


@pytest.fixture
def fake_llm(monkeypatch):
    """Install a FakeLLM everywhere pick_llm is used. Call it with a script."""

    def install(script):
        llm = FakeLLM(script)
        import data_agent.agents.data_agent as da
        import data_agent.agents.etl_analyst as etl
        import data_agent.agents.sql_analyst as sqla
        import data_agent.llm as llm_module

        for module in (llm_module, sqla, etl, da):
            monkeypatch.setattr(module, "pick_llm", lambda level, _llm=llm: _llm)
        return llm

    return install


class FakeDB:
    """Records queries instead of touching PostgreSQL."""

    executed: list = []

    def __init__(self, *args, **kwargs):
        pass

    def schema_details(self, schema_name="public"):
        return "Database Schema: public\n\nTable: payments\n  Column: payment_method, Data Type: character varying\n"

    def execute_sql(self, query):
        FakeDB.executed.append(query)
        return "Columns: ['payment_method', 'n']\n('google_pay', 3317)\n('apple_pay', 3301)"


@pytest.fixture
def fake_db(monkeypatch):
    import data_agent.agents.sql_analyst as sqla

    FakeDB.executed = []
    monkeypatch.setattr(sqla, "DatabaseUtil", FakeDB)
    return FakeDB
