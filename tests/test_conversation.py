"""Multi-turn conversation — context propagation across turns."""

from codex_backend_sdk import CodexClient, TextDelta


def _drain_text(client: CodexClient, context: list[dict]) -> str:
    """Stream with None user_message (context already contains the user turn)."""
    parts: list[str] = []
    for event in client.stream(None, conversation_history=context):
        if isinstance(event, TextDelta):
            parts.append(event.text)
    return "".join(parts)


def _user_item(text: str) -> dict:
    return {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": text}],
    }


def _assistant_item(text: str) -> dict:
    return {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text}],
    }


def test_model_remembers_name(client: CodexClient):
    context: list[dict] = []

    # Turn 1: introduce a name
    context.append(_user_item("My name is Alice. Just acknowledge with OK."))
    reply1 = _drain_text(client, context)
    context.append(_assistant_item(reply1))

    # Turn 2: ask the model to recall it
    context.append(_user_item("What is my name?"))
    reply2 = _drain_text(client, context)

    assert "Alice" in reply2, f"Model forgot the name. Got: {reply2!r}"


def test_context_accumulates_correctly(client: CodexClient):
    context: list[dict] = []

    context.append(_user_item("Remember the number 42. Just say OK."))
    reply1 = _drain_text(client, context)
    context.append(_assistant_item(reply1))

    context.append(_user_item("What number did I ask you to remember?"))
    reply2 = _drain_text(client, context)

    assert "42" in reply2, f"Model lost the number. Got: {reply2!r}"


def test_three_turn_conversation(client: CodexClient):
    context: list[dict] = []

    context.append(_user_item("I'm planning a trip to Japan. Just say OK."))
    r1 = _drain_text(client, context)
    context.append(_assistant_item(r1))

    context.append(_user_item("What country am I going to?"))
    r2 = _drain_text(client, context)
    context.append(_assistant_item(r2))
    assert "Japan" in r2, f"Turn 2 lost context: {r2!r}"

    context.append(_user_item("Name one city I could visit there."))
    r3 = _drain_text(client, context)
    assert r3.strip(), "Empty reply on turn 3"
