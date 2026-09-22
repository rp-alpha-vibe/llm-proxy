---
name: pii-quality-review
description: Review detection, masking and unmasking changes for affected PII categories, false positives, overlaps and exact round-trip behavior. Use all categories for shared-engine changes or submission; reuse the common review.
---

# PII Quality Review

Проверь качество поведения в рамках общего review из `code-change-review`.

## Объём

- Локальное правило: затронутые категории и категории, с которыми возможны пересечения.
- Общий scanner, приоритеты spans, offsets или механизм замены/демаскирования: все обязательные категории.
- Сдача: вся матрица обязательных типов из `docs/REQUIREMENTS.md`, включая ещё не реализованные категории.
- Быстрый общий regression suite запускай целиком, если доступен. Не повторяй полный ручной разбор всех категорий при локальной правке без риска общей регрессии.
- Отсутствующая функция вне scope локальной задачи — ограничение готовности продукта. Регрессия, нарушенный acceptance или открытый P0/P1 остаются блокерами по `AGENTS.md`.

## Матрица для выбранных категорий

Проверь применимые случаи:

- positive basic, formatting/case variants;
- contextual positive и negative / false positive;
- multiple entities, overlap/conflict;
- точный round-trip mask -> unmask, включая пробелы, пунктуацию и регистр.

При изменении демаскирования/общего механизма замены и при submission дополнительно проверить §5.1 requirements: новый текст ответа LLM, перестановку и повторение масок, отсутствие части масок и безопасное поведение с неизвестными/неоднозначными масками. Результат должен сохранять текст ответа, а не возвращать исходный prompt.

Особое внимание: ФИО vs публичное упоминание, адрес клиента vs отделение банка, личные vs обычные даты, PAN vs другие длинные числа, PIN/CVV в контексте, паспорт/код подразделения и сложные предложения.

Для каждого нового правила добавь хотя бы один разумный negative fixture. Не повышай recall маскированием всех похожих фрагментов.

## Fixtures и измерение

Используй только синтетические данные. Fixture содержит:

```text
input
expected masked spans/result
expected detected types
expected round-trip result
```

Для сценария ответа LLM fixture дополнительно содержит mapping текущего контекста, synthetic LLM response и явно заданный expected unmasked response. Настоящий вызов LLM не требуется.

Для локального изменения проверяй его fixtures и регрессию. Для заявления о качестве продукта используй воспроизводимый корпус и правила измерения из `docs/REQUIREMENTS.md`, §6.1.
Проверяй результат независимо от реализации: expected spans/результаты должны быть заданы явно, а не вычислены тем же detector-ом.
Выбранную маску и локальную метрику не выдавай за официальный формат или scoring.

## Пересечения

Проверь детерминированный приоритет, отсутствие двойной замены, стабильные offsets и сохранность соседнего текста.

## Выход в общем review

Укажи только существенное:

- проверенный объём и команду/результат;
- failing positives, false positives, overlap/round-trip defects;
- непокрытые обязательные категории для режима submission;
- ограничения и verdict: `pass | pass with follow-up | block`.

P0/P1: утечка ПД, блокирующее нарушение контракта или систематически неправильный round-trip.
P2: существенный bounded quality gap; P3: локальная проблема.
Не понижай обязательный критерий задачи до P2 ради положительного verdict.
