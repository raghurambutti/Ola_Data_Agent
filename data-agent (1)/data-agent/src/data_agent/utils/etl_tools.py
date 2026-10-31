"""
ETL helpers used by the ETL Analyst's tools (ported from the tutorial's
`utils/etl_tools.py`).

Paths given by the user (e.g. "data/extract") are resolved against the
project root, so they work no matter which folder you start the app from.
"""

import io
import contextlib
from pathlib import Path

import pandas as pd
import requests

from data_agent.config import PROJECT_ROOT

SUPPORTED_FORMATS = ("csv", "json", "parquet")


def resolve_path(path: str) -> Path:
    """Absolute path; relative paths are taken from the project root."""
    p = Path(path).expanduser()
    return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


class ETLTools:
    def extract_load(self, url: str, output_folder: str, format: str) -> str:
        """Download JSON from `url`, flatten it and save it to `output_folder`."""
        format = format.lower().strip().lstrip(".")
        if format not in SUPPORTED_FORMATS:
            return f"Unsupported format: {format}. Use one of {', '.join(SUPPORTED_FORMATS)}."

        folder = resolve_path(output_folder)

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            return f"Failed to extract data: {e}"
        except ValueError:
            return f"Failed to extract data: {url} did not return JSON."

        # Many APIs wrap records in "results" (e.g. PokeAPI) or "data".
        if isinstance(data, dict):
            for key in ("results", "data", "items", "records"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break

        df = pd.json_normalize(data)
        if df.empty:
            return f"The API at {url} returned no records."

        folder.mkdir(parents=True, exist_ok=True)
        filename = folder / f"extracted_data.{format}"

        if format == "csv":
            df.to_csv(filename, index=False)
        elif format == "json":
            df.to_json(filename, orient="records", lines=True)
        else:
            df.to_parquet(filename, index=False)

        return (
            f"Data successfully extracted and saved to {filename} "
            f"({len(df)} rows, columns: {list(df.columns)})"
        )

    def transform_load_context(self, file_path: str) -> str:
        """Return the first rows and column types of a data file as context for Claude."""
        path = resolve_path(file_path)
        if not path.exists():
            return f"File not found: {path}"

        ext = path.suffix.lower()
        if ext == ".csv":
            df = pd.read_csv(path)
        elif ext == ".json":
            df = pd.read_json(path, lines=True)
        elif ext == ".parquet":
            df = pd.read_parquet(path)
        else:
            return f"Unsupported file format: {ext}"

        return (
            f"Columns and types:\n{df.dtypes.to_string()}\n\n"
            f"First 3 rows:\n{df.head(3).to_string()}"
        )

    def execute_code(self, code: str) -> str:
        """
        Execute Pandas code written by Claude and return its printed output.

        WARNING: like the tutorial, this runs AI-generated Python on your
        machine. Only use the ETL agent with prompts and data you trust.
        """
        namespace = {"pd": pd, "Path": Path, "PROJECT_ROOT": PROJECT_ROOT, "__name__": "__etl__"}
        stdout = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout):
                exec(code, namespace)
        except Exception as e:
            return f"Failed to execute code: {type(e).__name__}: {e}"
        printed = stdout.getvalue().strip()
        return "Code executed successfully." + (f"\nOutput:\n{printed[:2000]}" if printed else "")
