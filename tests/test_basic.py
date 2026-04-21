"""Basic streaming, respond(), list_models(), usage()."""

from codex_backend_sdk import CodexClient, ResponseCompleted, ResponseFailed, TextDelta


def test_stream_yields_text_and_completion(client: CodexClient):
    events = list(client.stream("Reply with exactly: PONG"))
    text_events = [e for e in events if isinstance(e, TextDelta)]
    done_events = [e for e in events if isinstance(e, ResponseCompleted)]
    fail_events = [e for e in events if isinstance(e, ResponseFailed)]

    assert not fail_events, f"Stream failed: {fail_events[0].message}"
    assert text_events, "No TextDelta events received"
    assert done_events, "No ResponseCompleted event received"

    full_text = "".join(e.text for e in text_events)
    assert "PONG" in full_text

    done = done_events[0]
    assert done.input_tokens > 0
    assert done.output_tokens > 0


def test_respond_returns_text(client: CodexClient):
    text, completion = client.respond(
        "What is 2 + 2? Reply with just the number, nothing else."
    )
    assert text.strip(), "Empty response"
    assert "4" in text
    assert completion is not None
    assert completion.total_tokens > 0


def test_respond_print_stream(client: CodexClient, capsys):
    text, _ = client.respond("Say: hi", print_stream=True)
    captured = capsys.readouterr()
    assert text.strip()
    assert captured.out.strip()


def test_list_models(client: CodexClient):
    models = client.list_models()
    assert models, "No models returned"
    slugs = [m.slug for m in models]
    assert any("gpt" in s or "codex" in s for s in slugs), f"Unexpected slugs: {slugs}"
    # Models should be sorted by priority descending
    priorities = [m.priority for m in models]
    assert priorities == sorted(priorities, reverse=True)


def test_get_model(client: CodexClient):
    models = client.list_models()
    first = models[0]
    found = client.get_model(first.slug)
    assert found is not None
    assert found.slug == first.slug


def test_get_model_unknown(client: CodexClient):
    assert client.get_model("nonexistent-model-xyz") is None


def test_usage_returns_dict(client: CodexClient):
    quota = client.usage()
    assert isinstance(quota, dict), f"Expected dict, got {type(quota)}"
