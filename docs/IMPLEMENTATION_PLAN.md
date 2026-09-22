# Implementation Plan

Status: **accepted execution plan**

Этот документ превращает [REQUIREMENTS.md](REQUIREMENTS.md) и [ARCHITECTURE.md](ARCHITECTURE.md) в последовательность реализации.
Он не меняет требования и архитектуру. `AGENTS.md` задаёт процесс работы; содержательно план подчиняется `REQUIREMENTS.md`, `DECISIONS.md` и `ARCHITECTURE.md`.

Цель плана: получить submission-ready baseline как можно быстрее, сохраняя проверяемость после каждого крупного шага. Бонусные функции не входят в baseline.

## Оперативный план до 23 сентября 2026 года, 23:59 МСК

Этот порядок заменяет последовательное выполнение оставшихся эпиков; их обязательные результаты и критерии не отменяются. Цель — получить проверенный кандидат к 17:00–18:00 23 сентября и оставить время на внешнюю проверку и исправления. Verdict `block` при непройденном обязательном критерии не запрещает отправить честно описанный результат до дедлайна (D-006).

| Срок, МСК | Наблюдаемый результат |
| --- | --- |
| До 00:30 | E4: добавить отсутствующую dev-зависимость для async-тестов, выполнить clean-environment verify и один реальный HTTP → Redis mask/retry/unmask smoke; короткий review и checkpoint. Доступность публичного URL назначить отдельному исполнителю сразу. |
| До 02:30 | Первый deployment и ZIP с кодом готовы для ранней проверки на сайте; выяснены поддерживаемый доступ AlfaSonar и доступные примеры масок. Отсутствие сервера/URL — немедленный blocker для deployment-потока. |
| До 08:00 | Первый общий вариант со всеми обязательными категориями: детекторы, контекст, разрешение пересечений, competition mask и вручную размеченный компактный корпус. |
| До 12:00 | Интеграционная проверка всех типов, negatives, перекрытий, exact round-trip и нового ответа LLM; исправлены крупнейшие ошибки качества. |
| До 15:00 | Реальный Redis, security/log leak checks, Latency/RPS/TPS, 300-секундная нагрузка, отдельный профиль до 100 000 токенов и overload/recovery; исправления по измеренным bottlenecks. |
| До 18:00 | Окончательный ZIP пересобран из проверенного source, из него выполнен clean smoke; deployment совпадает с отправляемой версией; готовы презентация, VCS и URL; внешняя проверка и финальная форма отправки выполняются отдельно. |
| До 23:59 | Резерв на внешние результаты, прицельные исправления и повтор только затронутых проверок; новых бонусных функций нет. |

Четыре независимых потока: (1) общий registry/overlap/masking и интеграция, (2) structured detectors, (3) contextual/semantic detectors, (4) deployment/ZIP/observability/материалы сдачи. `ProcessService`, Redis session semantics и OverlapResolver имеют одного владельца изменения. Корпус качества создаётся параллельно детекторам; E9 повторно не реализует уже принятое поведение E3. Презентация и иные медиа не включаются в ZIP с кодом.

Экономия scope: искать в исходном тексте или представлении с сохранением длины, поэтому общий offset-map engine не нужен без доказанного изменения длины; выбирать минимальные правила и renderer через принятые интерфейсы; локальную NER-зависимость добавлять только после измеренного quality gap; не строить UI, dashboards, дополнительные стратегии и бонусы. Сохранять все обязательные категории, per-system policy, шифрование и изоляцию state, логи/метрики и измерения качества/нагрузки.

## 1. Milestones

| Milestone | Состав | Результат |
| --- | --- | --- |
| M1 — Core works | E0–E4 | Запускаемый `/process`, Redis state, encryption, retry/idempotency, exact round-trip |
| M2 — Functional baseline | E5–E10 | Все обязательные PII категории, masking, product demask, воспроизводимое quality measurement |
| M3 — Engineering baseline | E11–E13 | Security/observability/performance подтверждены |
| M4 — Submission ready | E14–E16 | Совместимость tester, deployment/package и финальная приёмка |

Основной критический путь после D-006:

```text
E4 -> минимальный E5 -> E6/E7/E8 -> E10 -> E13(final) -> E16
        |                  |            |
        +-> E15(ранний ZIP/deploy)      +-> E11(final)
        +-> E12(logs/metrics) ----------> E13(final)
        +-> E14(contract/auth) ---------> E14(deployed checks) -> E16
```

E6/E7/E8 и подготовка корпуса E10 идут параллельно после минимального контракта E5; финальное измерение E10 ждёт их интеграции. E12, E14 contract/auth и E15 deployment/packaging начинаются сразу на runnable E4. Поздние зависимости отдельных эпиков означают только их финальную приёмку, не начало работы.

---

## Epic E0 — Project skeleton и единая проверка

**Goal:** reproducible project из clean checkout.

### Tasks

- [x] E0.1 Создать Python 3.12 project и `pyproject.toml`.
- [x] E0.2 Создать `src/llm_proxy` и FastAPI application factory.
- [x] E0.3 Реализовать `GET /healthz`.
- [x] E0.4 Добавить Redis в local Docker Compose.
- [x] E0.5 Добавить typed settings: Redis URL, encryption key, TTL, concurrency, config path.
- [x] E0.6 Добавить `config/systems.example.yaml` без реальных секретов.
- [x] E0.7 Настроить formatter/lint/typecheck/pytest.
- [x] E0.8 Создать одну быструю команду `verify` для локальной проверки.
- [x] E0.9 CI должен запускать ту же `verify` команду.
- [x] E0.10 Настроить `.gitignore` для env/cache/coverage/build/runtime.
- [x] E0.11 Добавить минимальный Dockerfile.
- [x] E0.12 Обновить README только реально работающими install/run/verify командами.

### Acceptance

```text
clean checkout
-> install
-> start Redis
-> start app
-> GET /healthz = 200
-> verify = green
```

**Dependencies:** none.

---

## Epic E1 — Core domain contracts

**Goal:** зафиксировать маленькое ядро до появления implementation coupling.

### Tasks

- [ ] E1.1 Определить `PiiType` для всех обязательных категорий.
- [ ] E1.2 Определить `Detection(type,start,end,confidence,detector_id,...)`.
- [ ] E1.3 Определить `MaskResult(text, entities)`.
- [ ] E1.4 Определить `SessionRecord`.
- [ ] E1.5 Определить `ConsumerPolicy`.
- [ ] E1.6 Определить минимальные interfaces/protocols: `Detector`, `MaskStrategy`, `StateStore`, `ConsumerResolver`, `PolicyRegistry`.
- [ ] E1.7 Unit tests для validation/serialization и completeness обязательных PII типов.

### Acceptance

Domain-модели не зависят от FastAPI/Redis. Все обязательные PII типы представлены явно.

**Dependencies:** E0.

---

## Epic E2 — Encrypted Redis correlation state

**Goal:** shared state для multi-worker mask/unmask без plaintext PII.

### Tasks

- [x] E2.1 Реализовать AES-GCM encrypt/decrypt `SessionRecord`.
- [x] E2.2 Encryption key получать только из environment/secret.
- [x] E2.3 Уникальный nonce на record; использовать authenticated data для key/version binding.
- [x] E2.4 Реализовать `RedisStateStore.get/create_if_absent/update_ttl/delete`.
- [x] E2.5 Redis key: `session:{consumer_id}:{sha256(payload_id)}`.
- [x] E2.6 Atomic create через `SET NX`.
- [x] E2.7 Configurable normal TTL и short post-demask retry TTL.
- [x] E2.8 Redis persistence выключить в baseline.
- [x] E2.9 Redis не публиковать наружу.
- [x] E2.10 Redis unavailable => fail closed, без process-local fallback.
- [x] E2.11 Tests: ciphertext не содержит plaintext, concurrent create, TTL expiry, invalid key/tag, Redis failure.

### Acceptance

Несколько worker processes используют один согласованный encrypted state; raw PII отсутствует в Redis keys и plaintext storage.

**Dependencies:** E1.

---

## Epic E3 — ProcessService state machine

**Goal:** корректная семантика new/retry/exact-unmask/product-unmask.

### Tasks

- [x] E3.1 New `payload_id`: detect -> mask -> encrypted session -> `SET NX`.
- [x] E3.2 Если `SET NX` проигран race, перечитать winning session и классифицировать запрос снова.
- [x] E3.3 Existing session + original payload => вернуть ту же mask.
- [x] E3.4 Existing session + exact stored mask => вернуть exact original.
- [x] E3.5 Existing session + другой payload + `allow_demask=true` => mapping-based product demask.
- [x] E3.6 `allow_demask=false` реально запрещает demask.
- [x] E3.7 Unknown/ambiguous masks/placeholders не угадывать и не искать в других sessions/consumers; в product demask оставлять их в тексте без изменения.
- [x] E3.8 Consumer/session isolation tests.
- [x] E3.9 Concurrent duplicate tests.
- [x] E3.10 Redis loss/restart => controlled safe failure.

Для E3 detector/mask strategy может быть простым stub, чтобы сначала доказать state semantics.

### Acceptance

```text
new -> mask
same original -> same mask
exact mask -> exact original
modified known-mask text -> product demask
concurrent duplicate -> consistent state
foreign session/consumer -> no disclosure
```

**Dependencies:** E2.

---

## Epic E4 — Public /process + consumer policy

**Goal:** первый end-to-end runnable vertical slice.

### Tasks

- [ ] E4.1 Реализовать строгий request/response contract `POST /process`.
- [ ] E4.2 Validation: invalid JSON, missing/wrong fields, bounded errors без raw payload/stack trace.
- [ ] E4.3 Реализовать YAML `PolicyRegistry`.
- [ ] E4.4 Реализовать `ConsumerResolver` как отдельную boundary.
- [ ] E4.5 Не добавлять обязательный auth/system header в AlfaSonar contract без официального подтверждения.
- [ ] E4.6 Disabled consumer => controlled rejection.
- [ ] E4.7 Проверить policy isolation между systems.
- [ ] E4.8 Добавить bounded concurrency gate skeleton и 429 + `Retry-After`.
- [ ] E4.9 Integration tests полного HTTP mask -> unmask flow.

### Acceptance

Работает полный путь:

```text
HTTP -> policy -> ProcessService -> Redis -> result
```

Перед checkpoint M1 проверить этот путь на реальном Redis, mask → retry original → exact unmask, и воспроизводимость async-тестов в чистом dev-окружении. Будущие PII-детекторы, логирование и полная нагрузка не входят в acceptance E4.

**Milestone:** M1.

**Dependencies:** E3.

---

## Epic E5 — PII Engine framework

**Goal:** extensible local detection pipeline без зависимости от HTTP/state.

### Tasks

- [ ] E5.1 Реализовать `TextView`/normalization.
- [ ] E5.2 Все final spans должны ссылаться на original coordinates.
- [ ] E5.3 Если normalization меняет длину, реализовать offset map.
- [ ] E5.4 Реализовать detector registry по `enabled PiiType`.
- [ ] E5.5 Реализовать `ContextResolver`.
- [ ] E5.6 Реализовать централизованный `OverlapResolver`.
- [ ] E5.7 Priority: validated structured > context-confirmed > generic.
- [ ] E5.8 Применять replacements справа налево.
- [ ] E5.9 Tests: overlaps, adjacent spans, Unicode/кириллица, punctuation, case.

### Acceptance

Новый detector добавляется без изменений `ProcessService`, API и Redis.

**Dependencies:** E1, E4.

---

## Epic E6 — Structured PII detectors

**Goal:** быстро закрыть детерминированные категории с низким false-positive rate.

### Tasks

- [ ] E6.1 Email: valid/invalid, punctuation, case.
- [ ] E6.2 Phone: +7/8, spaces, dashes, parentheses, negatives.
- [ ] E6.3 INN: 10/12 digits + checksum.
- [ ] E6.4 PAN: accepted layouts + Luhn + negative long numbers.
- [ ] E6.5 Passport series/number: compact/spaced/context variants.
- [ ] E6.6 Division code: format + context.
- [ ] E6.7 Russian driver license formats.
- [ ] E6.8 Для каждого detector добавить positive/format/case/negative/multiple/punctuation fixtures.
- [ ] E6.9 Microbenchmark типичного и pathological input для новых regex/scanners.

### Acceptance

Structured suite green; нет известных систематических false positives; regex не демонстрируют pathological slowdown.

**Dependencies:** E5.

---

## Epic E7 — Contextual и semantic PII detectors

**Goal:** закрыть самые рискованные по качеству категории.

### Tasks

- [ ] E7.1 Общий date parser: numeric variants и textual Russian dates.
- [ ] E7.2 Birth date detector через context anchors.
- [ ] E7.3 Passport issue date detector через отдельный context.
- [ ] E7.4 CVV/CVC detector, не маскирующий произвольные 3-digit numbers.
- [ ] E7.5 PIN detector с достаточным card context.
- [ ] E7.6 Citizenship detector.
- [ ] E7.7 Birth place detector.
- [ ] E7.8 Passport issuer detector.
- [ ] E7.9 Address detector и components; negative organization/bank addresses.
- [ ] E7.10 Person/FIO detector с contextual positives и public-person negatives.
- [ ] E7.11 Cardholder detector поверх person-like span + card context.
- [ ] E7.12 После измерения quality рассматривать lightweight local NLP/NER только для доказанного gap.
- [ ] E7.13 Любой NLP/NER addition обязан пройти quality + performance comparison с baseline.

### Acceptance

Все обязательные semantic/contextual категории имеют positive и negative coverage. Публичный человек, обычная дата и адрес организации не маскируются без достаточного персонального контекста.

**Dependencies:** E5.

---

## Epic E8 — Masking strategies

**Goal:** отделить quality detection от неизвестного официального mask format.

### Tasks

- [ ] E8.1 Реализовать `MaskStrategy` interface.
- [ ] E8.2 Реализовать `CompetitionMaskStrategy`.
- [ ] E8.3 Подтверждённые примеры ТЗ использовать как regression fixtures.
- [ ] E8.4 Не вшивать competition rendering в detectors.
- [ ] E8.5 Реализовать `PlaceholderMaskStrategy` со stable unique placeholders для product flow; это внутренняя baseline mask strategy, а не bonus tokenization/detokenization.
- [ ] E8.6 Повтор одной сущности в session должен иметь стабильную identity.
- [ ] E8.7 Гарантировать invariant: текст вне PII spans не изменяется.
- [ ] E8.8 Проверить mask collision/ambiguity safety.

### Acceptance

Один и тот же `Detection[]` можно отрендерить разными strategies без изменения detection pipeline.

**Dependencies:** E5; может идти параллельно с E6/E7.

---

## Epic E9 — Регрессия product demasking для новых масок

**Goal:** проверить уже реализованный в E3 mapping-based flow после интеграции новых масок; исправлять только доказанный gap.

### Tasks

- [ ] E9.1 Проверить E3 flow на competition masks и placeholders: reorder, repeat, missing и unknown/ambiguous tokens.
- [ ] E9.2 Проверить изоляцию session/consumer и сохранение нового текста, пробелов и пунктуации на синтетическом ответе LLM.
- [ ] E9.3 Исправить только выявленный регрессией gap, не вводя второй state machine.

### Acceptance

Synthetic LLM response с reordered/repeated known masks даёт ожидаемый unmasked response и сохраняет новый текст.

**Dependencies:** E3, E8.

---

## Epic E10 — Quality corpus и измерение

**Goal:** превратить PII quality в воспроизводимую метрику, а не впечатление.

### Tasks

- [ ] E10.1 Определить fixture schema: input, expected spans/types, expected mask при наличии канона, expected round-trip, tags.
- [ ] E10.2 Для каждого обязательного типа покрыть basic positive.
- [ ] E10.3 Добавить formatting/case variants.
- [ ] E10.4 Добавить contextual positives и negatives.
- [ ] E10.5 Добавить multiple PII и overlap/conflict cases.
- [ ] E10.6 Добавить сложные identity/card/address предложения.
- [ ] E10.7 Negative corpus: public persons, bank addresses, ordinary dates, arbitrary IDs/long numbers/3-4 digit numbers.
- [ ] E10.8 Реализовать quality runner: precision/recall/F1 per type, false positives, exact round-trip.
- [ ] E10.9 Expected данные задаются вручную, не detector-ом.
- [ ] E10.10 Зафиксировать corpus size, baseline и локальные thresholds до tuning.
- [ ] E10.11 Gap fixing: weakest category -> inspect errors -> smallest fix -> rerun.
- [ ] E10.12 Не выдавать локальный F1 за официальный span-based scoring.

### Acceptance

Одна команда воспроизводимо измеряет все обязательные категории; нет непокрытых обязательных типов.

**Milestone:** M2.

**Dependencies:** E5 для подготовки E10.1–E10.7; E6, E7, E8, E9 для финального quality runner/gate E10.8–E10.12.

---

## Epic E11 — Security hardening

**Goal:** доказать отсутствие очевидных PII/secret leaks и корректную isolation model.

### Tasks

- [ ] E11.1 Log leak tests для name/phone/email/PAN/passport synthetic values.
- [ ] E11.2 Metric labels не содержат payload/PII.
- [ ] E11.3 Redis inspection подтверждает отсутствие plaintext PII.
- [ ] E11.4 Secrets/key только через environment/secret; real `.env` не commit.
- [ ] E11.5 Cross-consumer demask isolation.
- [ ] E11.6 Cross-session demask isolation.
- [ ] E11.7 Реальный TTL cleanup.
- [ ] E11.8 Ошибки/exception responses не содержат PII/stack traces.
- [ ] E11.9 Использовать HTTPS/TLS termination, если deployment platform это предоставляет; не вводить собственный TLS как обязательный blocker, поскольку официальный tester допускает HTTP.

### Acceptance

Security tests не находят raw PII/secrets в logs, metrics, repository или Redis plaintext; sessions изолированы.

**Dependencies:** E2–E10.

---

## Epic E12 — Logging и metrics

**Goal:** выполнить observability requirements без создания собственного bottleneck.

### Tasks

- [ ] E12.1 Baseline использует один structured completion event на operation, если этого достаточно для наблюдаемости без лишнего log volume; отдельные stage-events не обязательны.
- [ ] E12.2 Completion log должен делать наблюдаемыми основные processing stages через безопасные stage/status/timing metadata и содержать operation/status/latency/pii types/count без raw PII.
- [ ] E12.3 Реализовать metrics:
  - requests_total;
  - responses_total;
  - requests_inflight;
  - request_duration_seconds;
  - pii_detected_total{type};
  - processed_tokens_total;
  - redis_duration_seconds;
  - overload_rejections_total.
- [ ] E12.4 Зафиксировать tokenizer для TPS и документировать его.
- [ ] E12.5 Настроить Prometheus multiprocess aggregation для нескольких Uvicorn workers.
- [ ] E12.6 Проверить, что worker aggregation отражает весь service, а не один process.
- [ ] E12.7 Metrics/logging tests без sensitive labels/high-cardinality payload IDs.

### Acceptance

Latency/RPS/TPS и detected PII types наблюдаемы; несколько workers агрегируются корректно; raw PII отсутствует.

**Dependencies:** E4; удобно завершить после E10.

---

## Epic E13 — Performance и overload

**Goal:** доказать локальный performance baseline и найти реальные bottlenecks.

### Tasks

- [ ] E13.1 Microbench всех hot detectors: typical/long/pathological.
- [ ] E13.2 Проверить payload до 100 000 токенов отдельным profile.
- [ ] E13.3 Искать catastrophic regex, quadratic passes, repeated full scans, excessive copies/allocations.
- [ ] E13.4 Реализовать k6 stateful mask -> unmask scenario.
- [ ] E13.5 300s baseline после warm-up на 1000 target RPS.
- [ ] E13.6 Измерять offered RPS, unique successful RPS, p50/p95/p99/max, attempts, errors, 429, CPU, memory, Redis latency.
- [ ] E13.7 Baseline должен пройти thresholds из `REQUIREMENTS.md §7.1`.
- [ ] E13.8 Экспериментально подобрать worker count, Redis pool, concurrency limit.
- [ ] E13.9 Отдельный overload profile: 429 + Retry-After, bounded memory, recovery после снижения нагрузки.
- [ ] E13.10 Оптимизировать только измеренный bottleneck, затем повторить relevant tests.

### Acceptance

Baseline проходит требования проекта; large payload profile не демонстрирует неконтролируемую деградацию; overload восстанавливается.

**Milestone:** M3.

**Dependencies:** E10–E12.

---

## Epic E14 — AlfaSonar compatibility

**Goal:** исключить несовместимость с официальным tester.

### Tasks

- [ ] E14.1 Проверить contract format через официальный self-check/example.
- [ ] E14.2 Получить официальный ответ о consumer identification/auth, если организаторы его предоставляют.
- [ ] E14.3 Адаптировать только `ConsumerResolver`, не core flow.
- [ ] E14.4 Убедиться, что tester не обязан отправлять непредусмотренные request fields/headers.
- [ ] E14.5 Проверить полный deployed mask -> unmask pair официальным body format.
- [ ] E14.6 Проверить retry и 429 semantics на deployed endpoint.

### Acceptance

Официальный request format проходит полный flow; access policy не ломает tester contract.

**Dependencies:** E4 для E14.1–E14.4 и раннего deployed smoke E14.5; финальный E14.5–E14.6 повторяется после integration/performance changes. Не ждать E13 для начала проверки официального доступа.

---

## Epic E15 — Deployment и packaging

**Goal:** воспроизводимо развернуть именно тот source package, который сдаётся.

### Tasks

- [ ] E15.1 Production Docker image.
- [ ] E15.2 App + private Redis topology.
- [ ] E15.3 Использовать внешний HTTPS/platform TLS termination, если он доступен; HTTP остаётся допустимым для официального tester согласно контракту.
- [ ] E15.4 Runtime secrets/config только через environment/secret.
- [ ] E15.5 Создать `scripts/package.py`.
- [ ] E15.6 ZIP строится по allowlist и содержит только исходники решения и минимальные файлы, необходимые для его сборки/запуска/конфигурации; внутренние project docs и agent instructions не включаются без явного требования организаторов.
- [ ] E15.7 Автоматически исключить `.git`, `.agents`, внутренние `docs/`, envs, cache, coverage, build/dist, runtime data, datasets, media, IDE files.
- [ ] E15.8 Script повторно открывает ZIP и проверяет blacklist.
- [ ] E15.9 Инструкция настройки consumer <= 5 предложений.
- [ ] E15.10 Clean-environment smoke из содержимого submission package.
- [ ] E15.11 Подготовить отдельную краткую презентацию, проверяемую ссылку на VCS и публичный URL для обязательных полей финальной формы; медиа не включать в source ZIP.

### Acceptance

Clean ZIP проходит self-inspection, из его содержимого сервис можно собрать/запустить, deployed endpoint доступен.

**Dependencies:** runnable E4 для первого ZIP/deploy. Финальный ZIP и deployed checks выполняются повторно после интеграции E6–E13 и уточнения E14.

---

## Epic E16 — Submission verification

**Goal:** финальная доказательная приёмка, без новой разработки.

### Tasks

- [ ] E16.1 Запустить `release-verification` в режиме `submission`.
- [ ] E16.2 Packaging/external code-quality gate.
- [ ] E16.3 Deployed API/contract/idempotency/concurrency/429 gate.
- [ ] E16.4 Full PII quality gate.
- [ ] E16.5 Performance/reliability/100k-token gate.
- [ ] E16.6 Consumer policy/extensibility gate.
- [ ] E16.7 Security/logging/metrics gate.
- [ ] E16.8 Documentation/known limitations gate.
- [ ] E16.9 Любой непроверенный mandatory criterion => `block`, не Done.
- [ ] E16.10 После исправления blocker повторить только затронутые проверки, затем финальный gate.
- [ ] E16.11 Проверить обе операции сайта: внешнюю проверку ZIP и отдельную окончательную отправку ZIP, презентации, VCS и URL до 23 сентября, 23:59 МСК.

### Acceptance

Для verdict `pass`: `release-verification: submission -> pass`, обязательная внешняя code-quality проверка пройдена, deployed endpoint доступен. При `block` до дедлайна разрешена отправка имеющегося результата с явным указанием непроверенных/проваленных критериев; отправка не меняет verdict.

**Milestone:** M4 / Submission ready.

**Dependencies:** E15.

---

## 2. Parallelization rules

После стабилизации E1/E5 безопасно параллелить:

- E6 structured detectors;
- E7 semantic/contextual detectors;
- подготовку quality corpus E10.1–E10.7;
- E12 observability;
- k6 scenario из E13;
- packaging tooling из E15.

Не раздавать разным implementation owners одновременно:

- ProcessService state machine;
- Redis session semantics;
- mapping model для demask;
- OverlapResolver.

Это shared mechanisms с высоким риском несовместимых решений.

## 3. Risk-first priority

Самые рискованные зоны, которые нужно вскрыть рано:

1. state machine + retry + concurrency;
2. semantic PII quality: FIO/address/issuer/birthplace;
3. competition mask format;
4. реальный 1000 successful RPS;
5. AlfaSonar access ambiguity.

При обнаружении проблемы исправлять минимальный затронутый механизм, а не расширять scope всего проекта.

## 4. Bonus backlog

Только после M4 baseline:

- 2000 RPS;
- synthetic replacement;
- дополнительные удостоверяющие документы;
- advanced configurable masking/tokenization;
- conditional masking по комбинации нескольких PII;
- demo/admin UI.

Бонус не может ухудшать mandatory quality/performance/security.

## 5. Правило ведения плана

- Использовать task IDs `E<epic>.<task>` в task briefs/PR/commit context, где это помогает.
- После accepted самостоятельной подзадачи или логически связанного набора подзадач фиксировать проверенное состояние commit-ом до перехода к существенно другой работе.
- Граница каждого Epic и Milestone всегда завершается commit-ом; для длинной задачи допускаются дополнительные стабильные checkpoints.
- Commit создаётся после актуальных проверок/review и не заменяет acceptance. Не делать commit на каждую мелкую правку и не собирать независимые изменения в один огромный commit.
- Отмечать выполненные checkbox только после acceptance конкретной задачи/эпика.
- Не превращать этот файл в журнал реализации.
- Новое обязательное требование сначала попадает в `REQUIREMENTS.md`, архитектурное изменение — в `ARCHITECTURE.md`/`DECISIONS.md`, и только потом корректируется этот план.
- Если задача оказалась не нужна для mandatory baseline, удалить/перенести её, а не реализовывать потому, что она когда-то попала в план.
