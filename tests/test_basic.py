"""Basic Responses, Models, and Codex-only resources."""

from codex_backend_sdk import CodexClient, Response


def test_responses_create_returns_text(client: CodexClient):
    response = client.responses.create(
        model="gpt-5.4",
        input="Reply with exactly: PONG",
    )

    assert isinstance(response, Response)
    assert "PONG" in response.output_text
    assert response.usage is not None
    assert response.usage.input_tokens > 0


def test_responses_create_stream_yields_events(client: CodexClient):
    events = list(client.responses.create(input="Say: hi", stream=True))

    assert any(event.type in {"response.output_text.delta", "response.content_part.delta"} for event in events)
    assert any(event.type == "response.completed" for event in events)


def test_models_list_and_retrieve(client: CodexClient):
    models = client.models.list()

    assert models.data, "No models returned"
    assert any("gpt" in model.id or "codex" in model.id for model in models)
    assert client.models.retrieve(models[0].id).id == models[0].id


def test_usage_returns_dict(client: CodexClient):
    quota = client.codex.usage()
    assert isinstance(quota, dict), f"Expected dict, got {type(quota)}"
