# llm-proxy

Модуль защиты персональных данных для хакатона Альфавайб.

## Что мы делаем

Строим быстрый HTTP-модуль защиты ПД в цепочке взаимодействия системы-потребителя с LLM:

```text
consumer -> detect PII -> mask -> LLM
consumer <- unmask <- LLM
```

Схема выше логическая: baseline-сервис не выполняет сетевой вызов к LLM. Потребитель передаёт в модуль текст до отправки в модель и затем передаёт ответ LLM для демаскирования.

Сервис должен находить обязательные типы ПД, маскировать их без лишних false positives, восстанавливать ПД внутри ответа LLM, поддерживать разные политики потребителей и выдерживать нагрузку хакатона.

Полная исполнимая спецификация и критерии сдачи: [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md).

## Когда проект можно сдавать

Baseline считается готовым только когда одновременно:

- пройдена обязательная автоматическая code-quality проверка;
- развёрнутый `POST /process` доступен и строго соответствует контракту;
- покрыты все обязательные категории ПД и проверен exact round-trip;
- демаскирование сохраняет новый текст ответа LLM при перестановке и повторении известных масок;
- проверены retry/idempotency/concurrency/429;
- пройдены локальные пороги нагрузки из requirements §7.1 и отдельно проверены крупные тексты до 100 000 токенов;
- работают per-system access/policy настройки;
- подтверждена совместимость доступа тестера с официальным контрактом без несогласованных обязательных полей/заголовков;
- безопасны хранение, логи и метрики; доступны Latency/RPS/TPS;
- подготовлен чистый ZIP только с исходниками;
- `release-verification` в режиме `submission` не имеет блокеров.

Бонусы вроде 2000 RPS, синтетической замены и дополнительных документов делаем только после обязательного baseline.
Срок окончательной отправки на сайте организаторов — 23 сентября 2026 года, 23:59 МСК. Раздел проверки ZIP и финальная форма — разные шаги; для формы также нужны отдельная презентация (до 50 МБ), ссылка на VCS и URL работающего сервиса. Оперативный порядок работ указан в [плане](docs/IMPLEMENTATION_PLAN.md). Если локальный gate не пройден, это честно отмечается как `block` готовности, но не запрещает отправить имеющийся результат до дедлайна.

## AI-разработка

- [AGENTS.md](AGENTS.md) — лёгкий процесс разработки, review и приёмки.
- [Требования](docs/REQUIREMENTS.md) — что именно обязано работать для успешной сдачи.
- [Архитектура](docs/ARCHITECTURE.md) — принятый runtime, state, PII pipeline, masking и deployment.
- [План реализации](docs/IMPLEMENTATION_PLAN.md) — эпики, подзадачи, зависимости и milestones до submission.
- [Решения](docs/DECISIONS.md) — только важные принятые решения.
- [Skills](.agents/skills/) — requirements, architecture, review, PII quality, performance и release verification.

Реализацию выполняет DeepSeek. Общая точка входа — `AGENTS.md`; канонические skills находятся в `.agents/skills/`.
Если клиент не загружает их автоматически, передать `AGENTS.md` и нужный `.agents/skills/<name>/SKILL.md` явно.

## Запуск

Требования: Python 3.12 и Docker Compose. Скопируйте `.env.example` в `.env`, задайте `LLM_PROXY_ENCRYPTION_KEY` длиной 16, 24 или 32 байта и запустите стек:

```bash
python -m pip install -e ".[dev]"
docker compose up --build -d
```

Проверить сервис:

```bash
curl http://localhost:8000/healthz
```

Процесс слушает HTTP. Если площадка даёт ingress с TLS, завершение TLS остаётся на ней. Собственный TLS в процесс не добавляется: официальный tester допускает HTTP.

Локальная нагрузка, не официальный scoring:

```bash
python scripts/bench_hot_path.py
docker run --rm -v "$(pwd)/scripts/load:/scripts" -e RATE=1000 grafana/k6 run /scripts/mask_unmask.js
```

`mask_unmask.js` держит пороги §7.1: 1000 успешных операций в секунду на окне 300 с после прогрева, p95 не выше 1 с, без 429 и без ошибок. Профиль перегрузки — `scripts/load/overload.js`; там 429 допустим и baseline не заменяет.

`GET /metrics` отдаёт Prometheus-метрики. RPS — это rate `requests_total`, latency — histogram `request_duration_seconds`, TPS — rate `processed_tokens_total`. Token для TPS — непустой фрагмент между Unicode-пробелами; это не tokenizer конкретной LLM и не официальная метрика Альфы. Несколько workers задаются `LLM_PROXY_WEB_WORKERS`. Они должны делить `PROMETHEUS_MULTIPROC_DIR`: в Docker он уже равен `/tmp/prometheus-multiproc`. `GET /metrics` суммирует процессы этого каталога.

Остановить локальный стек:

```bash
docker compose down
```

## Проверка

Одна команда запускает formatter, lint, typecheck и pytest:

```bash
python scripts/verify.py
python -m llm_proxy.quality
```

`python -m llm_proxy.quality` печатает локальные precision/recall/F1, false positives и exact round-trip по синтетическому корпусу из 46 fixtures. Пороги зафиксированы в `src/llm_proxy/quality/gate.py`: F1 не ниже 0.95 по каждой покрытой категории, round-trip 1.0, на negative fixtures нет срабатываний. Это не официальный span-based scoring.

CI использует ту же команду.

## Политики потребителей

Добавьте систему в `config/systems.example.yaml` под `systems` и задайте для неё `enabled`, `pii_types` и `allow_demask`. Потребитель runtime выбирается через `LLM_PROXY_DEFAULT_CONSUMER_ID`; официальный запрос `/process` не содержит `system_id` или обязательного auth header. Перезапустите приложение после изменения YAML; неизвестный или отключённый потребитель получает отказ, а policy и Redis-session остаются изолированными. Поле `mask_strategy` выбирает renderer: `placeholder` или `competition`.

## Текущий этап

E0–E13 завершены в части правил, renderer-ов, product demask, локального quality gate, security tests, observability и локального load baseline. На этой машине (24 CPU, Redis 7, 8 workers) окно 300 с после 15 с прогрева дало 300001 успешную baseline-операцию, 0 ошибок и 0 ответов 429. p50 3.78 мс, p95 21.78 мс, p99 57.15 мс, max 286.37 мс. Это не официальный прогон организаторов и не 2000 RPS. На каждый `POST /process` пишется один JSON completion log без сырых ПД: operation, status, latency, типы и число ПД, а также `detect_ms` / `redis_ms` / `total_ms`. Security tests проверяют, что синтетические ФИО, телефон, email, PAN и паспорт не попадают в логи, ответ `/metrics`, plaintext Redis и тела ошибок. Сессии разных потребителей и `payload_id` не раскрывают mapping. Ключ шифрования задаётся через окружение, `.env` не коммитится. Реальный Redis TTL проверяется, когда Redis доступен; иначе тест пропускается и не заменяет живой прогон. `POST /process` проходит policy и `ProcessService` до Redis: новый payload маскируется, повтор исходного текста возвращает ту же маску, точная маска восстанавливает исходный текст. Синтетический ответ LLM восстанавливает известные однозначные маски `placeholder` и `competition` при перестановке и повторе, сохраняет новый текст и оставляет неизвестные или неоднозначные токены. Policy `placeholder` маскирует как `[[PII:TYPE:n]]`, policy `competition` — как `<TYPE_n>`. Второй формат — локальное обратимое допущение, пока нет официального образца маски. `python -m llm_proxy.quality` на 46 синтетических fixtures дал локальный F1 1.0 по каждой обязательной категории, round-trip 1.0 и ноль срабатываний на negative fixtures. Пороги в `gate.py` не снижались. Это не официальный span-based scoring. Локальный NLP/NER не добавлялся: E7.12–E7.13 остаются открытыми, потому что этот корпус не показал quality gap. Async-тесты запускаются через `pytest-asyncio`. Smoke `test_http_redis_mask_retry_and_exact_unmask` использует Redis по `LLM_PROXY_TEST_REDIS_URL` или `redis://127.0.0.1:6379/15` и пропускается, если Redis недоступен; пропуск не заменяет прогон на реальном Redis. Официальный способ допуска AlfaSonar остаётся открытой границей и блокером submission readiness. Load baseline и submission packaging ещё в работе.
