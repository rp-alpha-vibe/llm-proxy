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

Требования: Python 3.12 и Docker Compose. Скопируйте `.env.example` в `.env`, задайте `LLM_PROXY_ENCRYPTION_KEY` длиной 16, 24 или 32 байта и запустите стек.

Потребитель задаётся `LLM_PROXY_DEFAULT_CONSUMER_ID` и должен совпадать с ключом секции `systems` в `config/systems.example.yaml`. Для официального прогона оставьте `alfa_tester`: политика `competition` пишет локальный обратимый токен `<TYPE_n>`. Ключ шифрования сессии передаётся только через окружение и в репозиторий не попадает. Redis остаётся во внутренней сети compose и наружу не публикуется. Запрос тестера — `POST /process` с полями `payload` и `payload_id`, без дополнительных обязательных заголовков.

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

E0–E13 и E15.1–E15.10 завершены. Материалы E15.11: `submission/presentation.html`, `submission/CHECKLIST.md`; ZIP — `python scripts/package.py`. На этой машине локальный load baseline: 300001 успешных операций за 300 с, p95 21.78 мс, 0 ошибок/429 (не официальный scoring). Quality gate: локальный F1 1.0 на 46 fixtures. VCS: https://github.com/rp-alpha-vibe/llm-proxy (сейчас private). Публичный URL для формы может быть временным Cloudflare Tunnel, пока ПК и tunnel запущены; durable deploy — отдельное решение владельца. E14 AlfaSonar и внешняя проверка ZIP на сайте организаторов ещё не закрыты.
