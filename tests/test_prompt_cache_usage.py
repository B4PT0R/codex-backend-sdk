import pytest

from codex_backend_sdk._models import ResponseUsage, TokenDetails
from codex_backend_sdk.resources._responses_payloads import _usage_from_backend


def test_response_usage_preserves_prompt_cache_reads_and_writes():
    usage = _usage_from_backend({
        "input_tokens": 2_048,
        "output_tokens": 32,
        "total_tokens": 2_080,
        "input_tokens_details": {
            "cached_tokens": 1_024,
            "cache_write_tokens": 768,
        },
    })

    assert usage.input_tokens_details.cached_tokens == 1_024
    assert usage.input_tokens_details.cache_write_tokens == 768


@pytest.mark.parametrize("details", [None, {}, {"cache_write_tokens": 12}, {"cached_tokens": None}])
def test_missing_cache_read_measurement_is_not_zero(details):
    usage = _usage_from_backend({"input_tokens": 100, "input_tokens_details": details})
    assert usage.input_tokens_details.cached_tokens is None


def test_omitted_usage_details_remain_unreported():
    assert _usage_from_backend({"input_tokens": 100}).input_tokens_details.cached_tokens is None
    assert ResponseUsage(input_tokens=100).input_tokens_details.cached_tokens is None
    assert TokenDetails().cached_tokens is None


def test_explicit_zero_cache_read_measurement_is_preserved():
    usage = _usage_from_backend({
        "input_tokens": 100, "input_tokens_details": {"cached_tokens": 0},
    })
    assert usage.input_tokens_details.cached_tokens == 0
