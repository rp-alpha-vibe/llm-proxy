"""Safety bounds for hot-path scans.

Fixed before the first measurement. A pass only shows the scan finished
inside the bound. It is not a §7.1 1000 RPS or p95 result.
"""

from scripts.bench_hot_path import large_payload, pathological_cases, time_detect, time_large_mask

from llm_proxy.observability.tokens import count_tokens

PATHOLOGICAL_MAX_SECONDS = 1.0
LARGE_PAYLOAD_MAX_SECONDS = 10.0


def test_pathological_detector_scans_stay_bounded() -> None:
    for name, text in pathological_cases().items():
        elapsed = time_detect(text, repeats=1)
        assert elapsed < PATHOLOGICAL_MAX_SECONDS, name


def test_hundred_thousand_token_payload_stays_bounded() -> None:
    assert count_tokens(large_payload()) >= 100_000
    elapsed, tokens = time_large_mask()
    assert tokens >= 100_000
    assert elapsed < LARGE_PAYLOAD_MAX_SECONDS
