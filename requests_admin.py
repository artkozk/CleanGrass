"""Админская часть заявок с сайта и из MAX для основного Telegram-бота.

Подключается из main.py: requests_admin.register(bot, is_admin) —
обязательно ДО fallback-обработчика текста.

Умеет:
- кнопки регулярки: sub:ok:<id> (подтвердить + назначить дату первого
  покоса), sub:no:<id> (отклонить pending / отменить active);
- кнопки разовых заявок: req:take:<id> («взял в работу», клиент в MAX
  получает подтверждение), req:rej:<id> (отклонить, без сообщений клиенту);
- команды администратора: /subs — активные и ожидающие регулярки,
  /zayavki — необработанные заявки с кнопками.

Ответы клиентам уходят в MAX по HTTP API (MAX_TOKEN из .env).
"""
import json
import logging
import os
import re
import sqlite3
import urllib.parse
import urllib.request
from datetime import date, datetime

from config import DB_NAME

MAX_API = 'https://botapi.max.ru'
MAX_TOKEN = os.getenv('MAX_TOKEN', '')


def _db():
    conn = sqlite3.connect(DB_NAME, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _esc(s):
    return str(s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _ensure_columns():
    db = _db()
    for ddl in ("ALTER TABLE site_requests ADD COLUMN kind TEXT NOT NULL DEFAULT 'pokos'",
                'ALTER TABLE site_requests ADD COLUMN max_user_id INTEGER'):
        try:
            db.execute(ddl)
        except sqlite3.OperationalError:
            pass
    db.commit()
    db.close()


def max_send(user_id, text):
    if not MAX_TOKEN or not user_id:
        return
    url = f'{MAX_API}/messages?' + urllib.parse.urlencode({'user_id': user_id})
    req = urllib.request.Request(
        url, data=json.dumps({'text': text}, ensure_ascii=False).encode(),
        method='POST',
        headers={'Authorization': MAX_TOKEN, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()
    except Exception as e:
        logging.error(f'max_send to {user_id}: {e}')


def parse_date(text):
    m = re.search(r'(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?', text or '')
    if not m:
        return None
    day, month = int(m.group(1)), int(m.group(2))
    year = m.group(3)
    year = int(year) + (2000 if year and int(year) < 100 else 0) if year else date.today().year
    try:
        d = date(year, month, day)
    except ValueError:
        return None
    if not m.group(3) and d < date.today():
        d = date(year + 1, month, day)
    return d


KIND_TITLES = {'pokos': 'Разовый покос', 'zamer': 'Бесплатный замер', 'regular': 'Регулярный покос'}


def register(bot, is_admin):
    _ensure_columns()

    # ---------- регулярка ----------

    def get_sub(sub_id):
        db = _db()
        row = db.execute('SELECT * FROM subscriptions WHERE id=?', (sub_id,)).fetchone()
        db.close()
        return row

    def ask_date(chat_id, sub_id):
        msg = bot.send_message(
            chat_id,
            f'📅 Дата первого покоса для заявки #{sub_id}?\n'
            'Напишите, например: <b>15.07</b>')
        bot.register_next_step_handler(msg, lambda m: set_date(m, sub_id))

    def set_date(message, sub_id):
        d = parse_date(message.text)
        if not d:
            bot.send_message(message.chat.id, 'Не понял дату. Пример: 15.07')
            ask_date(message.chat.id, sub_id)
            return
        sub = get_sub(sub_id)
        if not sub or sub['status'] not in ('pending', 'active'):
            bot.send_message(message.chat.id, f'Заявка #{sub_id} уже неактуальна.')
            return
        db = _db()
        db.execute("UPDATE subscriptions SET status='active', next_date=?, last_reminded=NULL "
                   'WHERE id=?', (d.isoformat(), sub_id))
        db.commit()
        db.close()
        bot.send_message(
            message.chat.id,
            f'✅ Регулярный покос #{sub_id} подтверждён.\n'
            f'📍 {_esc(sub["address"])}\n📅 Первый покос: {d.strftime("%d.%m.%Y")}, '
            f'дальше каждые {sub["interval_days"]} дней.\n'
            'Накануне каждого покоса напомню и вам, и клиенту.')
        max_send(sub['user_id'],
                 f'✅ Регулярный покос подтверждён!\n'
                 f'Первый покос — {d.strftime("%d.%m")}, дальше раз в 2 недели.\n'
                 'Накануне каждого покоса напомню здесь.')

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith('sub:'))
    def sub_actions(c):
        if not is_admin(c.from_user.id):
            bot.answer_callback_query(c.id, 'Только для администратора')
            return
        _, action, sid = c.data.split(':')
        sub_id = int(sid)
        sub = get_sub(sub_id)
        if not sub:
            bot.answer_callback_query(c.id, 'Заявка не найдена')
            return
        if sub['status'] not in ('pending', 'active'):
            bot.answer_callback_query(c.id, f'Заявка уже в статусе «{sub["status"]}»')
            return
        bot.answer_callback_query(c.id)
        try:
            bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id,
                                          reply_markup=None)
        except Exception:
            pass
        if action == 'ok':
            ask_date(c.message.chat.id, sub_id)
        elif action == 'no':
            was_active = sub['status'] == 'active'
            db = _db()
            db.execute("UPDATE subscriptions SET status=? WHERE id=?",
                       ('cancelled' if was_active else 'declined', sub_id))
            db.commit()
            db.close()
            bot.send_message(c.message.chat.id,
                             f'❌ Регулярка #{sub_id} {"отменена" if was_active else "отклонена"}.')
            if was_active:
                max_send(sub['user_id'],
                         'Регулярный покос отменён. Понадобится снова — '
                         'оставьте заявку в боте.')
            else:
                max_send(sub['user_id'],
                         'Пока не получается подтвердить регулярный покос — '
                         'перезвоним и обсудим детали.')

    # ---------- разовые заявки ----------

    def get_req(req_id):
        db = _db()
        row = db.execute('SELECT * FROM site_requests WHERE id=?', (req_id,)).fetchone()
        db.close()
        return row

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith('req:'))
    def req_actions(c):
        if not is_admin(c.from_user.id):
            bot.answer_callback_query(c.id, 'Только для администратора')
            return
        _, action, rid = c.data.split(':')
        req_id = int(rid)
        row = get_req(req_id)
        if not row:
            bot.answer_callback_query(c.id, 'Заявка не найдена')
            return
        if row['status'] != 'new':
            bot.answer_callback_query(c.id, f'Уже обработана ({row["status"]})')
            return
        new_status = 'taken' if action == 'take' else 'rejected'
        db = _db()
        db.execute('UPDATE site_requests SET status=? WHERE id=?', (new_status, req_id))
        db.commit()
        db.close()
        bot.answer_callback_query(c.id, 'Взял в работу' if action == 'take' else 'Отклонена')
        try:
            bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id,
                                          reply_markup=None)
        except Exception:
            pass
        bot.send_message(c.message.chat.id,
                         f'{"✅" if action == "take" else "🗑"} Заявка #{req_id} '
                         f'{"в работе" if action == "take" else "отклонена"}.')
        if action == 'take':
            try:
                max_uid = row['max_user_id']
            except (KeyError, IndexError):
                max_uid = None
            if max_uid:
                max_send(max_uid, '✅ Приняли вашу заявку в работу — перезвоним и договоримся.')

    # ---------- команды ----------

    @bot.message_handler(commands=['subs'])
    def cmd_subs(message):
        if not is_admin(message.from_user.id):
            return
        db = _db()
        rows = db.execute("SELECT * FROM subscriptions WHERE status IN ('pending','active') "
                          'ORDER BY next_date IS NULL, next_date').fetchall()
        db.close()
        if not rows:
            bot.send_message(message.chat.id, 'Активных регулярок нет.')
            return
        for sub in rows:
            if sub['status'] == 'active' and sub['next_date']:
                d = datetime.strptime(sub['next_date'], '%Y-%m-%d')
                status = f'📅 следующий: {d.strftime("%d.%m")}'
            else:
                status = '⏳ ждёт подтверждения'
            kb = {'inline_keyboard': [[{'text': '❌ Отменить',
                                        'callback_data': f'sub:no:{sub["id"]}'}] +
                                      ([{'text': '✅ Подтвердить',
                                         'callback_data': f'sub:ok:{sub["id"]}'}]
                                       if sub['status'] == 'pending' else [])]}
            bot.send_message(
                message.chat.id,
                f'🔁 Регулярка #{sub["id"]} — {status}\n'
                f'👤 {_esc(sub["name"])}\n☎️ <code>{_esc(sub["phone"])}</code>\n'
                f'📍 {_esc(sub["address"])}',
                reply_markup=json.dumps(kb))

    @bot.message_handler(commands=['zayavki'])
    def cmd_zayavki(message):
        if not is_admin(message.from_user.id):
            return
        db = _db()
        rows = db.execute("SELECT * FROM site_requests WHERE status='new' "
                          'ORDER BY id DESC LIMIT 8').fetchall()
        db.close()
        if not rows:
            bot.send_message(message.chat.id, 'Необработанных заявок нет. 👍')
            return
        for r in rows:
            try:
                kind = KIND_TITLES.get(r['kind'], r['kind'])
            except (KeyError, IndexError):
                kind = 'Покос'
            src = {'max': 'MAX', 'site': 'сайт'}.get(r['source'], r['source'])
            kb = {'inline_keyboard': [[
                {'text': '✅ Взял в работу', 'callback_data': f'req:take:{r["id"]}'},
                {'text': '🗑 Отклонить', 'callback_data': f'req:rej:{r["id"]}'},
            ]]}
            bot.send_message(
                message.chat.id,
                f'🧾 Заявка #{r["id"]} ({src}) — {kind}'
                f'{" · регулярно" if r["regular"] else ""}\n'
                f'👤 {_esc(r["name"])}\n☎️ <code>{_esc(r["phone"])}</code>\n'
                f'📍 {_esc(r["address"])}\n🕒 {r["created_at"]}',
                reply_markup=json.dumps(kb))
