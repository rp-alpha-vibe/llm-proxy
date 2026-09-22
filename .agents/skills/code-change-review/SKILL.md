---
name: code-change-review
description: Read-only review of nontrivial implementation changes for correctness, failure behavior, security/privacy, performance risk, and misleading verification evidence.
---

# Code Change Review

Работай как скептический reviewer. Не исправляй код в этом проходе.

## Вход

Используй актуальный контекст; прочитай недостающее или изменившееся:

- `AGENTS.md`;
- релевантные требования;
- общий task brief и его разделы требований/архитектуры, если они были;
- полный diff;
- затронутый код и тесты.

Объём проверки выбирай по `AGENTS.md`, §4.1. Подключай применимые доменные skills как разделы одного review, без повторного чтения того же diff и отдельных отчётов.

## Pass 1 — Contract and behavior

Проверь:

- реализован ли принятый контракт;
- выполнены ли acceptance criteria;
- нет ли случайного расширения scope;
- корректны ли state transitions;
- корректны ли retry/idempotency;
- не подменяют ли тесты реальное требование.

## Pass 2 — Failure behavior

Проверь минимально применимую матрицу:

| Scenario | Question |
| --- | --- |
| first request | correct result/state? |
| retry | same observable result? |
| concurrent duplicate | race/data corruption? |
| malformed input | bounded clear failure? |
| dependency unavailable | safe degradation? |
| restart | required state recoverable? |
| overload | bounded latency / 429 behavior? |

## Security/privacy

Ищи:

- raw PII в logs/metrics/traces/errors;
- secrets в code/config/fixtures;
- чувствительные данные в committed tests;
- чрезмерное хранение исходных payloads;
- unsafe debug output.

## Verification quality

Зелёный тест считается доказательством только если он наблюдает нужное поведение.

Для важного negative path должны быть:

1. stimulus;
2. observable expected outcome.

## Findings

Классифицируй:

- P0: активный severe security/data-loss риск;
- P1: correctness/security/reliability defect, блокирующий сдачу;
- P2: существенный bounded weakness;
- P3: локальная maintainability/clarity проблема.

Верни сначала findings, затем проверенные вещи, затем verdict. Не перечисляй неприменимые пункты ради заполнения отчёта:

`pass | pass with follow-up | block`.

Стандартный change может review-ить тот же агент отдельным проходом.
Открытый P0/P1 или неподтверждённый обязательный критерий означает `block`. После исправлений перепроверь изменённое поведение и diff; повторяй весь review только при существенном расширении риска.
