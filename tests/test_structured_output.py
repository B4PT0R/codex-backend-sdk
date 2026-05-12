"""Structured output through official Responses text.format."""

import json

from codex_backend_sdk import CodexClient


def _json_schema(schema: dict) -> dict:
    return {
        "format": {
            "type": "json_schema",
            "name": schema["title"],
            "schema": schema,
            "strict": True,
        }
    }


def test_extract_person(client: CodexClient):
    schema = {
        "title": "person",
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
        "required": ["name", "age"],
        "additionalProperties": False,
    }

    response = client.responses.create(
        input="Extract: Bob is 42 years old.",
        text=_json_schema(schema),
    )
    data = json.loads(response.output_text)
    assert data["name"] == "Bob"
    assert data["age"] == 42


def test_output_is_valid_json(client: CodexClient):
    schema = {
        "title": "colors",
        "type": "object",
        "properties": {
            "colors": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["colors"],
        "additionalProperties": False,
    }

    response = client.responses.create(
        input="List three primary colors.",
        text=_json_schema(schema),
    )
    data = json.loads(response.output_text)
    assert isinstance(data["colors"], list)
    assert len(data["colors"]) == 3
