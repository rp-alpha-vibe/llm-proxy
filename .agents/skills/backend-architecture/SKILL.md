---
name: backend-architecture
description: Design the smallest complete backend solution before nontrivial changes to API boundaries, state/storage, concurrency, retry/idempotency, dependencies, security, runtime/deployment, observability, or performance.
---

# Backend Architecture

Работай как архитектор, не как implementer.

## Когда использовать

Skill нужен, если реализация должна выбрать или изменить:

- API/module boundary;
- state storage;
- concurrency/retry/idempotency;
- dependency;
- security/privacy boundary;
- runtime/deployment;
- performance/SLO semantics.

Локальным изменениям без новых границ skill не нужен.

## Цель

Выбрать **самое простое решение, которое полностью закрывает требования и риски текущей задачи**.

Не проектировать будущие микросервисы, очереди, БД, абстракции и универсальные framework-слои «на потом».

## Architecture Brief

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

Обычный brief должен укладываться примерно в 40 строк.

## Правило скорости

Не создавай отдельный ADR, threat model, sequence diagram или большой design doc, если конкретный риск не требует этого.

Если есть одна очевидная обратимая реализация в согласованном scope, выбери её и продолжай.

Если выбор меняет security/privacy model, внешний контракт или труднообратимую зависимость, дай рекомендацию и запроси решение владельца.

## После реализации

Отдельный architecture-conformance ritual не требуется.
Соответствие brief проверяет `code-change-review`.
