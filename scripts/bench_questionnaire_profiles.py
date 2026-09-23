"""Before/after hot-path timings for questionnaire detection changes.

Profiles from TASK_IMPROVE_PII_DETECTION §7. Writes aggregate numbers only.
"""


from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path

from llm_proxy.detection.models import MANDATORY_PII_TYPES

try:
    from scripts.bench_hot_path import build_engine, large_payload, pathological_cases
    from scripts.eval_labeled_sample import expected_fields
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from bench_hot_path import build_engine, large_payload, pathological_cases
    from eval_labeled_sample import expected_fields


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[index]


def _run_profile(name: str, texts: list[str], rounds: int = 3) -> dict[str, float]:
    engine = build_engine()
    # warmup
    for text in texts[: min(5, len(texts))]:
        engine.detect(text, MANDATORY_PII_TYPES)

    p95s: list[float] = []
    throughputs: list[float] = []
    for _ in range(rounds):
        timings: list[float] = []
        started = time.perf_counter()
        for text in texts:
            item_started = time.perf_counter()
            engine.detect(text, MANDATORY_PII_TYPES)
            timings.append(time.perf_counter() - item_started)
        elapsed = time.perf_counter() - started
        p95s.append(_percentile(timings, 95) * 1000.0)
        throughputs.append(len(texts) / elapsed if elapsed else 0.0)

    return {
        "p95_ms_median": statistics.median(p95s),
        "throughput_median": statistics.median(throughputs),
        "items": float(len(texts)),
        "rounds": float(rounds),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", default="")
    parser.add_argument("--tag", default="current")
    args = parser.parse_args()

    short_texts = [
        "ФИО: Тестов Иван; дата рождения: 01.01.1990; email: a@b.test;",
        "клиента зовут Иван Тестов, тел +7 900 111-22-33",
        "встреча 12.03.2024, код 123456789012",
    ]
    if args.sample:
        path = Path(args.sample)
        sample_lines = [
            line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        short_texts = sample_lines

    long_base = "слово " * 2_000
    long_texts = [
        long_base
        + "ФИО: Пример Пример; дата рождения: 01.02.1990; ИНН: 1234567890; "
        + "номер платёжной банковской карты: 4111 1111 1111 1111; "
        + "адрес — страна: Тест, индекс: 123456, город: Город, улица: Улица, дом: 1, квартира: 2;"
    ]

    huge = large_payload()
    pathological = list(pathological_cases().values())
    # Small labeled-rule probes (kept tiny so p95 stays driven by shared large/pathological inputs).
    pathological.append("ИНН: 123456789012; дата рождения: 01.01.1990; ФИО: Тест Тест;")
    pathological.append(
        "адрес — страна: X, индекс: 000000, город: Y, улица: Z, дом: 1, квартира: 2;"
    )

    profiles = {
        "short_or_sample": short_texts,
        "long_10k": long_texts * 30,
        "large_and_pathological": [huge, *pathological],
    }

    print(f"tag={args.tag}")
    for name, texts in profiles.items():
        stats = _run_profile(name, texts)
        print(
            f"profile={name} items={int(stats['items'])} rounds={int(stats['rounds'])} "
            f"p95_ms_median={stats['p95_ms_median']:.3f} "
            f"throughput_median={stats['throughput_median']:.2f}"
        )
        if name == "short_or_sample" and args.sample:
            # sanity: field extraction still finds expected labels
            assert expected_fields(texts[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
