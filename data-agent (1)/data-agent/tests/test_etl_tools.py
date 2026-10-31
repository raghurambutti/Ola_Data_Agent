"""ETL helpers (no network: requests.get is replaced)."""

import pandas as pd

from data_agent.config import PROJECT_ROOT
from data_agent.utils import etl_tools
from data_agent.utils.etl_tools import ETLTools, resolve_path


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_resolve_path_is_relative_to_project_root(tmp_path):
    assert resolve_path("data/extract") == (PROJECT_ROOT / "data/extract").resolve()
    assert resolve_path(str(tmp_path)) == tmp_path


def test_extract_load_unwraps_results_and_saves_csv(tmp_path, monkeypatch):
    payload = {"count": 2, "results": [{"name": "bulbasaur"}, {"name": "pidgey"}]}
    monkeypatch.setattr(etl_tools.requests, "get", lambda url, timeout: FakeResponse(payload))

    msg = ETLTools().extract_load("https://x", str(tmp_path), "csv")

    assert "2 rows" in msg
    df = pd.read_csv(tmp_path / "extracted_data.csv")
    assert df["name"].tolist() == ["bulbasaur", "pidgey"]


def test_extract_load_rejects_unknown_format(tmp_path):
    assert ETLTools().extract_load("https://x", str(tmp_path), "xml").startswith("Unsupported format")


def test_transform_context_and_execute_code(tmp_path):
    src = tmp_path / "in.csv"
    pd.DataFrame({"name": ["bulbasaur", "pidgey", "beedrill"]}).to_csv(src, index=False)

    context = ETLTools().transform_load_context(str(src))
    assert "bulbasaur" in context and "name" in context

    out = tmp_path / "out.csv"
    code = (
        f"df = pd.read_csv(r'{src}')\n"
        f"df[df['name'].str.startswith('b')].to_csv(r'{out}', index=False)\n"
        "print('rows', 2)"
    )
    result = ETLTools().execute_code(code)
    assert result.startswith("Code executed successfully") and "rows 2" in result
    assert pd.read_csv(out)["name"].tolist() == ["bulbasaur", "beedrill"]

    assert ETLTools().execute_code("1/0").startswith("Failed to execute code: ZeroDivisionError")
