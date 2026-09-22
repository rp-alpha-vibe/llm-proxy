---
name: performance-review
description: Review and measure hot-path/runtime performance against hackathon targets: RPS, latency, large payloads, concurrency, overload behavior and pathological inputs.
---

# Performance Review

Используй, если изменение затрагивает:

- HTTP runtime;
- regex/scanners/NER hot path;
- state store;
- concurrency;
- serialization;
- deployment;
- batching/caching;
- rate limiting.

## Targets from requirements

Базовые цели:

- 1000 RPS;
- latency <= 1s как ориентир;
- 5 минут нагрузки;
- large payload support до 100 000 токенов;
- bonus target: 2000 RPS.

Не утверждай, что цель достигнута, без измерения.

## Минимальный профиль

Где применимо, измерить:

- p50/p95/p99 latency;
- sustained RPS;
- error rate;
- 429 rate;
- CPU;
- memory;
- behavior under concurrency.

Проверить несколько размеров payload:

- small;
- medium;
- large;
- worst-case/adversarial для regex или parser.

## Regex / scanner safety

Искать:

- catastrophic backtracking;
- повторное полное сканирование текста без необходимости;
- квадратичные проходы;
- uncontrolled allocations;
- копирование больших строк на каждом detector-е.

## Overload

Проверить, что перегрузка не приводит к:

- неограниченному росту очереди;
- runaway memory;
- длительному зависанию;
- каскаду 5xx.

Если используется 429, проверить корректный `Retry-After` и восстановление.

## Evidence

Всегда указывать:

- команду/tool;
- профиль нагрузки;
- окружение;
- результат;
- ограничение измерения.

Вердикт:

`pass | pass with follow-up | block`.

Локальный benchmark не выдавать за production capacity proof.
