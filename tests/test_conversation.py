"""Multi-turn conversation with explicit Responses input items."""

from codex_backend_sdk import CodexClient


def _user(text: str) -> dict:
    return {"role": "user", "content": text}


def _assistant(text: str) -> dict:
    return {"role": "assistant", "content": text}


def test_model_remembers_name(client: CodexClient):
    history: list[dict] = [_user("My name is Alice. Just acknowledge with OK.")]
    reply1 = client.responses.create(input=history).output_text
    history.append(_assistant(reply1))
    history.append(_user("What is my name?"))

    reply2 = client.responses.create(input=history).output_text

    assert "Alice" in reply2, f"Model forgot the name. Got: {reply2!r}"


def test_context_accumulates_correctly(client: CodexClient):
    history: list[dict] = [_user("Remember the number 42. Just say OK.")]
    reply1 = client.responses.create(input=history).output_text
    history.append(_assistant(reply1))
    history.append(_user("What number did I ask you to remember?"))

    reply2 = client.responses.create(input=history).output_text

    assert "42" in reply2, f"Model lost the number. Got: {reply2!r}"
