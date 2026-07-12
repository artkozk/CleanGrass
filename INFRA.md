# Инфраструктура «Покос 48»

Сервер: Timeweb, `root@85.198.82.221` (вход по SSH-ключу).
Всё живёт в `/opt/cleangrass` (код ботов + база) и `/opt/pokos-site` (сайт).

## Компоненты

| Что | Файл | Сервис systemd | Порт |
|---|---|---|---|
| Telegram-бот (органайзер + админка заявок) | `main.py` (+ `requests_admin.py`) | `cleangrass-bot` | — (polling) |
| MAX-бот «Покос 48» для клиентов | `max_bot.py` | `pokos-max-bot` | — (polling) |
| API заявок с сайта | `site_api.py` | `pokos-site-api` | 127.0.0.1:8091 |
| Сайт pokos48.ru | `/opt/pokos-site/` | nginx (конфиг `pokos48`) | 80→443 |

- База — SQLite `/opt/cleangrass/grass_orders.db`, общая для всех трёх процессов.
- Токены — в `/opt/cleangrass/.env`: `BOT_TOKEN` (Telegram), `MAX_TOKEN` (MAX), в git не попадают.
- SSL — Let's Encrypt, автопродление через `certbot.timer`.
- Бэкап базы — ежедневно в `DIGEST_HOUR` Telegram-бот шлёт файл базы админу (внутри `main.py`).

## Таблицы заявок (создаются автоматически)

- `site_requests` — разовые заявки (сайт + MAX): name, phone, address, kind (`pokos`/`zamer`), source (`site`/`max`), status (`new`/`taken`/`rejected`), max_user_id.
- `subscriptions` — регулярка: status `pending` → (админ подтверждает в TG, задаёт дату) → `active`; `declined`/`cancelled`. next_date двигается на interval_days (14) автоматически.
- `max_clients`, `max_addresses` — память MAX-бота: телефон и адреса клиента.

## Потоки заявок

1. Сайт: форма → POST `/api/request` (nginx → 8091) → site_requests + карточка в TG с кнопками.
2. MAX: кнопки бота → site_requests/subscriptions + карточка в TG.
3. Регулярка: карточка «Подтвердить/Отклонить» → дата первого покоса → напоминания
   накануне в 18:00 МСК клиенту (MAX) и админу (TG) — поток `reminder_loop` в `max_bot.py`.

## Антиспам

- site_api: лимит 5 заявок/час с IP, honeypot-поле `website`, дедуп по телефону за 30 минут.
- max_bot: максимум 3 заявки в сутки на клиента, дедуп одинаковых необработанных заявок,
  пересылка свободных сообщений в TG — не больше 5 в час с человека.

## Команды администратора (в Telegram-боте)

- `/zayavki` — необработанные заявки с кнопками «Взял в работу / Отклонить».
- `/subs` — все регулярки со статусами и кнопками.

## Деплой

```sh
scp main.py max_bot.py requests_admin.py site_api.py root@85.198.82.221:/opt/cleangrass/
scp site/* root@85.198.82.221:/opt/pokos-site/
ssh root@85.198.82.221 "cd /opt/cleangrass && .venv/bin/python -m py_compile main.py max_bot.py requests_admin.py site_api.py && systemctl restart cleangrass-bot pokos-max-bot pokos-site-api"
```

Логи: `journalctl -u <сервис> -f` (у ботов PYTHONUNBUFFERED=1).
