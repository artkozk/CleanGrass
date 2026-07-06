import sqlite3
from typing import List, Dict, Optional, Tuple, Any
import logging

class Database:
    def __init__(self, db_name: str):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        logging.basicConfig(level=logging.INFO)

    def _init_db(self):
        with self.conn:
            # --- legacy tables (kept) ---
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    lang TEXT DEFAULT 'ru',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    address TEXT NOT NULL,
                    area REAL NOT NULL,
                    tariff INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    duration TEXT NOT NULL,
                    before_photo TEXT,
                    after_photo TEXT,
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS addresses (
                    address_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    address TEXT NOT NULL,
                    use_count INTEGER DEFAULT 1,
                    last_used TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id),
                    UNIQUE(user_id, address)
                )
            """)
            self.conn.execute('CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)')
            self.conn.execute('CREATE INDEX IF NOT EXISTS idx_addresses_user ON addresses(user_id)')

            # --- NEW tables for client/admin workflow ---
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    tg_id INTEGER PRIMARY KEY,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    tg_id INTEGER PRIMARY KEY,
                    name TEXT,
                    phone TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS sites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_tg_id INTEGER,
                    address TEXT NOT NULL,
                    area_sotki REAL,
                    contact_name TEXT,
                    contact_phone TEXT,
                    created_by TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_service_at TEXT,
                    service_count INTEGER DEFAULT 0
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS service_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id INTEGER NOT NULL,
                    service_at TEXT NOT NULL,
                    area_sotki REAL,
                    tariff INTEGER,
                    duration TEXT,
                    notes TEXT,
                    created_by_admin_tg_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(site_id) REFERENCES sites(id)
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS service_photos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    file_id TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(order_id) REFERENCES service_orders(id)
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_tg_id INTEGER NOT NULL,
                    site_id INTEGER,
                    address TEXT NOT NULL,
                    area_sotki REAL,
                    contacts TEXT,
                    comment TEXT,
                    status TEXT NOT NULL DEFAULT 'NEW',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    handled_by_admin_tg_id INTEGER,
                    linked_order_id INTEGER
                )
            """)
            self.conn.execute('CREATE INDEX IF NOT EXISTS idx_sites_client ON sites(client_tg_id)')
            self.conn.execute('CREATE INDEX IF NOT EXISTS idx_svc_site ON service_orders(site_id)')
            self.conn.execute('CREATE INDEX IF NOT EXISTS idx_req_status ON requests(status)')

            # --- зоны участка ---
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS site_zones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    area_sotki REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(site_id, name),
                    FOREIGN KEY(site_id) REFERENCES sites(id)
                )
            """)
            # --- служебные ключи (дата последнего дайджеста и т.п.) ---
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
        self._migrate()

    def _column_names(self, table: str) -> set:
        return {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}

    def _migrate(self):
        """Только ALTER TABLE ADD COLUMN — существующие данные не трогаем.
        Старые заказы автоматически получают work_type='mow' и dad_share=1."""
        wanted = {
            'service_orders': [
                ("work_type",    "TEXT NOT NULL DEFAULT 'mow'"),
                ("work_name",    "TEXT"),
                ("amount",       "REAL"),
                ("helper_name",  "TEXT"),
                ("helper_pay",   "REAL NOT NULL DEFAULT 0"),
                ("dad_share",    "INTEGER NOT NULL DEFAULT 1"),
                ("zones",        "TEXT"),
                ("duration_min", "INTEGER"),
            ],
            'sites': [
                ("remind_days",         "INTEGER NOT NULL DEFAULT 30"),
                ("remind_snooze_until", "TEXT"),
            ],
        }
        with self.conn:
            for table, cols in wanted.items():
                have = self._column_names(table)
                for name, decl in cols:
                    if name not in have:
                        self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

    # выручка заказа: покос = сотки×тариф, другая работа = фиксированная сумма
    REVENUE_SQL = "CASE WHEN work_type='other' THEN COALESCE(amount,0) ELSE COALESCE(area_sotki,0)*COALESCE(tariff,0) END"

    # ---------------- legacy methods (unchanged) ----------------
    def add_user(self, user_id: int):
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))

    def get_lang(self, user_id: int) -> str:
        row = self.conn.execute("SELECT lang FROM users WHERE user_id=?", (user_id,)).fetchone()
        return row['lang'] if row else 'ru'

    def set_lang(self, user_id: int, lang: str):
        with self.conn:
            self.conn.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))

    def create_order(self, user_id: int, data: Dict) -> int:
        try:
            with self.conn:
                cur = self.conn.execute("""
                    INSERT INTO orders (user_id, address, area, tariff, date, duration, before_photo, after_photo, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, data.get('address'), data.get('area'), data.get('tariff'),
                    data.get('date'), data.get('duration'), data.get('before_photo'),
                    data.get('after_photo'), data.get('notes')
                ))
                self._update_address_stats(user_id, data.get('address'))
                return cur.lastrowid
        except Exception as e:
            logging.error(f"Error creating order: {e}")
            return -1

    def _update_address_stats(self, user_id: int, address: str):
        try:
            with self.conn:
                row = self.conn.execute("SELECT address_id FROM addresses WHERE user_id=? AND address=?", (user_id, address)).fetchone()
                if row:
                    self.conn.execute("UPDATE addresses SET use_count=use_count+1, last_used=CURRENT_TIMESTAMP WHERE address_id=?", (row['address_id'],))
                else:
                    self.conn.execute("INSERT INTO addresses (user_id, address, last_used) VALUES (?, ?, CURRENT_TIMESTAMP)", (user_id, address))
        except Exception as e:
            logging.error(f"Error updating address stats: {e}")

    def get_last_addresses(self, user_id: int, limit:int=5) -> List[Tuple[str,int]]:
        try:
            rows = self.conn.execute("""
                SELECT address, use_count FROM addresses WHERE user_id=? ORDER BY last_used DESC LIMIT ?
            """, (user_id, limit)).fetchall()
            return [(r['address'], r['use_count']) for r in rows]
        except Exception as e:
            logging.error(f"Error getting last addresses: {e}")
            return []

    def get_last_order_for_address(self, user_id:int, address:str) -> Optional[Dict]:
        row = self.conn.execute("""
            SELECT area, tariff FROM orders WHERE user_id=? AND address=? ORDER BY date DESC, created_at DESC LIMIT 1
        """, (user_id, address)).fetchone()
        return dict(row) if row else None

    def get_orders_history(self, user_id:int, period:str='all', limit:int=50) -> List[Dict]:
        cond = {
            'week': "date >= date('now','-7 days')",
            'month': "date >= date('now','-1 month')",
            'year': "date >= date('now','-1 year')",
            'all': "1=1",
        }.get(period, "1=1")
        rows = self.conn.execute(f"""
            SELECT order_id, address, area, tariff, date, duration, notes, before_photo, after_photo, (area*tariff) AS total_price
            FROM orders WHERE user_id=? AND {cond} ORDER BY date DESC, created_at DESC LIMIT ?
        """, (user_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_orders_history_range(self, user_id:int, dfrom:str, dto:str, limit:int=200) -> List[Dict]:
        rows = self.conn.execute("""
            SELECT order_id, address, area, tariff, date, duration, notes, before_photo, after_photo, (area*tariff) AS total_price
            FROM orders WHERE user_id=? AND date BETWEEN ? AND ? ORDER BY date ASC, created_at ASC LIMIT ?
        """, (user_id, dfrom, dto, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_statistics(self, user_id:int, period:str='all') -> Dict[str, float]:
        cond = {
            'week': "date >= date('now','-7 days')",
            'month': "date >= date('now','-1 month')",
            'year': "date >= date('now','-1 year')",
            'all': "1=1",
        }.get(period, "1=1")
        row = self.conn.execute(f"""
            SELECT COUNT(*) AS total_orders, SUM(area) AS total_area, SUM(area*tariff) AS total_income,
                   AVG(area*tariff) AS avg_order_price, AVG(area) AS avg_area, AVG(tariff) AS avg_tariff
            FROM orders WHERE user_id=? AND {cond}
        """, (user_id,)).fetchone()
        return {
            'total_orders': row['total_orders'] or 0,
            'total_area': row['total_area'] or 0,
            'total_income': row['total_income'] or 0,
            'avg_order_price': row['avg_order_price'] or 0,
            'avg_area': row['avg_area'] or 0,
            'avg_tariff': row['avg_tariff'] or 0,
        }

    def get_statistics_advanced(self, user_id:int, dfrom:Optional[str], dto:Optional[str], tmin:Optional[int], tmax:Optional[int], amin:Optional[float], amax:Optional[float]) -> Dict[str,Any]:
        clauses = ["user_id=?"]; params=[user_id]
        if dfrom and dto: clauses.append("date BETWEEN ? AND ?"); params+= [dfrom, dto]
        if tmin is not None: clauses.append("tariff >= ?"); params.append(tmin)
        if tmax is not None: clauses.append("tariff <= ?"); params.append(tmax)
        if amin is not None: clauses.append("area >= ?"); params.append(amin)
        if amax is not None: clauses.append("area <= ?"); params.append(amax)
        where = " AND ".join(clauses)
        row = self.conn.execute(f"""
            SELECT COUNT(*) AS total_orders, SUM(area) AS total_area, SUM(area*tariff) AS total_income,
                   AVG(area*tariff) AS avg_order_price, AVG(area) AS avg_area, AVG(tariff) AS avg_tariff
            FROM orders WHERE {where}
        """, tuple(params)).fetchone()
        items = self.conn.execute(f"""
            SELECT order_id, address, area, tariff, date, duration, (area*tariff) AS total_price
            FROM orders WHERE {where} ORDER BY date ASC LIMIT 200
        """, tuple(params)).fetchall()
        return {
            'stats': {
                'total_orders': row['total_orders'] or 0,
                'total_area': row['total_area'] or 0,
                'total_income': row['total_income'] or 0,
                'avg_order_price': row['avg_order_price'] or 0,
                'avg_area': row['avg_area'] or 0,
                'avg_tariff': row['avg_tariff'] or 0
            },
            'items': [dict(r) for r in items]
        }

    def update_order_fields(self, user_id:int, order_id:int, fields:Dict) -> bool:
        if not fields: return False
        allowed = ['address','area','tariff','date','duration','notes','before_photo','after_photo']
        sets=[]; params=[]
        for k,v in fields.items():
            if k in allowed:
                sets.append(f"{k}=?"); params.append(v)
        if not sets: return False
        params += [order_id, user_id]
        with self.conn:
            cur = self.conn.execute(f"UPDATE orders SET {', '.join(sets)} WHERE order_id=? AND user_id=?", tuple(params))
            return cur.rowcount > 0

    def delete_order(self, user_id:int, order_id:int) -> bool:
        with self.conn:
            cur = self.conn.execute("DELETE FROM orders WHERE order_id=? AND user_id=?", (order_id, user_id))
            return cur.rowcount > 0

    # ---------------- NEW: admin/client workflow ----------------

    # Admins
    def add_admin(self, tg_id:int):
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO admins(tg_id) VALUES (?)", (tg_id,))

    def is_admin(self, tg_id:int, seeded_admins:List[int]=None) -> bool:
        if seeded_admins and tg_id in seeded_admins:
            return True
        row = self.conn.execute("SELECT tg_id FROM admins WHERE tg_id=?", (tg_id,)).fetchone()
        return bool(row)

    def count_new_requests(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS c FROM requests WHERE status='NEW'").fetchone()
        return int(row['c'] or 0)

    # Clients
    def upsert_client(self, tg_id:int, name:str=None, phone:str=None):
        with self.conn:
            row = self.conn.execute("SELECT tg_id FROM clients WHERE tg_id=?", (tg_id,)).fetchone()
            if row:
                if name is not None:
                    self.conn.execute("UPDATE clients SET name=? WHERE tg_id=?", (name, tg_id))
                if phone is not None:
                    self.conn.execute("UPDATE clients SET phone=? WHERE tg_id=?", (phone, tg_id))
            else:
                self.conn.execute("INSERT INTO clients(tg_id,name,phone) VALUES (?,?,?)", (tg_id, name, phone))

    def get_client(self, tg_id:int) -> Optional[Dict]:
        row = self.conn.execute("SELECT tg_id,name,phone FROM clients WHERE tg_id=?", (tg_id,)).fetchone()
        return dict(row) if row else None

    # Sites
    def create_site(self, client_tg_id:Optional[int], address:str, area_sotki:Optional[float], contacts:Optional[str],
                    created_by:str='CLIENT', name:Optional[str]=None, phone:Optional[str]=None) -> int:
        if contacts and not (name or phone):
            # naive split: try phone digits
            import re
            digits = re.findall(r'\+?\d[\d\s\-()]{7,}', contacts)
            phone = digits[0].strip() if digits else contacts.strip()
            name = None
        with self.conn:
            cur = self.conn.execute("""
                INSERT INTO sites(client_tg_id,address,area_sotki,contact_name,contact_phone,created_by)
                VALUES(?,?,?,?,?,?)
            """, (client_tg_id, address, area_sotki, name, phone, created_by))
            return cur.lastrowid

    def list_sites_for_client(self, client_tg_id:int) -> List[Dict]:
        rows = self.conn.execute("""
            SELECT id,address,area_sotki,contact_name,contact_phone,last_service_at,service_count
            FROM sites WHERE client_tg_id=? ORDER BY COALESCE(last_service_at, created_at) DESC
        """, (client_tg_id,)).fetchall()
        return [dict(r) for r in rows]

    def search_sites(self, q:str, limit:int=20) -> List[Dict]:
        q = (q or '').strip()
        if not q or q=='-':
            rows = self.conn.execute("""
                SELECT id,address,area_sotki,contact_name,contact_phone,last_service_at,service_count
                FROM sites ORDER BY COALESCE(last_service_at, created_at) DESC LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]
        rows = self.conn.execute("""
            SELECT id,address,area_sotki,contact_name,contact_phone,last_service_at,service_count
            FROM sites WHERE address LIKE ? ORDER BY COALESCE(last_service_at, created_at) DESC LIMIT ?
        """, (f"%{q}%", limit)).fetchall()
        return [dict(r) for r in rows]

    def get_site(self, site_id:int) -> Optional[Dict]:
        row = self.conn.execute("SELECT * FROM sites WHERE id=?", (site_id,)).fetchone()
        return dict(row) if row else None

    def update_site(self, site_id:int, fields:Dict) -> bool:
        allowed={'address','area_sotki','contact_name','contact_phone','client_tg_id'}
        sets=[]; params=[]
        for k,v in fields.items():
            if k in allowed:
                sets.append(f"{k}=?"); params.append(v)
        if not sets:
            return False
        params.append(site_id)
        with self.conn:
            cur=self.conn.execute(f"UPDATE sites SET {', '.join(sets)} WHERE id=?", tuple(params))
            return cur.rowcount>0

    # Service orders
    def create_service_order(self, site_id:int, service_at:str, area_sotki:Optional[float], tariff:Optional[int],
                             duration:Optional[str], notes:Optional[str], admin_tg_id:int, photo_file_ids:List[str],
                             work_type:str='mow', work_name:Optional[str]=None, amount:Optional[float]=None,
                             helper_name:Optional[str]=None, helper_pay:float=0, dad_share:int=1,
                             zones:Optional[str]=None, duration_min:Optional[int]=None) -> int:
        with self.conn:
            cur=self.conn.execute("""
                INSERT INTO service_orders(site_id,service_at,area_sotki,tariff,duration,notes,created_by_admin_tg_id,
                                           work_type,work_name,amount,helper_name,helper_pay,dad_share,zones,duration_min)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (site_id, service_at, area_sotki, tariff, duration, notes, admin_tg_id,
                  work_type, work_name, amount, helper_name, helper_pay, dad_share, zones, duration_min))
            oid=cur.lastrowid
            for fid in photo_file_ids or []:
                self.conn.execute("INSERT INTO service_photos(order_id,file_id) VALUES(?,?)", (oid, fid))
            # счётчик покосов и дата последнего покоса — только для покосов,
            # «другая работа» на них не влияет (в т.ч. на напоминания)
            if work_type != 'other':
                self.conn.execute("""
                    UPDATE sites
                    SET service_count = COALESCE(service_count,0) + 1,
                        last_service_at = MAX(COALESCE(last_service_at,''), ?),
                        remind_snooze_until = NULL
                    WHERE id=?
                """, (service_at, site_id))
            return oid

    def list_service_orders_for_site(self, site_id:int, limit:int=100) -> List[Dict]:
        rows=self.conn.execute("""
            SELECT * FROM service_orders WHERE site_id=? ORDER BY service_at DESC, created_at DESC LIMIT ?
        """, (site_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_service_order(self, order_id:int) -> Optional[Dict]:
        row=self.conn.execute("SELECT * FROM service_orders WHERE id=?", (order_id,)).fetchone()
        return dict(row) if row else None

    def get_service_order_photos(self, order_id:int) -> List[str]:
        rows=self.conn.execute("SELECT file_id FROM service_photos WHERE order_id=? ORDER BY id", (order_id,)).fetchall()
        return [r['file_id'] for r in rows]

    def update_service_order(self, order_id:int, fields:Dict) -> bool:
        allowed={'service_at','area_sotki','tariff','duration','notes',
                 'work_name','amount','helper_name','helper_pay','dad_share','zones','duration_min'}
        sets=[]; params=[]
        for k,v in fields.items():
            if k in allowed:
                sets.append(f"{k}=?"); params.append(v)
        if not sets:
            return False
        params.append(order_id)
        with self.conn:
            cur=self.conn.execute(f"UPDATE service_orders SET {', '.join(sets)} WHERE id=?", tuple(params))
            return cur.rowcount>0

    def delete_service_order(self, order_id:int) -> bool:
        with self.conn:
            self.conn.execute("DELETE FROM service_photos WHERE order_id=?", (order_id,))
            cur=self.conn.execute("DELETE FROM service_orders WHERE id=?", (order_id,))
            return cur.rowcount>0

    def delete_all_orders_for_site(self, site_id:int) -> int:
        with self.conn:
            # count
            row=self.conn.execute("SELECT COUNT(*) AS c FROM service_orders WHERE site_id=?", (site_id,)).fetchone()
            count=int(row['c'] or 0)
            # delete photos then orders
            self.conn.execute("""
                DELETE FROM service_photos
                WHERE order_id IN (SELECT id FROM service_orders WHERE site_id=?)
            """, (site_id,))
            self.conn.execute("DELETE FROM service_orders WHERE site_id=?", (site_id,))
            # reset counters
            self.conn.execute("UPDATE sites SET service_count=0,last_service_at=NULL WHERE id=?", (site_id,))
            return count

    # Requests
    def create_request(self, client_tg_id:int, site_id:Optional[int], address:str, area_sotki:Optional[float], contacts:str, comment:str) -> int:
        with self.conn:
            cur=self.conn.execute("""
                INSERT INTO requests(client_tg_id,site_id,address,area_sotki,contacts,comment,status)
                VALUES(?,?,?,?,?,?, 'NEW')
            """, (client_tg_id, site_id, address, area_sotki, contacts, comment))
            return cur.lastrowid

    def list_requests(self, status:str='NEW', limit:int=50) -> List[Dict]:
        rows=self.conn.execute("""
            SELECT id,client_tg_id,site_id,address,area_sotki,contacts,comment,status,created_at
            FROM requests WHERE status=? ORDER BY created_at DESC LIMIT ?
        """, (status, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_request(self, req_id:int) -> Optional[Dict]:
        row=self.conn.execute("""
            SELECT id,client_tg_id,site_id,address,area_sotki,contacts,comment,status,created_at,handled_by_admin_tg_id,linked_order_id
            FROM requests WHERE id=?
        """, (req_id,)).fetchone()
        return dict(row) if row else None

    def update_request(self, req_id:int, fields:Dict) -> bool:
        allowed={'status','handled_by_admin_tg_id','linked_order_id'}
        sets=[]; params=[]
        for k,v in fields.items():
            if k in allowed:
                sets.append(f"{k}=?"); params.append(v)
        if not sets:
            return False
        params.append(req_id)
        with self.conn:
            cur=self.conn.execute(f"UPDATE requests SET {', '.join(sets)} WHERE id=?", tuple(params))
            return cur.rowcount>0

    # Admin archive search
    def find_service_orders(self, address_like:Optional[str], date_from:Optional[str], date_to:Optional[str], price_min:Optional[float], price_max:Optional[float], limit:int=50) -> List[Dict]:
        clauses=[]; params=[]
        # join sites to filter by address
        q = """SELECT so.id, so.service_at, so.area_sotki, so.tariff, (COALESCE(so.area_sotki,0)*COALESCE(so.tariff,0)) AS total,
                        s.id AS site_id, s.address
                 FROM service_orders so
                 JOIN sites s ON s.id = so.site_id
              """
        if address_like and address_like!='-':
            clauses.append("s.address LIKE ?"); params.append(f"%{address_like}%")
        if date_from and date_from!='-':
            clauses.append("so.service_at >= ?"); params.append(date_from)
        if date_to and date_to!='-':
            clauses.append("so.service_at <= ?"); params.append(date_to)
        if price_min is not None:
            clauses.append("(COALESCE(so.area_sotki,0)*COALESCE(so.tariff,0)) >= ?"); params.append(price_min)
        if price_max is not None:
            clauses.append("(COALESCE(so.area_sotki,0)*COALESCE(so.tariff,0)) <= ?"); params.append(price_max)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows=self.conn.execute(q + " " + where + " ORDER BY so.service_at DESC, so.created_at DESC LIMIT ?", tuple(params+[limit])).fetchall()
        return [dict(r) for r in rows]

    def stats_all_service_orders(self) -> Dict[str, float]:
        row=self.conn.execute(f"""
            SELECT COUNT(*) AS total_orders,
                   SUM(area_sotki) AS total_area,
                   SUM({self.REVENUE_SQL}) AS total_income,
                   AVG({self.REVENUE_SQL}) AS avg_order_price
            FROM service_orders
        """).fetchone()
        return {
            'total_orders': row['total_orders'] or 0,
            'total_area': row['total_area'] or 0,
            'total_income': row['total_income'] or 0,
            'avg_order_price': row['avg_order_price'] or 0,
        }

    # ---------------- NEW: зоны участка ----------------
    def list_zones(self, site_id:int) -> List[Dict]:
        rows=self.conn.execute(
            "SELECT id,site_id,name,area_sotki FROM site_zones WHERE site_id=? ORDER BY id", (site_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_zone(self, zone_id:int) -> Optional[Dict]:
        row=self.conn.execute("SELECT id,site_id,name,area_sotki FROM site_zones WHERE id=?", (zone_id,)).fetchone()
        return dict(row) if row else None

    def add_zone(self, site_id:int, name:str, area_sotki:float) -> int:
        with self.conn:
            cur=self.conn.execute(
                "INSERT OR IGNORE INTO site_zones(site_id,name,area_sotki) VALUES(?,?,?)",
                (site_id, name.strip(), area_sotki))
            if cur.rowcount:
                return cur.lastrowid
            row=self.conn.execute(
                "SELECT id FROM site_zones WHERE site_id=? AND name=?", (site_id, name.strip())).fetchone()
            return row['id'] if row else 0

    def delete_zone(self, zone_id:int) -> bool:
        with self.conn:
            cur=self.conn.execute("DELETE FROM site_zones WHERE id=?", (zone_id,))
            return cur.rowcount>0

    # ---------------- NEW: помощники и тарифы (подсказки кнопками) ----------------
    def recent_helper_names(self, limit:int=6) -> List[str]:
        rows=self.conn.execute("""
            SELECT helper_name FROM service_orders
            WHERE helper_name IS NOT NULL AND helper_name != ''
            GROUP BY helper_name ORDER BY MAX(id) DESC LIMIT ?
        """, (limit,)).fetchall()
        return [r['helper_name'] for r in rows]

    def recent_tariffs(self, limit:int=5) -> List[int]:
        rows=self.conn.execute("""
            SELECT tariff FROM service_orders
            WHERE tariff IS NOT NULL AND tariff > 0
            GROUP BY tariff ORDER BY MAX(id) DESC LIMIT ?
        """, (limit,)).fetchall()
        return [int(r['tariff']) for r in rows]

    # ---------------- NEW: статистика с деньгами ----------------
    def list_orders_for_period(self, period:str='all') -> List[Dict]:
        cond = {
            'week':  "service_at >= date('now','-7 days')",
            'month': "service_at >= date('now','-1 month')",
            'year':  "service_at >= date('now','-1 year')",
            'all':   "1=1",
        }.get(period, "1=1")
        rows=self.conn.execute(f"""
            SELECT * FROM service_orders WHERE {cond} ORDER BY service_at ASC, created_at ASC
        """).fetchall()
        return [dict(r) for r in rows]

    # ---------------- NEW: напоминания ----------------
    def reminders_due(self, limit:int=50) -> List[Dict]:
        """Участки, где с последнего ПОКОСА прошло больше remind_days и напоминание не отложено."""
        rows=self.conn.execute("""
            SELECT s.id, s.address, s.contact_name, s.contact_phone, s.remind_days,
                   lm.last_mow,
                   CAST(julianday('now') - julianday(lm.last_mow) AS INTEGER) AS days_ago
            FROM sites s
            JOIN (SELECT site_id, MAX(service_at) AS last_mow
                  FROM service_orders WHERE work_type != 'other' GROUP BY site_id) lm
              ON lm.site_id = s.id
            WHERE julianday('now') - julianday(lm.last_mow) >= COALESCE(s.remind_days, 30)
              AND (s.remind_snooze_until IS NULL OR s.remind_snooze_until <= date('now'))
            ORDER BY days_ago DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def count_reminders_due(self) -> int:
        return len(self.reminders_due(limit=500))

    def snooze_site(self, site_id:int, days:int) -> bool:
        with self.conn:
            cur=self.conn.execute(
                "UPDATE sites SET remind_snooze_until = date('now', ?) WHERE id=?",
                (f'+{int(days)} days', site_id))
            return cur.rowcount>0

    def set_remind_days(self, site_id:int, days:int) -> bool:
        with self.conn:
            cur=self.conn.execute("UPDATE sites SET remind_days=? WHERE id=?", (int(days), site_id))
            return cur.rowcount>0

    # ---------------- NEW: meta и бэкап ----------------
    def meta_get(self, key:str) -> Optional[str]:
        row=self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row['value'] if row else None

    def meta_set(self, key:str, value:str):
        with self.conn:
            self.conn.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value))

    def backup_to(self, path:str):
        """Консистентная копия базы через sqlite backup API (безопасно на живой базе)."""
        dst = sqlite3.connect(path)
        try:
            with dst:
                self.conn.backup(dst)
        finally:
            dst.close()
