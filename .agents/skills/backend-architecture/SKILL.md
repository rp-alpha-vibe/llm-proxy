---
name: backend-architecture
description: Add the smallest complete design to the task brief when changing API/module boundaries, state/storage semantics, concurrency, retry/idempotency, material runtime dependencies, security, deployment or execution/SLO models. Skip local optimizations within accepted boundaries.
---

# Backend Architecture

Сначала прочитай релевантные разделы `docs/ARCHITECTURE.md`. Принятая архитектура является baseline: не переоткрывай её без нового требования, benchmark/quality evidence или явного решения владельца.

Если задача действительно меняет архитектурную границу, сначала выбери минимальное изменение, затем продолжай реализацию в том же рабочем цикле.

## Когда использовать

Skill нужен, если реализация должна выбрать или изменить:

- API/module boundary;
- state storage;
- concurrency/retry/idempotency;
- существенную runtime-зависимость;
- security/privacy boundary;
- runtime/deployment;
- модель выполнения/SLO; для локальной оптимизации в принятых границах достаточно `performance-review`.

Локальным изменениям без новых границ skill не нужен.

## Цель

Выбрать **самое простое решение, которое полностью закрывает требования и риски текущей задачи**.

Не проектировать будущие микросервисы, очереди, БД, абстракции и универсальные framework-слои «на потом».

## Архитектурный раздел общего task brief

Дополни существующий brief. Не повторяй уже записанные требования, Goal и Verification. Заполни только применимые поля:

```md
# Architecture Brief

Goal:
Relevant requirements:
Current behavior:

Critical flow:
...

Boundaries:
- ...

State:
- what
- where
- lifecycle

Failure behavior:
- retry
- concurrency
- dependency failure
- restart/recovery

Security:
- sensitive data exposure
- logs/metrics/traces

Performance:
- expected hot path
- budget

Verification:
- tests/bench/load checks

Decision:
- chosen option
- why
- rejected material alternative(s), only if relevant
```

Обычный архитектурный раздел должен укладываться примерно в 40 строк; простой выбор может занимать несколько предложений.

## Правило скорости

Не создавай отдельный ADR, threat model, sequence diagram или большой design doc, если конкретный риск не требует этого.

Если решение уже предусмотрено `docs/ARCHITECTURE.md`, следуй ему и не создавай новый architecture brief.
Если есть одна очевидная обратимая реализация внутри принятых границ, выбери её и продолжай.

Если выбор меняет security/privacy model, внешний контракт или труднообратимую зависимость, дай рекомендацию и запроси решение владельца.

## После реализации

Отдельный architecture-conformance ritual не требуется.
Соответствие brief проверяет `code-change-review`.
