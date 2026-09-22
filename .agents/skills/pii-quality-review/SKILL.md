---
name: pii-quality-review
description: Review PII detection, masking and unmasking changes against the hackathon categories, variants, false positives, overlaps, context and round-trip behavior.
---

# PII Quality Review

Используй после любого изменения detection/masking/unmasking.

Цель: доказать не только наличие detector-а, но и качество поведения.

## 1. Coverage matrix

Для каждого обязательного типа ПД проверить применимые категории:

- positive basic;
- formatting variants;
- case variants;
- contextual positive;
- contextual negative / false positive;
- multiple entities in one text;
- overlap/conflict with another detector;
- round-trip mask -> unmask.

Обязательные типы перечислены в `docs/REQUIREMENTS.md`.

## 2. Особое внимание

Проверять отдельно:

- ФИО vs публичное/неперсональное упоминание;
- адрес клиента vs адрес организации/отделения;
- даты рождения vs обычные даты;
- PAN vs другие длинные числа;
- PIN/CVV только в достаточном контексте;
- паспорт и код подразделения;
- сложные предложения с несколькими ПД.

## 3. False positives важны так же, как recall

Нельзя улучшать recall ценой маскирования каждого похожего фрагмента.

Для каждого нового правила должен существовать хотя бы один negative fixture, если тип допускает разумный false positive.

## 4. Fixtures

Использовать только синтетические данные.

Fixture должен явно содержать:

```text
input
expected masked spans/result
expected detected types
expected round-trip result
```

Если точный формат эталонной маски не подтверждён ТЗ/официальным примером, не выдавать выбранный формат за официальный.

## 5. Overlap

При пересечении detector spans проверить:

- детерминированный приоритет;
- отсутствие двойной замены;
- стабильные offsets;
- отсутствие повреждения соседнего текста.

## 6. Result

Верни:

- uncovered required categories;
- failing positive cases;
- false positives;
- overlap/round-trip defects;
- evidence that passed;
- verdict: `pass | pass with follow-up | block`.

P0/P1: утечка ПД или систематически неправильный round-trip.
P2: существенный quality gap.
P3: локальный edge case/maintainability risk.
