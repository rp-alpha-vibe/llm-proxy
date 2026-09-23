# Architecture

Status: **accepted baseline**

Эта архитектура реализует требования из [REQUIREMENTS.md](REQUIREMENTS.md) минимальным набором компонентов.
Если benchmark или quality corpus докажет, что решение не выполняет обязательный критерий, архитектуру можно изменить через явное решение владельца. Не добавлять инфраструктуру «на будущее».

## 1. Цели архитектуры

Система должна одновременно обеспечить:

- строгий контракт `POST /process`;
- детектирование всех обязательных типов ПД с контролем false positives;
- mask -> exact unmask для автоматической проверки;
- демаскирование известных сущностей внутри изменённого ответа LLM;
- идемпотентность и безопасную конкуренцию по `payload_id`;
- per-system access/policy;
- отсутствие raw PII в логах/метриках;
- минимизированное и зашифрованное временное состояние;
- локальный baseline 1000 successful RPS с критериями §7.1 requirements;
- отдельную обработку payload до 100 000 токенов;
- расширение detectors и mask strategies без переделки core flow.

## 2. Принятый стек

| Область | Решение |
| --- | --- |
| Runtime | Python 3.12 |
| HTTP | FastAPI |
| Server | Uvicorn, несколько worker processes |
| Shared state | Redis |
| Redis client | async Redis client |
| State encryption | AES-GCM, key injected через environment/secret |
| Config | YAML + environment для секретов |
| Tests | pytest |
| Load test | k6 |
| Metrics | Prometheus-compatible metrics |
| Deployment | Docker; локально/deploy — service + Redis |

Причины выбора:

- Python ускоряет реализацию текстовых/русскоязычных detectors и оставляет возможность подключить лёгкий локальный NLP-инструмент;
- FastAPI не добавляет существенной логики поверх обязательного HTTP-контракта;
- несколько workers позволяют использовать CPU cores;
- Redis нужен как общий correlation state между workers;
- внешняя БД, очередь и отдельные сервисы для требований проекта не нужны.

## 3. Runtime topology

```text
                     client / AlfaSonar
                            |
                       POST /process
                            |
                  +---------v---------+
                  |    FastAPI app    |
                  | validation        |
                  | consumer resolve  |
                  | overload gate     |
                  +---------+---------+
                            |
                  +---------v---------+
                  |  ProcessService   |
                  | state machine     |
                  +----+----------+---+
                       |          |
                  new session   known session
                       |          |
                +------v------+   |
                | PII Engine  |   |
                +------+------|   |
                       |          |
                +------v------+   |
                | Mask Engine |   |
                +------+------|   |
                       |          |
                       +----+-----+
                            |
                    +-------v-------+
                    | Redis state   |
                    | AES-GCM + TTL |
                    +---------------+

health -> /healthz
```

Схема задаёт целевой поток. Сейчас работают `POST /process` и `GET /healthz`. Structured logs и `GET /metrics` появляются в E12. Detection идёт через `PiiEngine`: structured-детекторы и контекстные правила для дат, CVV, PIN, гражданства, места рождения, органа выдачи, адреса, ФИО и держателя карты. Эти правила требуют личного или документного якоря, поэтому публичное упоминание, обычная дата и адрес организации сами по себе не маскируются. `mask_strategy` выбирает renderer: `placeholder` пишет `[[PII:TYPE:n]]`, `competition` пишет `<TYPE_n>`. Форма `<TYPE_n>` — локальное обратимое допущение по иллюстрации §5.1, а не подтверждённый официальный формат. Локальный NLP/NER не подключён.

Один deploy содержит приложение и Redis. Kubernetes, Kafka/RabbitMQ, PostgreSQL, Celery и отдельные microservices не входят в baseline.

## 4. Публичные и служебные интерфейсы

### Обязательный публичный контракт

```http
POST /process
Content-Type: application/json
```

Body и response строго соответствуют `docs/REQUIREMENTS.md`, §3.
E4 не добавляет обязательный auth/system header: consumer выбирается deployment setting `LLM_PROXY_DEFAULT_CONSUMER_ID` из ограниченного YAML-списка. Это deployment-routing assumption, а не authentication; доступ endpoint должен ограничиваться сетевой границей deployment. До подтверждения способа допуска AlfaSonar это не считается решением внешнего auth-контракта.
Нельзя добавлять обязательные request fields/headers, которых нет в официальном контракте.

### Служебные endpoints

Допустимы:

- `GET /healthz` — liveness: процесс отвечает. Redis и возможность записать сессию не проверяются; их отказ виден на `POST /process` как 503.
- `GET /metrics` — технические метрики, маршрут добавляется в E12. Сейчас его нет.

Они не меняют обязательный контракт и не содержат raw PII.

## 5. Process state machine

`ProcessService` — единственное место, где определяется mask/retry/unmask flow.

```text
request(consumer, payload_id, payload)
              |
        load session
              |
       +------+------+
       |             |
    missing        exists
       |             |
      MASK      compare payload
       |        +----+------------------+
       |        |                       |
       |     original                 exact mask
       |        |                       |
       |   retry MASK               exact UNMASK
       |                                |
       |                         other payload
       |                                |
       |                         LLM-response UNMASK
       |
 detect -> mask -> store SET NX -> return stored mask
```

Правила:

1. Нет session: выполнить detection + masking, сформировать encrypted session и записать через Redis `SET NX`.
2. Если другой worker выиграл race по тому же ключу: прочитать его session и вернуть сохранённую mask.
3. Existing session + payload == original: это retry mask; вернуть ту же mask.
4. Existing session + payload == stored mask: exact demask; вернуть original.
5. Иной payload при разрешённом demask: восстановить только известные mapping текущей session внутри переданного текста.
6. Иной payload при запрещённом demask: отказ по policy.
7. Неизвестные/неоднозначные маски не угадывать и не искать в других sessions.

Detection и masking должны быть детерминированными для одинаковых `text + policy`.

## 6. Shared state

Redis используется только как краткоживущий correlation store.

Ключ:

```text
session:{consumer_id}:{sha256(payload_id)}
```

Value — одна AES-GCM encrypted structure:

```text
SessionRecord
- version
- original_text
- masked_text
- entities[]
    - type
    - original_start
    - original_end
    - rendered_mask
    - stable_entity_id
- policy_id
- mask_strategy
- created_at
```

Raw original/mapping не хранится в Redis открытым текстом.

### Lifecycle

Baseline:

- после mask: TTL порядка 15 минут, точное значение конфигурируемо;
- после успешного exact/product demask: TTL сокращается до короткого retry-window порядка 1–2 минут;
- Redis persistence выключена по умолчанию;
- restart Redis может потерять незавершённые sessions; сервис в таком случае fail-closed и не пытается угадывать исходные ПД.

TTL должен покрывать полный официальный прогон и retry. Конкретное значение проверяется нагрузкой/памятью.

### Encryption

- AES-GCM;
- уникальный nonce на record;
- key приходит из environment/secret и не хранится в git;
- associated data связывает ciphertext с record key/version;
- plaintext существует только в памяти процесса на время обработки.

Отдельный KMS не требуется ТЗ и не входит в baseline.

## 7. Consumer policy

`ConsumerResolver` создаёт `ConsumerContext`, а `PolicyRegistry` хранит конфигурацию.

Пример:

```yaml
systems:
  alfa_tester:
    enabled: true
    pii_types: all
    allow_demask: true
    mask_strategy: competition

  demo:
    enabled: true
    pii_types: [person, phone, email, card]
    allow_demask: true
    mask_strategy: placeholder
```

Policy одной системы не влияет на другую.
Redis state всегда scoped по `consumer_id + payload_id`.

### Открытая граница: доступ AlfaSonar

Официальный contract не содержит consumer/auth field.
Поэтому способ идентификации `alfa_tester` не фиксируется выдуманным header.

До submission необходимо подтвердить поддерживаемый организаторами механизм либо совместимое deployment-level решение.
`ConsumerResolver` изолирует эту неопределённость от core flow.

## 8. PII Engine

PII Engine — чистый in-process модуль без HTTP, Redis и сетевых вызовов.

Контракт:

```python
detect(text, enabled_types) -> list[Detection]
```

`Detection` содержит минимум:

- `type`;
- `start`;
- `end`;
- `confidence`;
- `evidence/context` при необходимости для review/debug без raw PII в runtime logs.

Final `Detection.type` должен однозначно отображаться на конкретную обязательную категорию `PiiType` из requirements. Общие parser/scanner-компоненты можно переиспользовать, но policy-visible типы не должны схлопывать семантически разные обязательные категории, например дату рождения и дату выдачи паспорта; обязательные компоненты адреса должны оставаться идентифицируемыми.

Pipeline:

```text
original text
    |
TextView / normalization
    |
CandidateDetectors
    |
ContextResolver
    |
OverlapResolver
    |
final spans in original coordinates
```

### Detector classes

Structured:

- email;
- phone;
- ИНН;
- PAN;
- паспорт;
- код подразделения;
- водительское удостоверение.

Использовать regex/scanner + structural validation; PAN — Luhn, ИНН — checksum там, где применимо.

Context-structured:

- даты;
- CVV;
- PIN.

Использовать pattern + contextual anchors.

Semantic/contextual:

- ФИО;
- место рождения;
- гражданство;
- орган выдачи;
- адрес;
- имя держателя карты.

Baseline — локальные rules/dictionaries/context scoring.
Сетевые LLM-вызовы запрещены в hot path.
Лёгкий локальный NLP/NER dependency добавляется только если quality corpus показывает конкретный gap, который rules не закрывают.

### Offsets

Все final spans относятся к original text.

Нормализация либо сохраняет длину, либо ведёт явный offset map. Текущая `TextView` оставляет регистр, кириллицу и пунктуацию как есть и убирает только невидимые символы; spans возвращаются в координаты исходного текста.
Замены применяются справа налево после завершения detection.
Detector не изменяет исходный text.

### Overlaps

OverlapResolver централизован.
Приоритет:

1. структурно валидированный специализированный detector;
2. context-confirmed detector;
3. generic pattern.

Двойная замена пересекающихся spans запрещена.

## 9. Masking Engine

Detection отделён от формата маски:

```text
Detection[] -> MaskStrategy -> MaskResult
```

Это обязательно, потому что официальный канонический формат всех масок не раскрыт, а ТЗ требует гибкость policies.

Baseline interfaces, которые выбирает masking epic:

- `CompetitionMaskStrategy` — формат, выбранный для официального scoring после проверки доступных примеров;
- `PlaceholderMaskStrategy` — уникальные stable placeholders для надёжного product LLM-response demask.

До официального образца `CompetitionMaskStrategy` пишет обратимый токен `<TYPE_n>`. Это локальное допущение по форме иллюстрации в `docs/REQUIREMENTS.md`, §5.1, и не является подтверждённым форматом scoring. `PlaceholderMaskStrategy` пишет `[[PII:TYPE:n]]`. Повтор одного и того же значения получает тот же токен; разные значения получают разные номера. `create_app` выбирает renderer по `mask_strategy` из policy.

`PlaceholderMaskStrategy` — внутренняя стратегия маскирования baseline, а не заявленная бонусная tokenization/detokenization feature из ТЗ. Полноценная настраиваемая токенизация остаётся bonus backlog.

Пример placeholder strategy:

```text
[[PII:PERSON:1]]
[[PII:EMAIL:2]]
```

Placeholder strategy не объявляется официальным форматом Альфы.
Competition strategy не должна зашиваться внутрь detectors.

## 10. Demasking

### Exact automated round-trip

Если incoming payload точно равен stored `masked_text`:

```text
return original_text
```

Это обеспечивает точный официальный round-trip, включая пробелы, регистр и пунктуацию.

### LLM response

Для иного текста при `allow_demask=true`:

- искать только mappings текущей session;
- восстанавливать только однозначно встреченные известные masks/placeholders;
- поддерживать повторение и перестановку;
- сохранять весь новый non-PII текст ответа;
- неизвестные или неоднозначные masks/placeholders оставлять в тексте без изменения; не угадывать и не превращать наличие одного неизвестного фрагмента в отказ всего ответа;
- никогда не использовать mapping другой session/consumer.

Placeholder strategy является надёжным вариантом для product LLM flow.
Для competition masks product demask выполняется только там, где mapping однозначен.

## 11. Overload и failure behavior

### Bounded concurrency

Приложение имеет ограничение одновременной работы hot path.

Если capacity исчерпана:

```http
429 Too Many Requests
Retry-After: <bounded value>
```

`ConcurrencyGate` ограничивает hot path внутри каждого Uvicorn process; агрегированный лимит нескольких workers подбирается нагрузочным профилем E13. При локальном baseline 1000 RPS 429 не допускается; overload profile проверяется отдельно.

### Redis unavailable

Fail closed:

- не выполнять mask/unmask без гарантированного correlation state;
- вернуть контролируемую 5xx/503;
- не возвращать исходные ПД и не fallback-ить в process-local unsafe state.

### Invalid input

Использовать bounded 4xx без stack trace/raw payload в response/logs.

### Timeouts

Redis/network operations имеют явные короткие timeouts.
Не создавать неограниченные внутренние очереди.

## 12. Observability

Один structured completion event на `POST /process` содержит только безопасные metadata. Отдельные stage-events не пишутся: этапы видны в `stages`.

```json
{
  "event": "process_completed",
  "request_id": "...",
  "consumer": "alfa_tester",
  "operation": "mask",
  "status": 200,
  "payload_chars": 862,
  "token_count": 120,
  "pii_types": ["email", "phone"],
  "pii_count": 3,
  "latency_ms": 8.4,
  "stages": {"detect_ms": 6.1, "redis_ms": 1.2, "total_ms": 8.4}
}
```

`pii_types` — канонические значения `PiiType`, без исходных значений. `request_id` — случайный id события, не `payload_id`. Запрещены raw payload и значения ПД.

`GET /metrics` отдаёт Prometheus exposition. Минимальные metrics:

- `requests_total`;
- `requests_inflight`;
- `request_duration_seconds`;
- `responses_total{status}`;
- `pii_detected_total{type}`;
- `processed_tokens_total`;
- `redis_duration_seconds`;
- `overload_rejections_total`.

Labels ограничены `status` и `type`. `payload_id` в labels не входит. RPS — это rate `requests_total`, latency — histogram `request_duration_seconds`.

TPS считается по `processed_tokens_total`. Tokenizer — whitespace: один token это один непустой фрагмент, разделённый Unicode-пробелом. Модель LLM в ТЗ не задана, поэтому это не tokenizer конкретной модели и не официальная метрика Альфы.

Несколько Uvicorn workers пишут в общий `PROMETHEUS_MULTIPROC_DIR`. `GET /metrics` собирает все живые процессы этого каталога, а не память одного worker. По умолчанию процесс один; число workers выбирает нагрузочный профиль.

## 13. Performance model

Hot path не содержит:

- network LLM calls;
- внешнего NER API;
- БД общего назначения;
- message broker.

Mask:

```text
Redis GET -> detect -> resolve overlaps -> mask -> AES-GCM -> Redis SET NX
```

Exact unmask:

```text
Redis GET -> AES-GCM decrypt -> compare -> return original
```

Следствия:

- detection выполняется только на mask path;
- unmask — дешёвый state lookup;
- workers масштабируют CPU-bound detection по cores;
- Redis обеспечивает общий state между workers.

Локальный baseline, прошедший §7.1 на этой машине, использовал 8 worker processes и `max_concurrency` 1000 на process. Redis pool оставлен стандартным: узким местом первого прогона был лимит VU у генератора, не пул. Другое окружение нужно мерить заново.

Алгоритмы detectors должны избегать catastrophic backtracking, квадратичных проходов и неконтролируемого копирования больших строк.

## 14. Deployment

Минимальный deployment:

```text
Docker host / VM
|
+-- llm-proxy
|   +-- worker 1
|   +-- worker 2
|   +-- ...
|
+-- redis
    +-- private network
    +-- persistence OFF
```

Если площадка даёт ingress/TLS, использовать его.
Иначе официальный tester допускает HTTP.

Redis не публикуется наружу.

## 15. Структура кода

Текущее дерево. `scripts/package.py` не создаётся, пока у него нет реализации.

```text
src/llm_proxy/
├── main.py
├── api/
│   └── process.py
├── application/
│   ├── process_service.py
│   ├── overload.py
│   └── stubs.py
├── detection/
│   ├── models.py
│   ├── text_view.py
│   ├── registry.py
│   ├── context.py
│   ├── overlap.py
│   ├── engine.py
│   ├── structured/
│       ├── __init__.py
│       ├── common.py
│       ├── email.py
│       ├── phone.py
│       ├── inn.py
│       ├── pan.py
│       ├── passport.py
│       ├── division_code.py
│       └── driver_license.py
│   └── contextual/
│       ├── __init__.py
│       ├── common.py
│       ├── dates.py
│       ├── secrets.py
│       ├── person.py
│       ├── records.py
│       └── address.py
├── observability/
│   ├── logging.py
│   ├── metrics.py
│   ├── middleware.py
│   ├── timing.py
│   └── tokens.py
├── masking/
│   ├── base.py
│   ├── render.py
│   ├── placeholder.py
│   ├── competition.py
│   └── routing.py
├── quality/
│   ├── gate.py
│   ├── schema.py
│   ├── runner.py
│   └── corpus.yaml
├── state/
│   ├── models.py
│   ├── redis_store.py
│   └── crypto.py
└── policies/
    ├── models.py
    ├── loader.py
    └── consumer_resolver.py

config/
└── systems.example.yaml

tests/
└── test_*.py

scripts/
└── verify.py
```

Не добавлять слои/директории заранее, если в них ещё нет реальной обязанности.

## 16. Verification mapping

Колонка ниже — где доказательство должно появиться, а не список уже полученных результатов. Для E0–E13 есть контракт `/process`, retry, exact и product demask, изоляция политик, 429, шифрование сессии, quality corpus, security tests, structured completion log, Prometheus metrics и локальный k6 baseline. ZIP ещё не собран.

| Requirement | Architecture | Запланированное доказательство |
| --- | --- | --- |
| `POST /process` | API layer | integration contract test |
| retry/idempotency | ProcessService state machine | retry + concurrent tests |
| exact demask | encrypted SessionRecord | exact string assertion |
| LLM response demask | per-session mapping | synthetic response fixtures |
| all PII categories | detector plugins | quality corpus |
| false positives | ContextResolver | negative fixtures |
| extensibility | Detector + MaskStrategy boundaries | extension/config tests |
| per-system policies | ConsumerResolver + PolicyRegistry | isolation/config tests |
| 1000 RPS | multiprocess + Redis + bounded hot path | k6 300s baseline |
| latency <= 1s | deterministic local pipeline | p95 load gate |
| 100k tokens | linear-ish local processing | separate large-payload profile |
| 429 | overload gate | overload test |
| safe logs | structured metadata only | log capture/security tests |
| Latency/RPS/TPS | metrics module | metrics integration test |
| encryption/minimization | AES-GCM + Redis TTL | state/security tests |
| clean ZIP | package script | archive inspection |

## 17. Non-goals

Не входят в baseline без нового требования/evidence:

- PostgreSQL;
- Kafka/RabbitMQ;
- Celery/work queues;
- Kubernetes;
- service mesh;
- vector DB/RAG;
- внешний LLM/NER API;
- отдельный auth service;
- admin UI;
- distributed tracing;
- permanent audit storage;
- ML/NER model «на всякий случай».

## 18. Известные открытые вопросы

Архитектура намеренно оставляет адаптируемыми только неизвестные из ТЗ:

1. точный competition mask format;
2. официальный span-based scoring;
3. способ идентификации/допуска AlfaSonar; baseline использует только `LLM_PROXY_DEFAULT_CONSUMER_ID` и не выдумывает обязательный request header.
4. реальный distribution payload sizes;
5. внутренние банковские ИБ/compliance criteria.

Эти вопросы не должны блокировать реализацию независимых компонентов.
