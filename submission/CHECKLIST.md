# E15.11 — материалы окончательной отправки

Дедлайн формы: **23 сентября 2026, 23:59 МСК**.
Форма: https://reg.vibecoding-hackathon.ru/solution/solution

Презентация и медиа **не** входят в source ZIP.

| Элемент | Статус | Значение / действие |
| --- | --- | --- |
| Source ZIP | готово локально | `python scripts/package.py` → `dist/llm-proxy-src.zip` |
| Презентация | готово к экспорту | `submission/presentation.html` → Print → PDF (до 50 МБ) |
| Ссылка на VCS | есть, но **private** | https://github.com/rp-alpha-vibe/llm-proxy |
| Публичный URL сервиса | **Railway, работает сейчас** | https://llm-proxy-production-84c7.up.railway.app |
| Нагрузка Railway | probe 100 RPS **pass**; полный 1000/300 с **block** | [отчёт](railway-load-probe-2026-09-23.md); ~33% ошибок, 76k×429, p95≈10 с |
| Внешняя проверка ZIP на сайте | не подтверждена | отдельный шаг формы |
| E14 AlfaSonar | **блокер** | нужен доступ/self-check организаторов |

Проверено на Railway HTTPS URL для commit `0319247f94ca75d3f97cd0445bead1d59634d8fc`, активного во время проверки: `GET /healthz` → 200; `POST /process` с синтетическим email → mask, retry с тем же `payload_id` → тот же результат, передача маскированного ответа → exact unmask; `GET /metrics` → 200; невалидный запрос → 422 без traceback. Синтетический payload и `payload_id` отсутствуют в metrics и Railway Logs. Redis private, TTL и отсутствие plaintext в значении сессии проверены. Детали: [Railway deployment](../docs/DEPLOYMENT_RAILWAY.md).

Railway не зависит от локального ПК. Limited Trial даёт $5 на 30 дней и выключает deployments при исчерпании кредита; проверять Usage и доступность до 30 сентября 2026 года. Продолжительная доступность пока не доказана.

## Что должен сделать владелец

1. Решить, может ли репозиторий быть public, или выдать организаторам read-доступ. Сейчас `isPrivate: true`.
2. Открыть `submission/presentation.html` в браузере → Print → Save as PDF и загрузить PDF на форму.
3. Использовать постоянный Railway URL из таблицы; перед отправкой проверить `/healthz` и остаток кредита в Railway.
4. Загрузить на сайт: ZIP, PDF презентации, VCS URL, URL сервиса.
5. Не путать предварительную проверку ZIP с окончательной отправкой формы.

## Развёртывание

Фактическая схема и порядок повторного deploy описаны в [docs/DEPLOYMENT_RAILWAY.md](../docs/DEPLOYMENT_RAILWAY.md). E14 AlfaSonar, внешняя проверка ZIP и E16 submission gate остаются открытыми.
