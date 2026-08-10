import pytest

from codex_backend_sdk import OpenAI


class FakeWritingBlockClient(OpenAI):
    def __init__(self):
        super().__init__()
        self.calls = []

    def _post_chatgpt(self, path, *, body, **kwargs):
        self.calls.append((path, body, kwargs))
        if path.endswith("magic-edit"):
            return {"choices": ["replacement"], "model_slug": "model"}
        return {"status": "ok"}


def test_writing_block_update_preserves_official_payload():
    client = FakeWritingBlockClient()
    body = {
        "conversation_id": "conversation-1",
        "message_id": "message-1",
        "id": "block-1",
        "index": "0",
        "updated_at": "2026-08-10T00:00:00Z",
        "writing_block": {
            "id": "block-1",
            "index": "0",
            "title": "Draft",
            "content": "Hello",
            "metadata": {},
            "variant": "standard",
        },
    }

    assert client.chatgpt.writing_blocks.update(body) == {"status": "ok"}
    assert client.calls == [
        ("/conversation/message/writing-blocks", body, {})
    ]


def test_writing_block_magic_edit_builds_desktop_contract():
    client = FakeWritingBlockClient()

    response = client.chatgpt.writing_blocks.magic_edit(
        conversation_id="conversation-1",
        full_block_body_markdown="Hello world",
        start_index=6,
        end_index=11,
        marked_block_body_markdown="Hello ⟦MAGICSTART⟧world⟦MAGICEND⟧",
        instruction="Make it warmer",
        num_variations=2,
        mode="full-edit",
        timeout=15,
    )

    assert response["choices"] == ["replacement"]
    assert client.calls == [
        (
            "/conversation/message/writing-blocks/magic-edit",
            {
                "conversation_id": "conversation-1",
                "full_block_body_markdown": "Hello world",
                "start_index": 6,
                "end_index": 11,
                "marked_block_body_markdown": (
                    "Hello ⟦MAGICSTART⟧world⟦MAGICEND⟧"
                ),
                "instruction": "Make it warmer",
                "num_variations": 2,
                "mode": "full-edit",
            },
            {"timeout": 15},
        )
    ]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"start_index": -1}, "start_index"),
        ({"start_index": 6, "end_index": 5}, "end_index"),
        ({"end_index": 12}, "end_index"),
        ({"num_variations": 0}, "num_variations"),
        ({"instruction": ""}, "instruction"),
        ({"conversation_id": ""}, "conversation_id"),
        ({"mode": "unknown"}, "mode"),
    ],
)
def test_writing_block_magic_edit_rejects_invalid_boundaries(overrides, message):
    client = FakeWritingBlockClient()
    arguments = {
        "conversation_id": "conversation-1",
        "full_block_body_markdown": "Hello world",
        "start_index": 0,
        "end_index": 5,
        "marked_block_body_markdown": "⟦MAGICSTART⟧Hello⟦MAGICEND⟧ world",
        "instruction": "Improve it",
        **overrides,
    }

    with pytest.raises(ValueError, match=message):
        client.chatgpt.writing_blocks.magic_edit(**arguments)


def test_writing_block_magic_edit_validates_response_shape():
    client = FakeWritingBlockClient()
    client._post_chatgpt = lambda *args, **kwargs: {"choices": "invalid"}

    with pytest.raises(RuntimeError, match="choices"):
        client.chatgpt.writing_blocks.magic_edit(
            conversation_id="conversation-1",
            full_block_body_markdown="Hello",
            start_index=0,
            end_index=5,
            marked_block_body_markdown="⟦MAGICSTART⟧Hello⟦MAGICEND⟧",
            instruction="Improve it",
        )


def test_writing_block_update_requires_object_payload():
    client = FakeWritingBlockClient()
    with pytest.raises(TypeError, match="JSON object"):
        client.chatgpt.writing_blocks.update(["invalid"])
