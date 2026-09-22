---
name: code-change-review
description: Read-only review of nontrivial implementation changes for correctness, failure behavior, security/privacy, observability, extensibility, performance risk, and misleading verification evidence.
---

# Code Change Review

Работай как скептический reviewer. Не исправляй код в этом проходе.

## Вход

Используй актуальный контекст; прочитай недостающее или изменившееся:

- `AGENTS.md`;
- релевантные разделы `docs/REQUIREMENTS.md`;
- общий task brief и его requirements/architecture sections, если они были;
- полный diff;
- затронутый код и тесты.

Объём проверки выбирай по `AGENTS.md`, §4.1. Подключай применимые domain skills как разделы одного review, без повторного чтения того же diff и отдельных отчётов.

## Pass 1 — Contract and behavior

Проверь применимое:

- реализован ли принятый контракт и acceptance criteria;
- нет ли случайного расширения scope;
- корректны ли state transitions;
- корректны ли retry/idempotency/concurrent duplicates;
- для `/process`: retry исходного payload не превращается в demask, а ранее возвращённая mask корректно восстанавливает original;
- non-PII текст, порядок сущностей и соседние символы не повреждаются;
- конфигурация одной consumer-system не меняет политику другой;
- новый consumer с существующими правилами не требует правки core-кода;
- новый detector подключается через принятую точку расширения без переписывания state/routing;
- тесты не подменяют реальное требование удобной реализационной проверкой.

## Pass 2 — Failure behavior

Проверь минимально применимую матрицу:

| Scenario | Required question |
| --- | --- |
| first request | correct result/state? |
| retry same original | same mask/result without state corruption? |
| mask -> unmask | exact original restored? |
| concurrent duplicate | race/data corruption? |
| malformed input | bounded clear failure? |
| dependency unavailable | safe degradation? |
| restart | required state recoverable under chosen architecture? |
| overload | bounded latency/queue/memory and correct 429 behavior? |

Для 429 при scope runtime/load также проверить `Retry-After` и семантику из `docs/REQUIREMENTS.md` §3.

## Security/privacy

Проверь применимое:

- raw PII отсутствует в logs, traces, metrics labels, exception messages, committed fixtures и debug output;
- логи содержат только безопасные metadata и типы обнаруженных ПД;
- секреты/ключи отсутствуют в code/config/fixtures;
- оригинальные payloads не хранятся дольше и шире необходимого;
- lifecycle/TTL соответствует принятой модели хранения;
- если sensitive state находится во внешнем или persistent storage, есть доказуемое шифрование и безопасное управление ключами;
- чувствительные данные не копируются в unnecessary caches/artifacts;
- код и документация не заявляют compliance Банка/ЦБ/закона как доказанный факт без соответствующего evidence.

## Observability

Если затронут runtime/observability, проверить:

- логируются основные этапы обработки;
- по запросу логируются detected PII types без исходных значений;
- доступны метрики Latency, RPS и TPS;
- metric labels не содержат raw payload/PII и не создают неконтролируемую cardinality.

## Verification quality

Зелёный тест считается доказательством только если он наблюдает нужное поведение.

Для важного negative path должны быть:

1. stimulus;
2. observable expected outcome.

PII-изменения дополнить `pii-quality-review`.
Hot-path/runtime/performance изменения дополнить `performance-review`.
Не создавать отдельные отчёты: результаты включить в этот review.

## Findings

Классифицируй:

- P0: активный severe security/data-loss риск;
- P1: correctness/security/reliability defect, нарушающий обязательное требование или блокирующий сдачу;
- P2: существенный bounded weakness;
- P3: локальная maintainability/clarity проблема.

Верни сначала findings, затем подтверждённые проверки, затем verdict:

`pass | pass with follow-up | block`.

Не перечисляй неприменимые пункты ради заполнения отчёта.

Стандартный change может review-ить тот же агент отдельным проходом.
Открытый P0/P1 или неподтверждённый обязательный критерий означает `block`.
После исправлений перепроверь изменённое поведение и diff; полный review повторяй только при существенном расширении риска.
