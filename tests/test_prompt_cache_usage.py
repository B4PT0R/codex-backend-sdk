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
