---
name: release-verification
description: Final lightweight acceptance gate for a task. Verify fresh tests, acceptance criteria, relevant domain reviews, security hygiene, and known limitations before calling work done.
---

# Release Verification

Это финальная приёмка, а не ещё один большой аудит.

## Проверить

1. Goal достигнут.
2. Acceptance criteria имеют наблюдаемое доказательство.
3. Релевантные тесты запущены свежо, результаты и exit codes прочитаны.
4. Для nontrivial change был `code-change-review`.
5. Для PII-изменений был `pii-quality-review`.
6. Для hot-path/runtime/performance изменений был `performance-review`.
7. Нет открытых P0/P1.
8. Нет секретов и реальных ПД в diff, fixtures, логах, документации.
9. Known limitations названы честно.

## Три слоя

### Technical
lint/typecheck/unit/integration/build/contract tests — только применимые.

### Engineering
error handling, idempotency, concurrency, security, observability, recovery — только затронутые.

### Domain
соответствие требованиям хакатона, PII quality и/или performance evidence.

## Выход

```text
Verdict: pass | pass with follow-up | block

Acceptance:
- ...

Fresh verification:
- command/check -> result

Reviews:
- ...

Known limitations:
- ...

Next safe step:
- ...
```

Не создавать отдельные commits/reports только ради доказательства проверки.
