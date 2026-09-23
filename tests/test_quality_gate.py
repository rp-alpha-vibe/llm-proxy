from llm_proxy.detection.models import MANDATORY_PII_TYPES
from llm_proxy.quality.gate import BASELINE_FIXTURE_COUNT
from llm_proxy.quality.runner import evaluate, render_report


def test_quality_gate_covers_every_mandatory_type() -> None:
    report = evaluate()
    assert report.fixture_count == BASELINE_FIXTURE_COUNT
    assert report.ok, render_report(report)
    assert report.uncovered == ()
    assert {pii_type.value for pii_type in MANDATORY_PII_TYPES} <= set(report.scores)
