---
name: grill-me
description: Stress-test a material plan or architecture decision through a short Socratic interview. Use only when explicitly invoked with $grill-me.
---

# Grill Me

Skill работает только по явному вызову `$grill-me`.

Цель: найти решения, которые ещё не определены и реально могут изменить scope, architecture, security, data handling, performance или acceptance.

## Правила

1. Сначала изучи доступные факты. Не спрашивай пользователя то, что можно узнать из репозитория/ТЗ.
2. Не переоткрывай уже принятые решения без нового свидетельства.
3. Задавай за раунд максимум 3–5 вопросов.
4. Каждый вопрос должен иметь реальное последствие для реализации.
5. Для каждого вопроса дай одну краткую рекомендацию.
6. Не начинай реализацию в рамках interview.

Формат:

```text
Q1 — короткое название
Варианты и реальные последствия.
Recommendation: ...
```

Остановись, когда материальных развилок больше нет.
