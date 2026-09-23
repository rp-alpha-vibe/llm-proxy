# Railway deployment

Актуальный публичный API: https://llm-proxy-production-84c7.up.railway.app. Проект Railway `alpha-vibe`, окружение `production`, регион обоих сервисов EU West (Amsterdam). Первоначально проверен deploy commit `1de1a4f3019127d060243327ef8a597a4d1a29c2` из приватного `rp-alpha-vibe/llm-proxy`; ветка `main` подключена к автоматическому deploy, поэтому актуальный SHA нужно смотреть в Railway Deployments. Приложение и Redis работают в одном экземпляре каждый, без serverless sleep. Локальный ПК и Cloudflare Tunnel для работы API не нужны.

## Состав и настройка

- `llm-proxy`: сборка из `/Dockerfile`, публичный Railway HTTPS-домен на порт `8000`, healthcheck `/healthz`, один Uvicorn worker.
- `redis`: официальный `redis:7-alpine`, только приватная сеть Railway, без публичного домена и постоянного тома. Один экземпляр, AOF и RDB snapshots отключены. При перезапуске Redis незавершённые сессии пропадут; новый mask-запрос создаст новую сессию.
- Redis ACL отключает `default`, разрешает отдельному `proxy` доступ к `session:*` и минимальным командам. Пароль хранится в `REDIS_PASSWORD` сервиса Redis. При запуске временный ACL-файл создаётся с `umask 077`; значение пароля не пишется в репозиторий. В приложении `LLM_PROXY_REDIS_URL` использует Railway reference `redis://proxy:${{redis.REDIS_PASSWORD}}@${{redis.RAILWAY_PRIVATE_DOMAIN}}:6379/0`.
- `LLM_PROXY_ENCRYPTION_KEY` хранится только в переменных Railway. Приложение использует `LLM_PROXY_CONFIG_PATH=/app/config/systems.example.yaml`, `LLM_PROXY_DEFAULT_CONSUMER_ID=alfa_tester`, `LLM_PROXY_APP_HOST=0.0.0.0`, `LLM_PROXY_APP_PORT=8000`, `PORT=8000`, `LLM_PROXY_WEB_WORKERS=1`. TTL сессии — `900` секунд, TTL после демаскирования — `120` секунд, лимит параллельных запросов — `100`.

В Railway Redis start command:

```sh
/bin/sh -c 'umask 077; printf "user default off\nuser proxy on >%s ~session:* +get +set +expire +del +ping +ttl +info +config|get +client|setinfo\n" "$REDIS_PASSWORD" > /tmp/users.acl; exec redis-server --aclfile /tmp/users.acl --appendonly no --save ""'
```

## Повторное развёртывание и обновление

Для восстановления создайте в Railway проект с двумя сервисами в одном регионе. Redis создайте из `redis:7-alpine`, задайте ему секрет `REDIS_PASSWORD` и приведённую команду запуска; не назначайте публичный домен и volume. Приложение подключите к приватному GitHub-репозиторию, выберите Dockerfile builder, ветку `main`, один экземпляр и healthcheck `/healthz`. Задайте переменные выше, сгенерируйте новый ключ шифрования длиной 16/24/32 байта и добавьте публичный домен на порт `8000`. Не копируйте существующие секреты в документацию или терминальные логи.

Новый commit в `main` автоматически запускает сборку и deploy приложения. После обновления проверьте SHA активного deployment в Railway, затем `GET /healthz`, маскирование и демаскирование через `POST /process`, `GET /metrics`. Redis при изменении приложения пересоздавать не требуется. При смене ключа шифрования старые сессии перестанут демаскироваться; дождитесь истечения TTL либо запланируйте окно без активных сессий.

## Проверка и диагностика

```sh
curl -fsS https://llm-proxy-production-84c7.up.railway.app/healthz
curl -fsS https://llm-proxy-production-84c7.up.railway.app/metrics
```

`/healthz` должен вернуть `{"status":"ok"}`. Для `/process` используйте только синтетические данные: первый запрос с `payload` и `payload_id` маскирует ПД, повтор исходного запроса с тем же `payload_id` возвращает тот же результат, а передача маскированного ответа с тем же ID восстанавливает исходный текст. У приложения и Redis в Railway должны быть статусы Online/Active; в Deployments и Logs смотрите ошибки запуска и обращения к Redis. Redis Console: неавторизованный `PING` должен дать `NOAUTH`; авторизованные `CONFIG GET appendonly save` — `no` и пустой `save`; `TTL` ключа сессии после mask должен быть положительным. Не выводите содержимое сессии, пароли или реальные ПД в журнал диагностики.

## Ограничения тарифа

Railway Limited Trial показывает одноразовый кредит $5 и 30 дней; платёжный метод не добавлен. После исчерпания кредита Railway остановит deployments. На момент первоначальной проверки расход составил около $0.0003; это слишком короткий интервал, чтобы гарантировать доступность до 30 сентября 2026 года. Проверяйте `Workspace → Usage` и публичный healthcheck ежедневно, особенно перед прогоном организаторов. Публичный `/metrics` доступен без авторизации, как и `/process`; не добавляйте в запросы реальные ПД. [Короткий probe на Railway](../submission/railway-load-probe-2026-09-23.md) дал 12 неуспешных операций из 3001 при 100 RPS; причина ошибок не локализована. Полный профиль 1000 RPS / 300 секунд на Railway не проводился. Локальный benchmark не доказывает производительность пробного хостинга.
