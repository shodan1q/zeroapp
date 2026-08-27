"""Tests for node retry behaviour, including non-retryable failures."""

from __future__ import annotations

import pytest

from zerodev.llm import LLMConfigError, LLMError
from zerodev.pipeline.retry import _is_retryable, with_retry
from zerodev.pipeline.state import RetryPolicy

# Zero backoff keeps these tests fast; the schedule itself is not under test.
_FAST = RetryPolicy(max_retries=2, backoff_base=0.0, backoff_max=0.0)


def _counting_node(exc: Exception | None, calls: list[int]):
    @with_retry(policy=_FAST, node_name="probe")
    async def node(state):
        calls.append(1)
        if exc is not None:
            raise exc
        return {"ok": True}

    return node


async def test_successful_node_resets_retry_count() -> None:
    calls: list[int] = []
    result = await _counting_node(None, calls)({})
    assert result["ok"] is True
    assert result["retry_count"] == 0
    assert len(calls) == 1


async def test_transient_error_is_retried_to_exhaustion() -> None:
    calls: list[int] = []
    result = await _counting_node(LLMError("502 upstream"), calls)({})
    assert len(calls) == _FAST.max_retries + 1
    assert result["failed"] is True
    assert result["retry_count"] == _FAST.max_retries + 1


async def test_config_error_fails_without_retrying() -> None:
    # A missing base URL will still be missing after a backoff; spending the
    # retry budget on it only delays the error the operator needs to see.
    calls: list[int] = []
    result = await _counting_node(LLMConfigError("no base url"), calls)({})
    assert len(calls) == 1
    assert result["failed"] is True
    assert result["retry_count"] == 1
    assert "no base url" in result["errors"][0]


async def test_unknown_exceptions_stay_retryable() -> None:
    calls: list[int] = []
    await _counting_node(ValueError("boom"), calls)({})
    assert len(calls) == _FAST.max_retries + 1


async def test_errors_accumulate_onto_existing_state() -> None:
    calls: list[int] = []
    result = await _counting_node(LLMConfigError("x"), calls)({"errors": ["earlier"], "retry_count": 5})
    assert result["errors"][0] == "earlier"
    assert result["retry_count"] == 6


def test_is_retryable_defaults_to_true() -> None:
    assert _is_retryable(ValueError("x")) is True
    assert _is_retryable(LLMError("x")) is True
    assert _is_retryable(LLMConfigError("x")) is False


def test_config_error_stays_catchable_by_existing_handlers() -> None:
    # Call sites written as `except (anthropic.APIError, LLMError)` -- and older
    # ones catching RuntimeError -- must both keep working.
    assert issubclass(LLMConfigError, LLMError)
    assert issubclass(LLMConfigError, RuntimeError)
    with pytest.raises(LLMError):
        raise LLMConfigError("x")


def test_overload_backs_off_much_harder_than_a_blip() -> None:
    # An empty SSE stream is how a saturated relay says "too many"; retrying it
    # on the normal schedule is what turned overload into a collapsed batch.
    from zerodev.llm import LLMError, LLMOverloadedError, _retry_delay

    assert _retry_delay(1, LLMOverloadedError("empty")) > _retry_delay(1, LLMError("blip")) * 4
    assert _retry_delay(9, LLMOverloadedError("empty")) <= 120.0


def test_overloaded_is_still_retryable() -> None:
    from zerodev.llm import LLMOverloadedError
    from zerodev.pipeline.retry import _is_retryable

    assert _is_retryable(LLMOverloadedError("empty")) is True
