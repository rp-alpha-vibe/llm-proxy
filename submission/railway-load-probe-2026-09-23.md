# Отчёт: нагрузочный probe на Railway

- **Дата:** 23 сентября 2026
- **Цель:** проверить устойчивость deployed URL перед полным gate `REQUIREMENTS.md` §7.1
- **URL:** https://llm-proxy-production-84c7.up.railway.app/
- **Скрипт:** `scripts/load/mask_unmask.js` (k6, Docker `grafana/k6`)
- **Официальный scoring организаторов:** не выполнялся и не заявляется

---

## 1. Контекст

Командный baseline §7.1 (не официальный прогон Альфы):

| Показатель | Условие pass |
| --- | --- |
| Успешный RPS | уникальные успешные операции / длительность окна ≥ target rate |
| Latency | p95 ≤ 1000 мс |
| Технические ошибки | 0% (таймауты, 5xx, сетевые сбои, невалидные ответы) |
| 429 на baseline | 0 |

План: короткий probe RATE=100 → при зелёном результате полный RATE=1000 на 300 с.

---

## 2. Probe A — исходный (fail)

| Параметр | Значение |
| --- | --- |
| `RATE` | 100 |
| Warmup / baseline | 10s / 30s |
| `preAllocatedVUs` / `maxVUs` | **800 / 5000** (жёстко в скрипте) |
| Exit code | 99 |

| Метрика baseline | Значение | Вердикт |
| --- | --- | --- |
| HTTP reqs | 3001 | — |
| `http_req_failed` | 0.39% (12) | **fail** |
| checks | 99.60% | **fail** |
| 429 | 0 | pass |
| p95 | 83.8 мс | pass |

Ошибки генератора: `request timeout`, `unexpected EOF`.  
Гипотеза: чрезмерный пул заранее выделенных VU у короткого probe создавал лишнюю конкуренцию/хвост на стороне клиента.

---

## 3. Probe B — после уменьшения VU (pass)

Изменения в `mask_unmask.js`:

- `PRE_ALLOCATED_VUS` / `MAX_VUS` задаются через env;
- при `RATE < 1000` дефолты меньше (не 800/5000);
- для полного baseline 1000 RPS прежние 800/5000 сохранены.

Команда:

```bash
docker run --rm ^
  -v "%cd%\scripts\load:/scripts" ^
  -v "%cd%\submission:/out" ^
  -e BASE_URL=https://llm-proxy-production-84c7.up.railway.app ^
  -e RATE=100 -e WARMUP_DURATION=10s -e BASELINE_DURATION=30s ^
  -e PRE_ALLOCATED_VUS=50 -e MAX_VUS=200 ^
  grafana/k6 run --summary-export=/out/k6-railway-probe-100rps-summary.json ^
  /scripts/mask_unmask.js
```

| Параметр | Значение |
| --- | --- |
| `PRE_ALLOCATED_VUS` / `MAX_VUS` | **50 / 200** |
| Наблюдаемый max VUs | 9 |
| Exit code | **0** |
| Сырые метрики k6 | `submission/k6-railway-probe-100rps-summary.json` |

| Метрика baseline | Значение | Вердикт |
| --- | --- | --- |
| HTTP reqs | 3001 | — |
| `http_req_failed` | **0.00%** (0) | **pass** |
| checks | **100%** | **pass** |
| unexpected_status / 429 / dropped | 0 / 0 / 0 | **pass** |
| p50 / p95 / p99 / max | ~78 / **86.04** / ~98 / 245.75 мс | **pass** (p95) |

Это **не** полный §7.1 на 1000 RPS / 300 с. Это зелёный короткий probe на Railway.

---

## 4. Вердикт

| Проверка | Вердикт |
| --- | --- |
| Функциональный smoke Railway | pass (отдельно подтверждён) |
| Probe 100 RPS / 30 с после настройки VU | **pass** |
| Полный §7.1 1000 RPS / 300 с на Railway | **block** (см. §4.1) |
| Локальный §7.1 на dev-машине | pass (справочно; не Railway) |

### 4.1. Полный baseline на Railway (RATE=1000, 300 с) — fail

| Метрика | Значение | Порог | Вердикт |
| --- | --- | --- | --- |
| Offered / успешный RPS baseline | ~1000 / **~644.8** (193444 корректных операций / 300 с) | ≥1000 успешных RPS | **fail** |
| HTTP reqs | 289982 baseline; 292944 вместе с warmup | — | — |
| `http_req_failed` | **33.29% baseline**; 32.95% вместе с warmup | 0% | **fail** |
| `status_429` | **76483** | 0 на baseline | **fail** |
| `dropped_iterations` | **10019 baseline**; 10057 вместе с warmup | 0 | **fail** |
| p50 / p95 / p99 / max latency baseline | 94.77 мс / **9.9999 с** / 10.0007 с / 10.0048 с | p95 < 1 с | **fail** |
| Exit code | 99 | 0 | **fail** |

Сырые метрики: `submission/k6-railway-baseline-1000rps-summary.json`.

Railway выдерживает короткий probe 100 RPS, но не командный gate 1000 RPS / 300 с (перегрузка → 429, таймауты, dropped iterations). Постфактум графики Railway за окно прогона показывали пик CPU приложения около 1,2 vCPU и памяти около 280 МБ; панель trial — остаток $4.99. Метрики ресурсов локального генератора не сохранены. Значения Railway сняты визуально с графиков, без экспорта сырых временных рядов.

---

## 5. Следующий шаг

Для 1000 RPS на Railway нужны более мощные ресурсы (больше workers/CPU) или принять, что deploy URL — для демо/функциональной сдачи, а доказательство §7.1 остаётся локальным. Пороги скрипта не ослаблять.

---

## 6. Итог одной строкой

Probe 100 RPS на Railway после уменьшения VU — pass; полный 1000 RPS / 300 с — **block** (≈33% ошибок, десятки тысяч 429, p95 ≈10 с).
