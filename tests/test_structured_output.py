"""Structured output — JSON Schema enforcement via output_schema."""

import json

from codex_backend_sdk import CodexClient

_PERSON_SCHEMA = {
    "title": "person",
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age":  {"type": "integer"},
    },
    "required": ["name", "age"],
    "additionalProperties": False,
}

_COUNTRY_SCHEMA = {
    "title": "country_info",
    "type": "object",
    "properties": {
        "name":       {"type": "string"},
        "capital":    {"type": "string"},
        "population": {"type": "integer"},
    },
    "required": ["name", "capital", "population"],
    "additionalProperties": False,
}


def test_extract_person(client: CodexClient):
    text, _ = client.respond(
        "Extract: Bob is 42 years old.",
        output_schema=_PERSON_SCHEMA,
    )
    data = json.loads(text)
    assert data["name"] == "Bob"
    assert data["age"] == 42


def test_extract_country(client: CodexClient):
    text, _ = client.respond(
        "Give me info about France as JSON. Population circa 68 million.",
        output_schema=_COUNTRY_SCHEMA,
    )
    data = json.loads(text)
    assert data["name"].lower() == "france"
    assert "paris" in data["capital"].lower()
    assert isinstance(data["population"], int)
    assert data["population"] > 60_000_000


def test_output_is_valid_json(client: CodexClient):
    text, _ = client.respond(
        "List three primary colors.",
        output_schema={
            "title": "colors",
            "type": "object",
            "properties": {
                "colors": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["colors"],
            "additionalProperties": False,
        },
    )
    data = json.loads(text)
    assert isinstance(data["colors"], list)
    assert len(data["colors"]) == 3
