"""Hot-path timings for detectors and one 100 000-token payload.

Ceilings live in tests/test_hot_path_bench.py and were chosen before the run.
They catch catastrophic scans. They are not the §7.1 load gate.
"""

from time import perf_counter

from llm_proxy.application.process_service import ProcessService
from llm_proxy.detection.contextual import register_contextual_detectors
from llm_proxy.detection.engine import PiiEngine
from llm_proxy.detection.models import MANDATORY_PII_TYPES
from llm_proxy.detection.registry import DetectorRegistry
from llm_proxy.detection.structured import register_structured_detectors
from llm_proxy.masking.placeholder import PlaceholderMaskStrategy
from llm_proxy.observability.tokens import count_tokens
from llm_proxy.policies.models import ConsumerContext, ConsumerPolicy
from llm_proxy.state.models import SessionRecord, StateStore

_TYPICAL = (
    "Клиент Иван Петров, тел. +7 900 111-22-33, synthetic@example.test, паспорт 45 12 654321."
)


class _MemoryStateStore(StateStore):
    def __init__(self) -> None:
        self.records: dict[str, SessionRecord] = {}

    async def get(self, key: str) -> SessionRecord | None:
        return self.records.get(key)

    async def create_if_absent(self, key: str, record: SessionRecord, ttl_seconds: int) -> bool:
        if key in self.records:
            return False
        self.records[key] = record
        return True

    async def update_ttl(self, key: str, ttl_seconds: int) -> bool:
        return key in self.records

    async def delete(self, key: str) -> bool:
        return self.records.pop(key, None) is not None


def build_engine() -> PiiEngine:
    registry = DetectorRegistry()
    register_structured_detectors(registry)
    register_contextual_detectors(registry)
    return PiiEngine(registry)


def time_detect(text: str, repeats: int = 5) -> float:
    engine = build_engine()
    engine.detect(text, MANDATORY_PII_TYPES)
    started = perf_counter()
    for _ in range(repeats):
        engine.detect(text, MANDATORY_PII_TYPES)
    return (perf_counter() - started) / repeats


def pathological_cases() -> dict[str, str]:
    return {
        "digits_100k": "1" * 100_000,
        "email_fragments": "a@" * 20_000,
        "passport_keyword": "серия " * 5_000,
        "capital_words": "Слово " * 20_000,
    }


def large_payload() -> str:
    body = "слово " * 99_990
    text = (
        f"{body}клиент Иван Петров тел +7 900 111-22-33 synthetic@example.test паспорт 45 12 654321"
    )
    return text


def time_large_mask() -> tuple[float, int]:
    import asyncio

    text = large_payload()
    tokens = count_tokens(text)
    engine = build_engine()
    service = ProcessService(
        state_store=_MemoryStateStore(),
        detector=engine,
        mask_strategy=PlaceholderMaskStrategy(),
    )
    policy = ConsumerPolicy(
        policy_id="policy-bench",
        system_id="bench",
        enabled=True,
        pii_types=MANDATORY_PII_TYPES,
        allow_demask=True,
        mask_strategy="placeholder",
    )
    context = ConsumerContext(consumer_id="bench", policy=policy)

    async def run() -> None:
        await service.process(context, "bench-warmup", text)
        await service.process(context, "bench-large", text)

    started = perf_counter()
    asyncio.run(run())
    return perf_counter() - started, tokens


def main() -> None:
    print(f"typical_s {time_detect(_TYPICAL):.4f}")
    print(f"long_s {time_detect(_TYPICAL * 40):.4f}")
    for name, text in pathological_cases().items():
        print(f"{name}_s {time_detect(text, repeats=3):.4f}")
    elapsed, tokens = time_large_mask()
    print(f"large_tokens {tokens}")
    print(f"large_mask_s {elapsed:.4f}")


if __name__ == "__main__":
    main()
