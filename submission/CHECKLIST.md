# E15.11 — материалы окончательной отправки

Дедлайн формы: **23 сентября 2026, 23:59 МСК**.
Форма: https://reg.vibecoding-hackathon.ru/solution/solution

Презентация и медиа **не** входят в source ZIP.

| Элемент | Статус | Значение / действие |
| --- | --- | --- |
| Source ZIP | готово локально | `python scripts/package.py` → `dist/llm-proxy-src.zip` |
| Презентация | готово к экспорту | `submission/presentation.html` → Print → PDF (до 50 МБ) |
| Ссылка на VCS | есть, но **private** | https://github.com/rp-alpha-vibe/llm-proxy |
| Публичный URL сервиса | **временный, работает сейчас** | https://nova-licensing-daughters-readers.trycloudflare.com |
| Внешняя проверка ZIP на сайте | не подтверждена | отдельный шаг формы |
| E14 AlfaSonar | **блокер** | нужен доступ/self-check организаторов |

Проверено на временном URL: `GET /healthz` → 200, `POST /process` с синтетическим email → `contact <EMAIL_1>`.

Tunnel живёт, пока на этой машине работают `docker compose -p llm-proxy-submit` и `cloudflared`. После перезапуска URL сменится. Для сдачи лучше заменить на durable deploy.

## Что должен сделать владелец

1. Решить, может ли репозиторий быть public, или выдать организаторам read-доступ. Сейчас `isPrivate: true`.
2. Открыть `submission/presentation.html` в браузере → Print → Save as PDF и загрузить PDF на форму.
3. Либо оставить этот ПК включённым с tunnel до конца проверки, либо выдать credentials на Render/Fly/Railway для постоянного URL.
4. Загрузить на сайт: ZIP, PDF презентации, VCS URL, URL сервиса.
5. Не путать предварительную проверку ZIP с окончательной отправкой формы.

## Рекомендация по durable deploy

Минимальный вариант совпадает с репозиторием: `Dockerfile` + `docker-compose.yml`, Redis private, HTTP наружу, TLS на площадке.

Обязательные env:

- `LLM_PROXY_ENCRYPTION_KEY` (16/24/32 байта, не из репозитория)
- `LLM_PROXY_DEFAULT_CONSUMER_ID=alfa_tester`
- `LLM_PROXY_CONFIG_PATH=/app/config/systems.example.yaml`
