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

Требования: Python 3.12 и Docker Compose. Для stateful processing задайте `LLM_PROXY_ENCRYPTION_KEY`; без ключа Redis state store отказывает fail-closed.

```bash
python -m pip install -e ".[dev]"
docker compose up --build -d
```

Проверить сервис:

```bash
curl http://localhost:8000/healthz
```

Остановить локальный стек:

```bash
docker compose down
```

## Проверка

Одна команда запускает formatter, lint, typecheck и pytest:

```bash
python scripts/verify.py
```

CI использует ту же команду.

## Текущий этап

E0–E3 завершены: каркас, Redis/Compose, typed settings, `healthz`, encrypted Redis state, ProcessService state machine, `verify` и CI реализованы. Публичный `POST /process`, consumer policy/auth, PII engine, quality/load baseline и submission readiness ещё не реализованы.
