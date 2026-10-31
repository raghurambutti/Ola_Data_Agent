"""Config, Claude helpers and error messages."""

import anthropic
import httpx2
import pytest
from langchain_core.messages import AIMessage

from data_agent import config
from data_agent.errors import DatabaseConnectionError, EmptyModelResponseError, friendly_error
from data_agent.llm import message_text, strip_code_fences

REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _status_error(cls, code):
    return cls("error", response=httpx2.Response(code, request=REQ), body=None)


def test_missing_api_key_has_clear_message(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    with pytest.raises(ValueError) as exc:
        config.get_api_key()
    assert str(exc.value) == (
        "ANTHROPIC_API_KEY is missing. Please add your Anthropic API key to the .env file."
    )
    assert friendly_error(exc.value) == config.MISSING_KEY_MESSAGE


def test_models_are_defined_in_one_place():
    assert set(config.MODELS) == {"low", "medium", "high"}
    assert all(m.startswith("claude-") for m in config.MODELS.values())


@pytest.mark.parametrize(
    "fenced, expected",
    [
        ("```sql\nSELECT 1;\n```", "SELECT 1;"),
        ("```python\nprint('x')\n```", "print('x')"),
        ("SELECT 2;", "SELECT 2;"),
        ("  ```\nSELECT 3\n```  ", "SELECT 3"),
    ],
)
def test_strip_code_fences(fenced, expected):
    assert strip_code_fences(fenced) == expected


def test_empty_model_reply_raises():
    with pytest.raises(EmptyModelResponseError):
        message_text(AIMessage(content=""))
    assert message_text(AIMessage(content=[{"type": "text", "text": " hi "}])) == "hi"


@pytest.mark.parametrize(
    "exc, phrase",
    [
        (_status_error(anthropic.AuthenticationError, 401), "authentication failed"),
        (_status_error(anthropic.PermissionDeniedError, 403), "permission"),
        (_status_error(anthropic.NotFoundError, 404), "model was not found"),
        (_status_error(anthropic.RateLimitError, 429), "rate limit"),
        (_status_error(anthropic.InternalServerError, 500), "server error"),
        (anthropic.APIConnectionError(request=REQ), "network error"),
        (anthropic.APITimeoutError(request=REQ), "timed out"),
        (EmptyModelResponseError("x"), "empty response"),
        (DatabaseConnectionError("Could not connect to PostgreSQL"), "Could not connect"),
    ],
)
def test_friendly_errors(exc, phrase):
    assert phrase.lower() in friendly_error(exc).lower()
