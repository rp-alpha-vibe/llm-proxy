---
name: requirements-analysis
description: Turn a new or materially changed behavior, API contract, state machine, retry/idempotency rule, security/privacy rule, or acceptance criterion into a short testable requirements brief before implementation.
---

# Requirements Analysis

Работай как системный аналитик, а не как implementer.

## Когда использовать

Используй skill, если задача вводит или меняет:

- наблюдаемое поведение;
- API/контракт;
- state/retry/idempotency/recovery;
- security/privacy semantics;
- acceptance criteria;
- значимое предположение из неоднозначного ТЗ.

Не используй для локального regression fix, который только восстанавливает уже принятое поведение.

## Процесс

1. Прочитай `AGENTS.md`, релевантные разделы `docs/REQUIREMENTS.md` и `docs/DECISIONS.md`.
2. Раздели:
   - confirmed facts;
   - owner decisions;
   - assumptions;
   - open questions.
3. Не выбирай техническое решение. Сначала опиши требуемое поведение.
4. Сформируй короткий brief.

## Формат

```md
# Requirements Brief

Goal:
Source:
Scope:
Non-goals:

System scenarios:
- trigger -> expected result
- retry/failure -> expected result

Invariants:
- ...

Acceptance:
- observable criterion
- negative criterion

Open questions / assumptions:
- ...
```

Обычный brief должен помещаться примерно в 30 строк.

## Правило скорости

Если источники однозначны, не запрашивай подтверждение пользователя ради церемонии.
Orchestrator может принять brief и продолжить.

Остановись только если есть материальная развилка, меняющая scope, security/privacy model, внешний контракт или критерии сдачи.

## Handoff

Передай brief в `backend-architecture` или напрямую implementer-у, если архитектурного выбора не требуется.
