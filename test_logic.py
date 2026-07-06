"""Быстрые тесты логики: деньги, парсер длительности, миграция базы, зоны, напоминания.
Запуск: python test_logic.py (без pytest, без telebot)."""
import os
import shutil
import tempfile

from money import parse_duration_minutes, fmt_minutes, calc_money, per_hour
from database import Database

failures = []

def check(name, got, want):
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


# ---------- деньги (кейс из ТЗ) ----------
m = calc_money('mow', 5000, 1500, 1)
check('mow.earn', m['earn'], 3500)
check('mow.percent', m['percent'], 525.0)   # 15% от 3500
check('mow.dad', m['dad'], 175.0)           # 5% от 3500
check('mow.net', m['net'], 2975.0)

m = calc_money('other', 1000, 0, 0)         # другая работа без папы: −10%
check('other_no_dad.percent', m['percent'], 100.0)
check('other_no_dad.dad', m['dad'], 0.0)
check('other_no_dad.net', m['net'], 900.0)

m = calc_money('other', 2000, 500, 1)       # другая работа с папой: −15%, папе 5%
check('other_dad.earn', m['earn'], 1500)
check('other_dad.percent', m['percent'], 225.0)
check('other_dad.dad', m['dad'], 75.0)
check('other_dad.net', m['net'], 1275.0)

check('per_hour', per_hour(5000, 150), 2000.0)  # 5000 руб за 2.5 часа
check('per_hour_none', per_hour(5000, None), None)

# ---------- парсер длительности ----------
cases = {
    '2.5': 150, '2,5': 150, '2': 120,
    '2:30': 150, '2ч 30': 150, '2ч 30мин': 150, '2ч': 120,
    '2 40': 160, '45мин': 45,
    '9:30-12:00': 150,          # время работы
    '23:00-1:30': 150,          # через полночь
    '9-12': 180,
    'ерунда': None, '': None, '25:70': None,
}
for text, want in cases.items():
    check(f'dur({text!r})', parse_duration_minutes(text), want)

check('fmt_minutes', fmt_minutes(150), '2ч 30мин')
check('fmt_minutes_h', fmt_minutes(120), '2ч')

# ---------- миграция реальной базы (на копии!) ----------
tmpdir = tempfile.mkdtemp()
try:
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'grass_orders.db')
    dbpath = os.path.join(tmpdir, 'migrated.db')
    if os.path.exists(src):
        shutil.copyfile(src, dbpath)
        import sqlite3
        pre = sqlite3.connect(dbpath)
        old_orders = pre.execute("SELECT COUNT(*) FROM service_orders").fetchone()[0]
        pre.close()
    else:
        old_orders = 0

    db = Database(dbpath)  # __init__ прогоняет миграции

    cols = db._column_names('service_orders')
    for c in ('work_type', 'work_name', 'amount', 'helper_name', 'helper_pay',
              'dad_share', 'zones', 'duration_min'):
        check(f'col service_orders.{c}', c in cols, True)
    scols = db._column_names('sites')
    for c in ('remind_days', 'remind_snooze_until'):
        check(f'col sites.{c}', c in scols, True)

    # старые заказы не потерялись и читаются с дефолтами
    now_orders = db.conn.execute("SELECT COUNT(*) FROM service_orders").fetchone()[0]
    check('orders preserved', now_orders, old_orders)
    if old_orders:
        o = db.conn.execute("SELECT work_type, dad_share, helper_pay FROM service_orders LIMIT 1").fetchone()
        check('old.work_type', o['work_type'], 'mow')
        check('old.dad_share', o['dad_share'], 1)
        check('old.helper_pay', o['helper_pay'], 0)

    # ---------- зоны ----------
    sid = db.create_site(None, 'тестовый адрес, 1', 3.5, None, created_by='ADMIN',
                         name='Иван', phone='+7 900 000-00-00')
    z1 = db.add_zone(sid, 'перед домом', 2.0)
    z2 = db.add_zone(sid, 'за баней', 1.5)
    zdup = db.add_zone(sid, 'перед домом', 2.0)  # дубль → тот же id
    check('zone_dup', zdup, z1)
    zones = db.list_zones(sid)
    check('zones_count', len(zones), 2)
    check('zones_sum', sum(z['area_sotki'] for z in zones), 3.5)

    # ---------- заказ с новыми полями и статистика ----------
    oid = db.create_service_order(
        site_id=sid, service_at='2020-01-01', area_sotki=3.5, tariff=1000,
        duration='2ч 30мин', notes='', admin_tg_id=1, photo_file_ids=[],
        work_type='mow', helper_name='Саша', helper_pay=1500, dad_share=1,
        zones='перед домом, за баней', duration_min=150)
    o = db.get_service_order(oid)
    check('order.zones', o['zones'], 'перед домом, за баней')
    check('order.helper_pay', o['helper_pay'], 1500)
    # выручка заказа: 3.5 сот × 1000 = 3500... возьмём кейс из ТЗ: 5000
    db.update_service_order(oid, {'area_sotki': 5.0})
    o = db.get_service_order(oid)
    money = calc_money(o['work_type'], o['area_sotki'] * o['tariff'], o['helper_pay'], o['dad_share'])
    check('order.money.net', money['net'], 2975.0)

    # другая работа не увеличивает счётчик покосов и не двигает last_service_at
    site_before = db.get_site(sid)
    db.create_service_order(site_id=sid, service_at='2020-06-01', area_sotki=None, tariff=None,
                            duration='1ч', notes='', admin_tg_id=1, photo_file_ids=[],
                            work_type='other', work_name='копка земли', amount=3000,
                            dad_share=0, duration_min=60)
    site_after = db.get_site(sid)
    check('other_no_count', site_after['service_count'], site_before['service_count'])
    check('other_no_last', site_after['last_service_at'], site_before['last_service_at'])

    # ---------- напоминания ----------
    # последний покос 2020-01-01 → просрочен при интервале 30 дней
    due = db.reminders_due()
    check('reminder_due', any(r['id'] == sid for r in due), True)
    db.snooze_site(sid, 7)
    due = db.reminders_due()
    check('reminder_snoozed', any(r['id'] == sid for r in due), False)

    # новый покос сбрасывает отсрочку
    db.create_service_order(site_id=sid, service_at='2020-07-01', area_sotki=1.0, tariff=500,
                            duration='1ч', notes='', admin_tg_id=1, photo_file_ids=[],
                            duration_min=60)
    s = db.get_site(sid)
    check('snooze_reset', s['remind_snooze_until'], None)
    check('mow_counts', s['service_count'], site_before['service_count'] + 1)

    # meta
    db.meta_set('k', 'v1'); db.meta_set('k', 'v2')
    check('meta', db.meta_get('k'), 'v2')

    # бэкап
    bpath = os.path.join(tmpdir, 'backup.db')
    db.backup_to(bpath)
    check('backup_exists', os.path.exists(bpath) and os.path.getsize(bpath) > 0, True)

    # ---------- удаление участка целиком ----------
    check('site_in_recent', any(s['id'] == sid for s in db.list_sites_recent()), True)
    n_orders = db.count_orders_for_site(sid)
    check('site_orders_counted', n_orders >= 3, True)
    db.delete_site(sid)
    check('site_deleted', db.get_site(sid), None)
    check('site_zones_deleted', db.list_zones(sid), [])
    check('site_orders_deleted', db.count_orders_for_site(sid), 0)

    db.conn.close()
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

if failures:
    print("FAILED:")
    for f in failures:
        print(" -", f)
    raise SystemExit(1)
print(f"OK — все проверки пройдены ({'с миграцией реальной базы' if old_orders else 'база из репозитория не найдена'})")
