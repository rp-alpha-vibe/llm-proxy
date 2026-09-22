---
name: requirements-analysis
description: Turn a new or materially changed behavior, API contract, state machine, retry/idempotency rule, security/privacy rule, or acceptance criterion into a short testable requirements brief before implementation.
---

# Requirements Analysis

Сначала опиши требуемое поведение, затем переходи к реализации в рамках того же рабочего цикла.

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

1. Используй актуальный контекст из `AGENTS.md`, релевантных разделов `docs/REQUIREMENTS.md` и `docs/DECISIONS.md`; перечитай только недостающее или изменившееся.
2. Раздели:
   - confirmed facts;
   - owner decisions;
   - assumptions;
   - open questions.
3. Не выбирай техническое решение. Сначала опиши требуемое поведение.
4. Дополни общий task brief требованиями; не создавай второй документ с теми же Goal/Scope/Acceptance.

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

Формат — подсказка для нужных разделов, не обязательная анкета. Обычный раздел требований должен помещаться примерно в 30 строк; однозначной задаче достаточно нескольких пунктов.

## Правило скорости

Если источники однозначны, не запрашивай подтверждение пользователя ради церемонии.
Тот же агент может принять brief и продолжить; отдельный orchestrator или handoff не обязателен.

Остановись только если есть материальная развилка, меняющая scope, security/privacy model, внешний контракт или критерии сдачи.

## Handoff

При архитектурном выборе дополни тот же brief через `backend-architecture`; иначе переходи к реализации. Не переоткрывай принятые решения без нового факта.
