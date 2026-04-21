"""Reasoning — effort levels, reasoning tokens, ReasoningDelta events."""

from codex_backend_sdk import CodexClient, ReasoningDelta, ResponseCompleted, TextDelta

# Questions complex enough to reliably trigger reasoning tokens.
# Trivial arithmetic (2+2, 3x=15) is answered directly without reasoning.
_HARD_MATH = (
    "A train leaves city A at 9 am at 60 mph. "
    "Another leaves city B (300 miles away) at 10 am toward A at 90 mph. "
    "At what time do they meet? Show only the final answer (HH:MM am/pm)."
)
_LOGIC = (
    "I have a 4×4 grid. I want to place 4 non-attacking rooks "
    "(no two share a row or column). How many arrangements are there? "
    "Give only the number."
)


def test_reasoning_tokens_consumed(client: CodexClient):
    events = list(client.stream(_HARD_MATH, reasoning="medium"))
    done = next((e for e in events if isinstance(e, ResponseCompleted)), None)
    assert done is not None, "No ResponseCompleted event"
    assert done.usage.reasoning_tokens > 0, (
        f"Expected reasoning_tokens > 0, got {done.usage.reasoning_tokens}"
    )


def test_no_reasoning_tokens_without_reasoning(client: CodexClient):
    events = list(client.stream("What is the capital of France?"))
    done = next((e for e in events if isinstance(e, ResponseCompleted)), None)
    assert done is not None
    assert done.usage.reasoning_tokens == 0


def test_reasoning_delta_emitted(client: CodexClient):
    # Reasoning content is delivered as a completed "reasoning" output item,
    # not as streaming deltas. Pick a model that supports reasoning summaries.
    import pytest
    models = client.list_models()
    summary_model = next(
        (m.slug for m in models if m.supports_reasoning_summaries and m.supported_in_api),
        None,
    )
    if summary_model is None:
        pytest.skip("No API model supports reasoning summaries for this account")

    events = list(client.stream(
        _LOGIC,
        model=summary_model,
        reasoning="medium",
        reasoning_summary="concise",
        include_reasoning=True,
    ))
    reasoning_events = [e for e in events if isinstance(e, ReasoningDelta)]
    assert reasoning_events, (
        f"No ReasoningDelta event from {summary_model!r} — "
        "reasoning output item may be missing or empty"
    )
    combined = "".join(e.text for e in reasoning_events)
    assert combined.strip(), "ReasoningDelta has empty content"


def test_reasoning_per_call_override(client: CodexClient):
    """Session default reasoning=medium can be suppressed per call with reasoning=None."""
    c = CodexClient(reasoning="medium").authenticate()

    # With session default — complex question to ensure tokens are spent
    events_with = list(c.stream(_HARD_MATH))
    done_with = next(e for e in events_with if isinstance(e, ResponseCompleted))

    # Override to None for this call
    events_without = list(c.stream("What is the capital of Spain?", reasoning=None))
    done_without = next(e for e in events_without if isinstance(e, ResponseCompleted))

    assert done_with.usage.reasoning_tokens > 0, (
        f"Expected reasoning with session default, got {done_with.usage.reasoning_tokens}"
    )
    assert done_without.usage.reasoning_tokens == 0, (
        f"Expected 0 reasoning after override, got {done_without.usage.reasoning_tokens}"
    )
