#!/usr/bin/env python3
"""MAX-бот «Покос 48» — приём заявок от клиентов из мессенджера MAX.

Что умеет:
- помнит клиента: телефон спрашивается один раз, адреса сохраняются,
  постоянному клиенту заказ подтверждается в один тап;
- три разных сценария: разовый покос, регулярный (раз в 2 недели,
  с подтверждением админа и напоминаниями накануне), бесплатный замер;
- заявки → grass_orders.db, уведомления админам → Telegram (HTML,
  телефон копируемым <code>-блоком);
- регулярка: карточка в TG с кнопками «Подтвердить/Отклонить»
  (обрабатывает requests_admin.py в основном боте), напоминания
  клиенту и админу накануне в REMIND_HOUR.

Токены в .env: MAX_TOKEN, BOT_TOKEN.
"""
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo('Europe/Moscow')
except Exception:
    TZ = timezone(timedelta(hours=3))

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, 'grass_orders.db')
API = 'https://botapi.max.ru'
REMIND_HOUR = int(os.getenv('MAX_REMIND_HOUR', '18'))

FLOWS = {
    'order': {'kind': 'pokos', 'title': 'Разовый покос'},
    'zamer': {'kind': 'zamer', 'title': 'Бесплатный замер'},
    'regular': {'kind': 'regular', 'title': 'Регулярный покос (раз в 2 недели)'},
}

GREETING = ('Здравствуйте! Это «Покос 48» — покос травы в Кузьминских Отвержках '
            'и соседних сёлах.\n\n'
            'Разовый покос — от 450 ₽/сотка, регулярный (раз в 2 недели) — '
            'от 400 ₽/сотка. Точная цена — после бесплатного замера.\n\n'
            'Выберите, что нужно, или просто напишите сообщение:')

BOT_ID = None
state: dict = {}
_forwarded: dict = {}        # антиспам пересылки сообщений в TG: user_id -> [timestamps]
_limit_notified: dict = {}   # когда клиенту последний раз говорили про лимит


def load_env():
    env = {}
    try:
        with open(os.path.join(BASE, '.env'), encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


ENV = load_env()
MAX_TOKEN = ENV.get('MAX_TOKEN', '')
TG_TOKEN = ENV.get('BOT_TOKEN', '')


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def db_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------- MAX API ----------------

def api(method, path, params=None, body=None, timeout=20):
    url = f'{API}{path}'
    if params:
        url += '?' + urllib.parse.urlencode(params)
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': MAX_TOKEN,
        'Content-Type': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def send(user_id, text, buttons=None):
    body = {'text': text}
    if buttons:
        body['attachments'] = [{'type': 'inline_keyboard', 'payload': {'buttons': buttons}}]
    try:
        api('POST', '/messages', {'user_id': user_id}, body)
    except Exception as e:
        print(f'send to {user_id} failed: {e}', file=sys.stderr)


# ---------------- schema ----------------

def ensure_schema():
    db = db_conn()
    db.execute('''CREATE TABLE IF NOT EXISTS site_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, phone TEXT NOT NULL, address TEXT NOT NULL,
        regular INTEGER NOT NULL DEFAULT 0,
        source TEXT NOT NULL DEFAULT 'site',
        status TEXT NOT NULL DEFAULT 'new',
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    )''')
    try:
        db.execute("ALTER TABLE site_requests ADD COLUMN kind TEXT NOT NULL DEFAULT 'pokos'")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute('ALTER TABLE site_requests ADD COLUMN max_user_id INTEGER')
    except sqlite3.OperationalError:
        pass
    db.execute('''CREATE TABLE IF NOT EXISTS max_clients (
        user_id INTEGER PRIMARY KEY,
        name TEXT, phone TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS max_addresses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        address TEXT NOT NULL,
        last_used TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT, phone TEXT, address TEXT,
        interval_days INTEGER NOT NULL DEFAULT 14,
        status TEXT NOT NULL DEFAULT 'pending',
        next_date TEXT,
        last_reminded TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    )''')
    db.commit()
    db.close()


# ---------------- clients memory ----------------

def get_client(user_id):
    db = db_conn()
    row = db.execute('SELECT * FROM max_clients WHERE user_id=?', (user_id,)).fetchone()
    db.close()
    return row


def upsert_client(user_id, name=None, phone=None):
    db = db_conn()
    db.execute('INSERT INTO max_clients (user_id, name, phone) VALUES (?, ?, ?) '
               'ON CONFLICT(user_id) DO UPDATE SET '
               'name=COALESCE(excluded.name, name), '
               'phone=COALESCE(excluded.phone, phone)',
               (user_id, name, phone))
    db.commit()
    db.close()


def client_addresses(user_id, limit=3):
    db = db_conn()
    rows = db.execute('SELECT id, address FROM max_addresses WHERE user_id=? '
                      'ORDER BY last_used DESC LIMIT ?', (user_id, limit)).fetchall()
    db.close()
    return rows


def save_address(user_id, address):
    db = db_conn()
    row = db.execute('SELECT id FROM max_addresses WHERE user_id=? AND lower(address)=lower(?)',
                     (user_id, address)).fetchone()
    if row:
        db.execute("UPDATE max_addresses SET last_used=datetime('now','localtime') WHERE id=?",
                   (row['id'],))
    else:
        db.execute('INSERT INTO max_addresses (user_id, address) VALUES (?, ?)',
                   (user_id, address))
    db.commit()
    db.close()


def get_subscription(user_id):
    db = db_conn()
    row = db.execute("SELECT * FROM subscriptions WHERE user_id=? AND status IN ('pending','active') "
                     'ORDER BY id DESC LIMIT 1', (user_id,)).fetchone()
    db.close()
    return row


# ---------------- Telegram ----------------

def admin_ids():
    try:
        db = db_conn()
        ids = [r[0] for r in db.execute('SELECT tg_id FROM admins')]
        db.close()
        return ids
    except Exception as e:
        print(f'admin_ids error: {e}', file=sys.stderr)
        return []


def _tg_notify_blocking(text, reply_markup=None):
    if not TG_TOKEN:
        return
    url = f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage'
    for chat_id in admin_ids():
        payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
        if reply_markup:
            payload['reply_markup'] = json.dumps(reply_markup)
        data = urllib.parse.urlencode(payload).encode()
        # Telegram с сервера бывает недоступен по несколько секунд —
        # без ретраев карточка молча теряется
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url, data=data, timeout=10) as resp:
                    resp.read()
                break
            except Exception as e:
                print(f'tg notify attempt {attempt + 1} failed: {e}', file=sys.stderr)
                time.sleep(5 * (attempt + 1))


def tg_notify(text, reply_markup=None):
    # в фоне: обработка апдейтов MAX не должна ждать Telegram
    threading.Thread(target=_tg_notify_blocking, args=(text, reply_markup),
                     daemon=True).start()


def client_line(name, user_id, username=None):
    who = esc(name or 'Клиент')
    if username:
        who += f' (max.ru/{esc(username)})'
    return f'👤 {who} · id {user_id}'


# ---------------- menu ----------------

def menu_for(user_id):
    buttons = [
        [{'type': 'callback', 'text': '🌱 Заказать покос', 'payload': 'order'}],
        [{'type': 'callback', 'text': '🔁 Регулярный покос — дешевле', 'payload': 'regular'}],
        [{'type': 'callback', 'text': '📏 Бесплатный замер', 'payload': 'zamer'}],
    ]
    if get_subscription(user_id):
        buttons.append([{'type': 'callback', 'text': 'ℹ️ Мой регулярный покос', 'payload': 'sub_info'}])
    buttons.append([{'type': 'link', 'text': '🌐 Цены и фото работ — pokos48.ru',
                     'url': 'https://pokos48.ru'}])
    return buttons


# ---------------- flows ----------------

def start_flow(user_id, name, flow):
    upsert_client(user_id, name=name)
    if flow == 'regular':
        sub = get_subscription(user_id)
        if sub:
            show_sub_info(user_id, sub)
            return
    addrs = client_addresses(user_id)
    if addrs:
        buttons = [[{'type': 'callback', 'text': f'📍 {a["address"][:40]}',
                     'payload': f'addr:{a["id"]}'}] for a in addrs]
        buttons.append([{'type': 'callback', 'text': '✏️ Другой адрес', 'payload': 'addr_new'}])
        state[user_id] = {'flow': flow, 'step': 'pick', 'name': name, 'ts': time.time()}
        send(user_id, 'По какому адресу?', buttons)
    else:
        state[user_id] = {'flow': flow, 'step': 'address', 'name': name, 'ts': time.time()}
        send(user_id, 'Напишите адрес участка: село, улица, дом.')


def address_chosen(user_id, address):
    st = state.get(user_id)
    if not st:
        return
    st['address'] = address[:200]
    save_address(user_id, st['address'])
    client = get_client(user_id)
    phone = client['phone'] if client else None
    if phone:
        finalize(user_id, st['name'], phone)
    else:
        st['step'] = 'phone'
        send(user_id, 'Оставьте номер телефона — по нему перезвоним. '
                      'Нажмите кнопку или напишите номер сообщением.',
             [[{'type': 'request_contact', 'text': '📱 Отправить мой номер'}]])


def too_many_today(user_id):
    db = db_conn()
    n = db.execute("SELECT COUNT(*) FROM site_requests WHERE max_user_id=? "
                   "AND created_at > datetime('now', 'localtime', '-1 day')",
                   (user_id,)).fetchone()[0]
    db.close()
    return n >= 3


def duplicate_pending(user_id, kind):
    db = db_conn()
    row = db.execute("SELECT id FROM site_requests WHERE max_user_id=? AND kind=? "
                     "AND status='new' AND created_at > datetime('now', 'localtime', '-1 day')",
                     (user_id, kind)).fetchone()
    db.close()
    return row is not None


def finalize(user_id, name, phone, username=None):
    st = state.pop(user_id, None)
    if not st:
        return
    upsert_client(user_id, name=name, phone=phone)
    flow, address = st['flow'], st['address']
    if flow == 'regular':
        if get_subscription(user_id):
            send(user_id, 'Заявка на регулярный покос у вас уже есть — скоро перезвоним.')
            return
        db = db_conn()
        cur = db.execute('INSERT INTO subscriptions (user_id, name, phone, address) '
                         'VALUES (?, ?, ?, ?)', (user_id, name, phone, address))
        sub_id = cur.lastrowid
        db.commit()
        db.close()
        print(f'subscription request #{sub_id}: {name}, {phone}, {address}')
        tg_notify(f'🔁 Заявка на РЕГУЛЯРНЫЙ покос #{sub_id}\n'
                  f'{client_line(name, user_id, username)}\n'
                  f'☎️ <code>{esc(phone)}</code>\n📍 {esc(address)}\n\n'
                  f'Подтвердите и назначьте дату первого покоса:',
                  {'inline_keyboard': [[
                      {'text': '✅ Подтвердить', 'callback_data': f'sub:ok:{sub_id}'},
                      {'text': '❌ Отклонить', 'callback_data': f'sub:no:{sub_id}'},
                  ]]})
        send(user_id, '✅ Заявка на регулярный покос отправлена!\n\n'
                      'Перезвоним, договоримся о первом дне — дальше буду напоминать '
                      'здесь накануне каждого покоса.')
    else:
        meta = FLOWS[flow]
        if duplicate_pending(user_id, meta['kind']):
            send(user_id, 'Такая заявка у вас уже есть — перезвоним по ней. '
                          'Хотите что-то уточнить — просто напишите сообщением.')
            return
        if too_many_today(user_id):
            send(user_id, 'На сегодня заявок достаточно 🙂 Мы перезвоним по уже '
                          'оставленным. Если срочно — напишите сообщением.')
            return
        db = db_conn()
        cur = db.execute("INSERT INTO site_requests (name, phone, address, regular, source, kind, max_user_id) "
                         "VALUES (?, ?, ?, 0, 'max', ?, ?)",
                         (name, phone, address, meta['kind'], user_id))
        req_id = cur.lastrowid
        db.commit()
        db.close()
        print(f'max request #{req_id}: {meta["title"]}, {name}, {phone}, {address}')
        tg_notify(f'💚 Заявка из MAX #{req_id}\n🧾 {meta["title"]}\n'
                  f'{client_line(name, user_id, username)}\n'
                  f'☎️ <code>{esc(phone)}</code>\n📍 {esc(address)}',
                  {'inline_keyboard': [[
                      {'text': '✅ Взял в работу', 'callback_data': f'req:take:{req_id}'},
                      {'text': '🗑 Отклонить', 'callback_data': f'req:rej:{req_id}'},
                  ]]})
        if flow == 'zamer':
            send(user_id, '✅ Заявка на замер принята! Перезвоним и договоримся, когда подъехать.')
        else:
            send(user_id, '✅ Заявка принята! Перезвоним в ближайшее время и договоримся о дне.')


def show_sub_info(user_id, sub):
    when = ''
    if sub['status'] == 'active' and sub['next_date']:
        d = datetime.strptime(sub['next_date'], '%Y-%m-%d')
        when = f'\nСледующий покос: {d.strftime("%d.%m")}.'
    elif sub['status'] == 'pending':
        when = '\nЖдёт подтверждения — скоро перезвоним.'
    send(user_id,
         f'Ваш регулярный покос (раз в 2 недели):\n📍 {sub["address"]}{when}',
         [[{'type': 'callback', 'text': '❌ Отменить регулярный покос',
            'payload': f'sub_cancel:{sub["id"]}'}]])


def cancel_sub(user_id, sub_id):
    db = db_conn()
    row = db.execute('SELECT * FROM subscriptions WHERE id=? AND user_id=?',
                     (sub_id, user_id)).fetchone()
    if row and row['status'] in ('pending', 'active'):
        db.execute("UPDATE subscriptions SET status='cancelled' WHERE id=?", (sub_id,))
        db.commit()
        tg_notify(f'❌ Клиент отменил регулярный покос #{sub_id}\n'
                  f'👤 {esc(row["name"] or "")}\n☎️ <code>{esc(row["phone"] or "")}</code>\n'
                  f'📍 {esc(row["address"] or "")}')
        send(user_id, 'Регулярный покос отменён. Понадобится снова — кнопки ниже.',
             menu_for(user_id))
    db.close()


# ---------------- updates ----------------

def contact_phone(message):
    for att in (message.get('body') or {}).get('attachments') or []:
        if att.get('type') == 'contact':
            payload = att.get('payload') or {}
            vcf = payload.get('vcf_info') or ''
            m = re.search(r'TEL[^:]*:([+\d][\d\-\s()]{5,})', vcf)
            if m:
                return m.group(1).strip()
            info = payload.get('max_info') or payload.get('tam_info') or {}
            if isinstance(info, dict) and info.get('phone'):
                return str(info['phone'])
    return None


def sender_of(update):
    # callback.user раньше message.sender: в message_callback поле message —
    # это сообщение С КНОПКАМИ, его отправитель — сам бот, а не клиент
    user = (update.get('user')
            or (update.get('callback') or {}).get('user')
            or (update.get('message') or {}).get('sender')
            or {})
    name = user.get('name') or ' '.join(
        x for x in [user.get('first_name'), user.get('last_name')] if x) or 'Клиент'
    return user.get('user_id'), name, user.get('username')


def handle_update(u):
    t = u.get('update_type')
    user_id, name, username = sender_of(u)
    print(f'update: {t} from {user_id} ({name})')
    if not user_id or user_id == BOT_ID:
        return
    if t == 'bot_started':
        upsert_client(user_id, name=name)
        send(user_id, GREETING, menu_for(user_id))
    elif t == 'message_callback':
        cb = u.get('callback') or {}
        payload = cb.get('payload') or ''
        try:
            api('POST', '/answers', {'callback_id': cb.get('callback_id')},
                {'notification': 'Ок'})
        except Exception as e:
            print(f'answer callback failed: {e}', file=sys.stderr)
        if payload in FLOWS:
            start_flow(user_id, name, payload)
        elif payload.startswith('addr:'):
            st = state.get(user_id)
            if not st or st.get('step') != 'pick':
                # нажали адрес на старом сообщении — считаем это новым заказом покоса
                state[user_id] = {'flow': 'order', 'step': 'pick', 'name': name}
            db = db_conn()
            row = db.execute('SELECT address FROM max_addresses WHERE id=? AND user_id=?',
                             (int(payload.split(':')[1]), user_id)).fetchone()
            db.close()
            if row:
                address_chosen(user_id, row['address'])
            else:
                state.pop(user_id, None)
                send(user_id, 'Этот адрес не нашёл. Начнём заново:', menu_for(user_id))
        elif payload == 'addr_new':
            st = state.get(user_id)
            if st:
                st['step'] = 'address'
                send(user_id, 'Напишите адрес участка: село, улица, дом.')
        elif payload == 'sub_info':
            sub = get_subscription(user_id)
            if sub:
                show_sub_info(user_id, sub)
            else:
                send(user_id, 'Активного регулярного покоса нет.', menu_for(user_id))
        elif payload.startswith('sub_cancel:'):
            cancel_sub(user_id, int(payload.split(':')[1]))
    elif t == 'message_created':
        msg = u.get('message') or {}
        text = ((msg.get('body') or {}).get('text') or '').strip()
        low = text.lower().lstrip('/')
        if low in ('start', 'начать', 'меню', 'menu', 'привет', 'здравствуйте'):
            state.pop(user_id, None)
            upsert_client(user_id, name=name)
            send(user_id, GREETING, menu_for(user_id))
            return
        if low in ('отмена', 'cancel', 'стоп', 'stop'):
            state.pop(user_id, None)
            send(user_id, 'Хорошо, отменил. Выберите, что нужно:', menu_for(user_id))
            return
        st = state.get(user_id)
        # брошенный диалог протухает через час: старый текст не считаем адресом/телефоном
        if st and time.time() - st.get('ts', 0) > 3600:
            state.pop(user_id, None)
            st = None
        if st:
            st['ts'] = time.time()
        if st and st['step'] in ('address', 'pick'):
            if not text:
                send(user_id, 'Напишите адрес текстом, пожалуйста.')
                return
            address_chosen(user_id, text)
        elif st and st['step'] == 'phone':
            phone = contact_phone(msg) or text
            if sum(c.isdigit() for c in phone) < 6:
                send(user_id, 'Не похоже на номер телефона. Напишите цифрами, '
                              'например: +7 900 123-45-67.')
                return
            finalize(user_id, st.get('name') or name, phone[:30], username)
        elif text:
            upsert_client(user_id, name=name)
            now = time.time()
            day_hits = [x for x in _forwarded.get(user_id, []) if now - x < 86400]
            hour_hits = [x for x in day_hits if now - x < 3600]
            if len(hour_hits) >= 3 or len(day_hits) >= 10:
                _forwarded[user_id] = day_hits
                # предупреждаем о лимите один раз, дальше молчим — иначе
                # спамер получает бесконечный пинг-понг с ботом
                if not _limit_notified.get(user_id) or now - _limit_notified[user_id] > 3600:
                    _limit_notified[user_id] = now
                    send(user_id, 'Ваши сообщения получили — ответим в ближайшее время.')
                print(f'forward limit for {user_id}, message dropped: {text[:100]}')
                return
            day_hits.append(now)
            _forwarded[user_id] = day_hits
            client = get_client(user_id)
            phone_note = ''
            if client and client['phone']:
                phone_note = f'\n☎️ <code>{esc(client["phone"])}</code>'
            print(f'max direct message from {name} ({user_id}): {text[:200]}')
            tg_notify(f'💬 Сообщение из MAX\n{client_line(name, user_id, username)}'
                      f'{phone_note}\n\n{esc(text[:1000])}')
            send(user_id, 'Сообщение передано — ответим здесь или по телефону.\n\n'
                          'А быстрее всего — оставить заявку кнопкой:', menu_for(user_id))


# ---------------- reminders ----------------

def reminder_tick():
    now = datetime.now(TZ)
    today = now.date()
    tomorrow = (today + timedelta(days=1)).isoformat()
    db = db_conn()
    # просроченные даты двигаем вперёд на интервал
    for sub in db.execute("SELECT * FROM subscriptions WHERE status='active' AND next_date < ?",
                          (today.isoformat(),)).fetchall():
        d = datetime.strptime(sub['next_date'], '%Y-%m-%d').date()
        while d < today:
            d += timedelta(days=sub['interval_days'])
        db.execute('UPDATE subscriptions SET next_date=? WHERE id=?', (d.isoformat(), sub['id']))
    db.commit()
    if now.hour >= REMIND_HOUR:
        subs = db.execute("SELECT * FROM subscriptions WHERE status='active' AND next_date=? "
                          'AND (last_reminded IS NULL OR last_reminded != next_date)',
                          (tomorrow,)).fetchall()
        for sub in subs:
            d = datetime.strptime(sub['next_date'], '%Y-%m-%d')
            if sub['user_id']:
                send(sub['user_id'],
                     f'🌱 Напоминаю: завтра ({d.strftime("%d.%m")}) приедем косить!\n'
                     f'📍 {sub["address"]}\n\n'
                     'Всё в силе. Если планы поменялись — просто напишите здесь.')
            tg_notify(f'🔁 Завтра регулярный покос:\n'
                      f'👤 {esc(sub["name"] or "")}, <code>{esc(sub["phone"] or "")}</code>\n'
                      f'📍 {esc(sub["address"] or "")}')
            db.execute('UPDATE subscriptions SET last_reminded=? WHERE id=?',
                       (sub['next_date'], sub['id']))
            db.commit()
    db.close()


def reminder_loop():
    while True:
        try:
            reminder_tick()
        except Exception as e:
            print(f'reminder error: {e}', file=sys.stderr)
        time.sleep(300)


# ---------------- main ----------------

def main():
    global BOT_ID
    if not MAX_TOKEN:
        print('MAX_TOKEN is empty in .env', file=sys.stderr)
        sys.exit(1)
    ensure_schema()
    me = api('GET', '/me')
    BOT_ID = me.get('user_id')
    print(f"max_bot started as {me.get('name')} (@{me.get('username')}), id={BOT_ID}")
    threading.Thread(target=reminder_loop, daemon=True).start()
    marker = None
    while True:
        try:
            params = {'timeout': 30}
            if marker is not None:
                params['marker'] = marker
            resp = api('GET', '/updates', params, timeout=50)
            marker = resp.get('marker', marker)
            for upd in resp.get('updates') or []:
                try:
                    handle_update(upd)
                except Exception as e:
                    print(f'handle_update error: {e} on {json.dumps(upd)[:400]}',
                          file=sys.stderr)
        except Exception as e:
            print(f'poll error: {e}', file=sys.stderr)
            time.sleep(5)


if __name__ == '__main__':
    main()
