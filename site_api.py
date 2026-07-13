#!/usr/bin/env python3
"""Приём заявок с сайта pokos48.ru.

POST /api/request  {name, phone, address, regular}
Сохраняет заявку в grass_orders.db (таблица site_requests) и шлёт
уведомление всем админам бота в Telegram. Слушает только 127.0.0.1:8091 —
наружу проксируется через nginx (location /api/).
"""
import hashlib
import json
import os
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, 'grass_orders.db')
HOST, PORT = '127.0.0.1', 8091
MAX_BODY = 4096
RATE_LIMIT = 5          # заявок с одного IP
RATE_WINDOW = 3600      # за час

_rate: dict = {}


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


BOT_TOKEN = load_env().get('BOT_TOKEN', '')


ALLOWED_EVENTS = {'view', 'click_phone', 'click_max', 'click_tg'}
_hit_rate: dict = {}


def ensure_table():
    db = sqlite3.connect(DB_PATH)
    db.execute('''CREATE TABLE IF NOT EXISTS site_hits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event TEXT NOT NULL,
        ref TEXT,
        visitor TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS site_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        address TEXT NOT NULL,
        regular INTEGER NOT NULL DEFAULT 0,
        source TEXT NOT NULL DEFAULT 'site',
        status TEXT NOT NULL DEFAULT 'new',
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    )''')
    db.commit()
    db.close()


def admin_ids():
    try:
        db = sqlite3.connect(DB_PATH)
        ids = [r[0] for r in db.execute('SELECT tg_id FROM admins')]
        db.close()
        return ids
    except Exception as e:
        print(f'admin_ids error: {e}', file=sys.stderr)
        return []


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _notify_admins_blocking(req_id, name, phone, address, regular):
    if not BOT_TOKEN:
        print('BOT_TOKEN is empty, skip notify', file=sys.stderr)
        return
    kind = 'Регулярный (раз в 2 недели)' if regular else 'Разовый'
    text = (f'🌐 Заявка с сайта #{req_id}\n'
            f'🧾 {kind}\n'
            f'👤 {esc(name)}\n'
            f'☎️ <code>{esc(phone)}</code>\n'
            f'📍 {esc(address)}')
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    for chat_id in admin_ids():
        data = urllib.parse.urlencode({'chat_id': chat_id, 'text': text,
                                       'parse_mode': 'HTML'}).encode()
        # Telegram с этого сервера периодически недоступен по несколько
        # секунд — без ретраев карточка молча теряется
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url, data=data, timeout=10) as resp:
                    resp.read()
                break
            except Exception as e:
                print(f'notify {chat_id} attempt {attempt + 1} failed: {e}', file=sys.stderr)
                time.sleep(5 * (attempt + 1))


def notify_admins(req_id, name, phone, address, regular):
    # в фоне: посетитель формы не должен ждать Telegram
    threading.Thread(target=_notify_admins_blocking,
                     args=(req_id, name, phone, address, regular), daemon=True).start()


def rate_ok(ip):
    now = time.time()
    hits = [t for t in _rate.get(ip, []) if now - t < RATE_WINDOW]
    if len(hits) >= RATE_LIMIT:
        _rate[ip] = hits
        return False
    hits.append(now)
    _rate[ip] = hits
    return True


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_hit(self, ip):
        ua = self.headers.get('User-Agent', '')
        if any(b in ua.lower() for b in ('bot', 'crawler', 'spider', 'preview')):
            return self._reply(200, {'ok': True})
        now = time.time()
        hits = [t for t in _hit_rate.get(ip, []) if now - t < 3600]
        if len(hits) >= 120:
            _hit_rate[ip] = hits
            return self._reply(200, {'ok': True})
        hits.append(now)
        _hit_rate[ip] = hits
        length = int(self.headers.get('Content-Length') or 0)
        if not 0 < length <= MAX_BODY:
            return self._reply(400, {'ok': False})
        try:
            data = json.loads(self.rfile.read(length).decode('utf-8'))
        except Exception:
            return self._reply(400, {'ok': False})
        event = str(data.get('event', ''))
        if event not in ALLOWED_EVENTS:
            return self._reply(400, {'ok': False})
        ref = str(data.get('ref', ''))[:200]
        visitor = hashlib.sha1(f'{ip}|{ua}'.encode()).hexdigest()[:16]
        db = sqlite3.connect(DB_PATH)
        db.execute('INSERT INTO site_hits (event, ref, visitor) VALUES (?, ?, ?)',
                   (event, ref, visitor))
        db.commit()
        db.close()
        self._reply(200, {'ok': True})

    def do_POST(self):
        ip = self.headers.get('X-Real-IP') or self.client_address[0]
        path = self.path.rstrip('/')
        if path == '/api/hit':
            return self._handle_hit(ip)
        if path != '/api/request':
            return self._reply(404, {'ok': False, 'error': 'not found'})
        if not rate_ok(ip):
            return self._reply(429, {'ok': False, 'error': 'too many requests'})
        length = int(self.headers.get('Content-Length') or 0)
        if not 0 < length <= MAX_BODY:
            return self._reply(400, {'ok': False, 'error': 'bad length'})
        try:
            data = json.loads(self.rfile.read(length).decode('utf-8'))
        except Exception:
            return self._reply(400, {'ok': False, 'error': 'bad json'})
        name = str(data.get('name', '')).strip()[:100]
        phone = str(data.get('phone', '')).strip()[:30]
        address = str(data.get('address', '')).strip()[:200]
        regular = 1 if data.get('regular') else 0
        # honeypot: скрытое поле, люди его не видят и не заполняют
        if str(data.get('website', '')).strip():
            print(f'honeypot hit from {ip}, dropped', file=sys.stderr)
            return self._reply(200, {'ok': True, 'id': 0})
        if not name or not phone or not address:
            return self._reply(400, {'ok': False, 'error': 'missing fields'})
        if sum(c.isdigit() for c in phone) < 6:
            return self._reply(400, {'ok': False, 'error': 'bad phone'})
        # дедуп только против двойной отправки: тот же телефон И адрес за 2 минуты
        digits = ''.join(c for c in phone if c.isdigit())
        db = sqlite3.connect(DB_PATH)
        recent = db.execute("SELECT id, phone, address FROM site_requests "
                            "WHERE source='site' AND created_at > datetime('now', 'localtime', '-2 minutes')").fetchall()
        for rid, rphone, raddr in recent:
            if (''.join(c for c in str(rphone) if c.isdigit()) == digits
                    and str(raddr).strip().lower() == address.lower()):
                db.close()
                print(f'double submit from {ip} (same as #{rid}), skipped')
                return self._reply(200, {'ok': True, 'id': rid})
        cur = db.execute(
            'INSERT INTO site_requests (name, phone, address, regular) VALUES (?, ?, ?, ?)',
            (name, phone, address, regular))
        req_id = cur.lastrowid
        db.commit()
        db.close()
        print(f'request #{req_id} from {ip}: {name}, {phone}, {address}, regular={regular}')
        notify_admins(req_id, name, phone, address, regular)
        self._reply(200, {'ok': True, 'id': req_id})

    def log_message(self, fmt, *args):
        pass


if __name__ == '__main__':
    ensure_table()
    print(f'site_api listening on {HOST}:{PORT}, db={DB_PATH}')
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
