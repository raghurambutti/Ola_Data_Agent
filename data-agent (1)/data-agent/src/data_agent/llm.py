"""
Claude model factory (replaces the tutorial's `utils/llm_pick.py`).

The tutorial mixed OpenAI and Anthropic models. This project uses Anthropic
only, through `langchain-anthropic` (which calls the official `anthropic`
SDK and the Messages API underneath), so LangGraph keeps working unchanged.
"""

from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage

from data_agent.config import (
    LLM_MAX_RETRIES,
    LLM_TIMEOUT_SECONDS,
    MAX_TOKENS,
    MODELS,
    get_api_key,
)
from data_agent.errors import EmptyModelResponseError


@lru_cache(maxsize=None)
def pick_llm(level: str) -> ChatAnthropic:
    """
    Return the Claude chat model for a task level: "low", "medium" or "high".
    Model IDs are defined in config.py and can be overridden in .env.
    """
    level = level.lower()
    if level not in MODELS:
        raise ValueError(f"Unsupported level: {level!r}. Use one of {sorted(MODELS)}.")

    return ChatAnthropic(
        model=MODELS[level],
        api_key=get_api_key(),
        max_tokens=MAX_TOKENS[level],
        max_retries=LLM_MAX_RETRIES,
        timeout=LLM_TIMEOUT_SECONDS,
    )


def message_text(message: BaseMessage) -> str:
    """Plain text of a Claude reply, raising if the reply is empty."""
    text = (message.text or "").strip()
    if not text:
        raise EmptyModelResponseError("no text in model reply")
    return text


def invoke_text(level: str, prompt) -> str:
    """Send a prompt (string or message list) and return the reply text."""
    return message_text(pick_llm(level).invoke(prompt))


def strip_code_fences(text: str) -> str:
    """Remove ```sql / ```python fences Claude may wrap code in."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]  # drop ```lang
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text
