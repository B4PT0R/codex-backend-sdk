import pytest

from codex_backend_sdk import ImageResponse, OpenAI


class FakeJSONResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeImagesClient(OpenAI):
    def __init__(self):
        super().__init__(model="gpt-test")
        self.posts = []

    def _post_raw(self, path, **kwargs):
        self.posts.append((path, kwargs))
        return FakeJSONResponse({
            "created": 1,
            "data": [{"b64_json": "aW1hZ2U="}],
            "background": "opaque",
            "quality": "medium",
            "size": "1024x1024",
        })


def test_images_generate_posts_codex_payload_and_returns_typed_response():
    client = FakeImagesClient()

    response = client.images.generate(
        prompt="a cheerful blue robot",
        background="opaque",
        n=1,
        quality="medium",
        size="1024x1024",
        extra_body={"custom": {"enabled": True}},
        timeout=180,
    )

    assert isinstance(response, ImageResponse)
    assert response.data[0].b64_json == "aW1hZ2U="
    assert response.background == "opaque"
    assert client.posts == [
        (
            "/images/generations",
            {
                "body": {
                    "prompt": "a cheerful blue robot",
                    "model": "gpt-image-2",
                    "background": "opaque",
                    "n": 1,
                    "quality": "medium",
                    "size": "1024x1024",
                    "custom": {"enabled": True},
                },
                "timeout": 180,
            },
        )
    ]


def test_images_edit_normalizes_urls_and_posts_codex_payload():
    client = FakeImagesClient()

    response = client.images.edit(
        images=[
            "data:image/png;base64,aW1hZ2U=",
            {"image_url": "https://example.test/reference.png"},
        ],
        prompt="add a red star",
        quality="low",
        timeout=240,
    )

    assert isinstance(response, ImageResponse)
    assert client.posts == [
        (
            "/images/edits",
            {
                "body": {
                    "images": [
                        {"image_url": "data:image/png;base64,aW1hZ2U="},
                        {"image_url": "https://example.test/reference.png"},
                    ],
                    "prompt": "add a red star",
                    "model": "gpt-image-2",
                    "quality": "low",
                },
                "timeout": 240,
            },
        )
    ]


@pytest.mark.parametrize(
    "images, match",
    [
        ([], "at least one"),
        ([""], "non-empty"),
        ([{}], "image_url"),
    ],
)
def test_images_edit_rejects_invalid_images(images, match):
    client = FakeImagesClient()

    with pytest.raises(ValueError, match=match):
        client.images.edit(images=images, prompt="add a star")


def test_images_generate_uses_minimal_default_payload():
    client = FakeImagesClient()

    client.images.generate(prompt="a red flower")

    _, kwargs = client.posts[0]
    assert kwargs["body"] == {
        "prompt": "a red flower",
        "model": "gpt-image-2",
    }


@pytest.mark.parametrize("field", ["prompt", "model"])
def test_images_generate_rejects_empty_required_fields(field):
    client = FakeImagesClient()
    arguments = {"prompt": "a red flower", "model": "gpt-image-2"}
    arguments[field] = ""

    with pytest.raises(ValueError, match=field):
        client.images.generate(**arguments)
