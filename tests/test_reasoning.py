"""Reasoning through the official Responses reasoning parameter."""

import pytest
from codex_backend_sdk import CodexClient

_HARD_MATH = (
    "A train leaves city A at 9 am at 60 mph. "
    "Another leaves city B (300 miles away) at 10 am toward A at 90 mph. "
    "At what time do they meet? Show only the final answer (HH:MM am/pm)."
)


def test_reasoning_tokens_consumed(client: CodexClient):
    response = client.responses.create(
        input=_HARD_MATH,
        reasoning={"effort": "medium"},
    )

    assert response.usage.output_tokens_details.reasoning_tokens > 0


def test_reasoning_summary_output_item_when_supported(client: CodexClient):
    summary_model = next(
        (
            model.id
            for model in client.models.list()
            if getattr(model, "supports_reasoning_summaries", False)
            and getattr(model, "supported_in_api", False)
        ),
        None,
    )
    if summary_model is None:
        pytest.skip("No API model supports reasoning summaries for this account")

    response = client.responses.create(
        model=summary_model,
        input="How many ways can 4 non-attacking rooks be placed on a 4x4 board?",
        include=["reasoning.encrypted_content"],
        reasoning={"effort": "medium", "summary": "concise"},
    )

    reasoning_items = [item for item in response.output if item.get("type") == "reasoning"]
    assert reasoning_items
