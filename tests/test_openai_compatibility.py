"""Guard the additive compatibility contract with the current OpenAI SDK."""

import inspect
import sys

import openai
import pytest
from openai import OpenAI as OfficialOpenAI
from openai.resources.audio.transcriptions import Transcriptions as OpenAITranscriptions
from openai.resources.embeddings import Embeddings as OpenAIEmbeddings
from openai.resources.files import Files as OpenAIFiles
from openai.resources.images import Images as OpenAIImages
from openai.resources.models import Models as OpenAIModels
from openai.resources.responses.responses import Responses as OpenAIResponses

from codex_backend_sdk.resources.images import Images
from codex_backend_sdk.resources.files import Files
from codex_backend_sdk.resources.models import Models
from codex_backend_sdk.resources.openai_oauth import AudioTranscriptions, Embeddings
from codex_backend_sdk.resources.responses import Responses


def _parameters(method):
    return set(inspect.signature(method).parameters) - {"self"}


@pytest.mark.parametrize(
    "surface, backend_method, official_method",
    [
        ("responses.create", Responses.create, OpenAIResponses.create),
        ("responses.parse", Responses.parse, OpenAIResponses.parse),
        ("responses.compact", Responses.compact, OpenAIResponses.compact),
        ("models.list", Models.list, OpenAIModels.list),
        ("models.retrieve", Models.retrieve, OpenAIModels.retrieve),
        ("images.generate", Images.generate, OpenAIImages.generate),
        ("images.edit", Images.edit, OpenAIImages.edit),
        ("embeddings.create", Embeddings.create, OpenAIEmbeddings.create),
        ("files.create", Files.create, OpenAIFiles.create),
        (
            "audio.transcriptions.create",
            AudioTranscriptions.create,
            OpenAITranscriptions.create,
        ),
    ],
)
def test_common_surfaces_accept_every_official_parameter(
    surface, backend_method, official_method
):
    missing = _parameters(official_method) - _parameters(backend_method)
    assert not missing, (
        f"{surface} is missing parameters added by openai-python {openai.__version__}: "
        f"{', '.join(sorted(missing))}"
    )

    backend_parameters = inspect.signature(backend_method).parameters
    official_parameters = inspect.signature(official_method).parameters
    newly_required = {
        name
        for name in official_parameters
        if name != "self"
        and official_parameters[name].default is not inspect.Parameter.empty
        and backend_parameters[name].default is inspect.Parameter.empty
    }
    assert not newly_required, (
        f"{surface} makes optional official parameters mandatory: "
        f"{', '.join(sorted(newly_required))}"
    )


def test_compatibility_baseline_uses_audited_openai_sdk():
    if sys.version_info < (3, 10):
        pytest.skip("openai-python 2.53.0 requires Python 3.10 or newer")
    version = tuple(int(part) for part in openai.__version__.split(".")[:3])
    assert version >= (2, 53, 0)
