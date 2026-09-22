---
name: ux-ui-review
description: Lightweight read-only review of the hackathon demo UI for clarity, task flow, trust, responsive behavior and safe handling of sensitive data. Use only when the task includes user-facing UI.
---

# UX/UI Review

Используй только для реального demo UI.

## Проверить

- пользователь сразу понимает, что является исходным текстом, что обнаружено и что замаскировано;
- визуально различимы original / masked / unmasked states;
- найденные типы ПД и выбранная policy объяснимы;
- ошибки, loading и retry не создают ложного ощущения успеха;
- реальные ПД не попадают в screenshots/demo artifacts;
- интерфейс работает на обычном desktop viewport;
- нет очевидного overflow/truncation на разумных длинных текстах;
- основной сценарий можно пройти без объяснений разработчика.

## Review

Проверяй runnable UI, если он доступен. Screenshot доказывает только визуальное состояние, но не интерактивность.

Верни:

- P1/P2/P3 findings;
- что было реально проверено;
- positively confirmed behavior;
- verdict: `pass | pass with follow-up | block`.

Не превращай review в редизайн. Исправляй только проблемы, мешающие демо или доверию.
