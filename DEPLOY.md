# Розгортання Кривди на сервері

Інструкція для адміністратора сервера. Уся система запускається однією командою Docker Compose.
Доступ до Telegram серверу не потрібен: дані з Telegram збирає окремий сервіс (Telegram gateway),
розміщений поза мережею катедри. Сервер лише звертається до нього через HTTPS.

## Вимоги

- Linux із Docker Engine і Docker Compose v2: команда `docker compose version` має працювати.
- `git`.
- Вихідний доступ в інтернет (HTTPS) до:
  - GitHub (код), Docker Hub, `ghcr.io`, `docker.litellm.ai`, npm і PyPI (збірка образів);
  - `api.lapathoniia.top` (мовна модель);
  - адреси Telegram gateway на `*.vercel.app` (її надає розробник).
- Близько 4 ГБ RAM і 20 ГБ вільного диска.

## Перший запуск

```bash
git clone <адреса репозиторію> kryvda
cd kryvda
cp .env.example .env
nano .env          # заповнити п'ять значень із розділу REQUIRED, див. таблицю нижче
docker compose up -d --build
```

Перша збірка триває 5–15 хвилин. Після неї відкрийте `http://<адреса сервера>/`.

| Змінна | Звідки взяти |
| --- | --- |
| `POSTGRES_PASSWORD` | Згенерувати: `openssl rand -hex 24`. **Не змінювати після першого запуску** — база створюється з цим паролем. |
| `LITELLM_MASTER_KEY` | Згенерувати: `openssl rand -hex 32`. |
| `LAPATHONIIA_API_KEY` | Надає розробник. |
| `TELEGRAM_GATEWAY_URL` | Надає розробник, наприклад `https://kryvda-gateway.vercel.app`. |
| `TELEGRAM_GATEWAY_TOKEN` | Надає розробник. |

Решта значень у `.env` має робочі типові налаштування. Найчастіше змінюють лише `FRONTEND_PORT`
(порт веб-інтерфейсу, типово 80), якщо порт 80 уже зайнятий.

## Оновлення

```bash
cd kryvda
git pull
docker compose up -d --build
```

Міграції бази даних застосовуються автоматично. Дані зберігаються між оновленнями.

## Перевірка стану

```bash
docker compose ps
```

Усі сервіси мають бути `Up`. Сервіс `migrate` завершується одразу після старту зі статусом
`Exited (0)` — це нормально. Сервіс `telegram-gateway` на сервері не запускається, так і має бути.

```bash
curl http://localhost:8000/health                      # API живий
curl http://localhost:8000/channels/collection-health  # коли востаннє зібрано кожен канал
```

Збір із Telegram відбувається раз на годину (`COLLECTION_POLL_INTERVAL_SECONDS`), тож нові пости
з'являються із затримкою до години. Перший запуск поступово підтягує історію за рік.

## Логи

```bash
docker compose logs -f --tail=100 telegram-scraper   # збір із Telegram
docker compose logs -f --tail=100 ai-worker          # аналіз постів
docker compose logs --tail=100                       # усі сервіси
```

Логи обмежені за розміром і не переповнять диск.

## Резервні копії

Сервіс `backup` раз на добу зберігає копію бази в теку `./backups` і видаляє копії, старші за
`BACKUP_RETENTION_DAYS` днів (типово 14). Тека `./backups` варто додатково копіювати на інший
носій.

Відновлення з копії (замінює поточні дані):

```bash
docker compose stop api telegram-scraper ai-worker
docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < backups/<файл>.dump
docker compose up -d
```

## Зупинка і перезавантаження сервера

```bash
docker compose stop      # зупинити, дані зберігаються
docker compose up -d     # запустити знову
```

Після перезавантаження сервера все стартує саме, якщо служба Docker увімкнена в автозапуск:
`sudo systemctl enable docker`.

Команда `docker compose down -v` **видаляє базу даних**. Не використовуйте її без резервної копії.

## Мережа і безпека

- Назовні відкритий лише порт веб-інтерфейсу (`FRONTEND_PORT`).
- API (`8000`) і PostgreSQL (`5432`) доступні лише з самого сервера (`127.0.0.1`).
- Через веб-інтерфейс API доступний лише для читання; зміни реєстру виконуються з самого сервера.
- Файл `.env` містить секрети: не додавайте його в git і не пересилайте відкритими каналами.

## Типові проблеми

| Симптом | Що зробити |
| --- | --- |
| `required variable ... is missing a value` під час запуску | Заповнити вказану змінну в `.env`. |
| Помилка збірки під час завантаження пакетів (npm, PyPI, Docker Hub) | Фаєрвол блокує ці адреси — дозволити їх або звернутися до розробника. |
| `port is already allocated` | Змінити `FRONTEND_PORT` (або `API_PORT`/`POSTGRES_PORT`) у `.env`. |
| У `collection-health` помилка `Telegram gateway is unreachable` | Перевірити доступ: `curl -I <TELEGRAM_GATEWAY_URL>/health`. Має повернути `200`. |
| Помилка `Telegram gateway returned 401` | `TELEGRAM_GATEWAY_TOKEN` у `.env` не збігається з токеном gateway — уточнити в розробника. |
| Помилка `Telegram gateway returned 503` | Telegram-сесія відкликана — повідомити розробника. |
| Помилка `rate limited` | Telegram тимчасово обмежив запити; збір відновиться сам наступного запуску. |
