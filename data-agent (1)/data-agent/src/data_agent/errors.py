"""
Turns low-level exceptions into short, useful messages for the user.

The CLI calls `friendly_error(exc)` so a bad key, a rate limit or a stopped
database prints a one-line explanation instead of a long traceback.
"""

import anthropic
import psycopg2

from data_agent.config import MISSING_KEY_MESSAGE


class EmptyModelResponseError(RuntimeError):
    """Claude returned no usable text."""


class DatabaseConnectionError(RuntimeError):
    """PostgreSQL could not be reached."""


def friendly_error(exc: BaseException) -> str:
    """Map an exception to a human-readable message."""

    if isinstance(exc, ValueError) and str(exc) == MISSING_KEY_MESSAGE:
        return MISSING_KEY_MESSAGE

    # --- Anthropic API errors (order matters: most specific first) ---------
    if isinstance(exc, anthropic.AuthenticationError):
        return (
            "Anthropic rejected your API key (authentication failed). "
            "Check ANTHROPIC_API_KEY in the .env file - it should start with 'sk-ant-'."
        )
    if isinstance(exc, anthropic.PermissionDeniedError):
        return (
            "Your Anthropic API key does not have permission to use this model. "
            "Check your account at https://console.anthropic.com or change the model in .env."
        )
    if isinstance(exc, anthropic.NotFoundError):
        return (
            "The Claude model was not found. Check the CLAUDE_MODEL_* values in .env "
            f"(details: {_short(exc)})."
        )
    if isinstance(exc, anthropic.RateLimitError):
        return (
            "Anthropic rate limit reached, even after automatic retries. "
            "Wait a minute and try again, or check your usage limits in the Anthropic Console."
        )
    if isinstance(exc, anthropic.APITimeoutError):
        return "The request to Claude timed out. Check your internet connection and try again."
    if isinstance(exc, anthropic.APIConnectionError):
        return (
            "Could not reach the Anthropic API (network error). "
            "Check your internet connection, VPN or proxy and try again."
        )
    if isinstance(exc, anthropic.BadRequestError):
        return f"Claude rejected the request: {_short(exc)}"
    if isinstance(exc, anthropic.InternalServerError):
        return "Anthropic's API had a server error or is overloaded. Please try again shortly."
    if isinstance(exc, anthropic.APIStatusError):
        return f"Anthropic API error (HTTP {exc.status_code}): {_short(exc)}"
    if isinstance(exc, anthropic.AnthropicError):
        return f"Anthropic SDK error: {_short(exc)}"

    if isinstance(exc, EmptyModelResponseError):
        return f"Claude returned an empty response. Please rephrase and try again. ({exc})"

    # --- Database errors ----------------------------------------------------
    if isinstance(exc, DatabaseConnectionError):
        return str(exc)
    if isinstance(exc, psycopg2.Error):
        return f"PostgreSQL error: {_short(exc)}"

    return f"Unexpected error ({type(exc).__name__}): {_short(exc)}"


def _short(exc: BaseException, limit: int = 300) -> str:
    text = " ".join(str(exc).split())
    return text if len(text) <= limit else text[:limit] + "..."
