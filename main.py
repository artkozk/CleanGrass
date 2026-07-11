import logging
import os
import re
import tempfile
import threading
import time
from typing import Dict, Optional, List
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import telebot
from telebot import types
from telebot.custom_filters import StateFilter

from config import DB_NAME, LANG, T, BOT_TOKEN, ADMIN_IDS, ADMIN_PASSWORD, BOT_TZ, DIGEST_HOUR
from database import Database
from money import parse_duration_minutes, fmt_minutes, calc_money, per_hour
from states import (
    OrderStates, DeleteStates, HistoryRangeStates, StatsFilterStates, EditOrderStates,
    AdminRegStates, ClientRequestStates, AdminOrderStates, AdminDeleteAllStates,
    AdminFindStates, AdminEditSiteStates, AdminEditServiceOrderStates, AdminRemindStates,
    AdminSitesStates, AdminZoneManageStates
)
from keyboards import (
    main_menu, cancel_kb, tariffs_kb, addresses_kb, confirm_kb, period_kb,
    order_actions_kb, delete_confirm_kb, stats_filters_kb, edit_order_kb, settings_kb,
    client_start_kb, client_site_nav_kb, client_contacts_reply_kb,
    admin_menu_kb, admin_more_kb, admin_requests_list_kb, admin_request_actions_kb, admin_archive_kb,
    admin_site_actions_kb, admin_sites_kb, admin_orders_list_kb, admin_order_actions_kb,
    admin_edit_site_kb, admin_edit_order_kb, admin_inline_done_kb,
    work_type_kb, zones_kb, tariff_quick_kb, date_quick_kb, duration_quick_kb, paid_quick_kb,
    helper_yn_kb, helper_names_kb, dad_share_kb, skip_kb, step_nav_kb, prompt_cancel_kb,
    stats_period_kb, remind_actions_kb,
    site_pick_kb, sites_browse_kb, search_results_kb, zones_manage_kb, confirm_action_kb
)

logging.basicConfig(level=logging.INFO, filename='bot.log', format='%(asctime)s %(levelname)s %(message)s')

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is empty. Set env BOT_TOKEN in your .env or environment.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')
bot.add_custom_filter(StateFilter(bot))

db = Database(DB_NAME)

try:
    TZ = ZoneInfo(BOT_TZ)
except Exception:
    TZ = timezone(timedelta(hours=3))  # нет базы зон — считаем по Москве

# temp storage for flows
temp: Dict[int, Dict] = {}

# ---------------- utils ----------------

def get_lang(uid:int)->str:
    try:
        return db.get_lang(uid) or 'ru'
    except Exception:
        return 'ru'

def is_admin(uid:int)->bool:
    return db.is_admin(uid, seeded_admins=ADMIN_IDS)

def admin_ids_all()->List[int]:
    rows = db.conn.execute("SELECT tg_id FROM admins").fetchall()
    ids = {int(r["tg_id"]) for r in rows}
    ids.update(ADMIN_IDS)
    return sorted(ids)

def fmt_area(a: Optional[float]) -> str:
    if a is None:
        return "—"
    return f"{float(a):.2f}".rstrip('0').rstrip('.')

def fmt_price(v: Optional[float]) -> str:
    if v is None:
        v = 0
    return "{:,.0f}".format(float(v)).replace(",", " ")

def fmt_date_display(s: Optional[str]) -> str:
    if not s:
        return '—'
    try:
        return datetime.strptime(s, '%Y-%m-%d').strftime('%d.%m.%Y')
    except Exception:
        return s

def parse_duration(text: str) -> Optional[str]:
    text = text.strip().lower()
    text = re.sub(r'[^\dчhмmмин:., ]', '', text)
    try:
        if ',' in text or '.' in text:
            hours = float(text.replace(',', '.'))
            total = int(round(hours * 60))
            return f"{total//60}ч {total%60}мин"
        if 'ч' in text or 'h' in text:
            parts = re.split('[чh]', text, maxsplit=1)
            h = int(parts[0].strip() or '0'); m = 0
            if len(parts) > 1:
                mtxt = parts[1].replace('мин','').replace('m','').strip()
                if mtxt: m = int(mtxt)
            return f"{h}ч {m}мин"
        if ':' in text:
            h, m = text.split(':')[:2]
            return f"{int(h)}ч {int(m)}мин"
        if ' ' in text:
            p = text.split()
            if len(p)>=2: return f"{int(p[0])}ч {int(p[1])}мин"
        h = int(text)
        return f"{h}ч"
    except Exception:
        return None

def parse_date(s: str) -> Optional[datetime]:
    s = s.strip().lower()
    if s == '-':
        return None
    if re.fullmatch(r'\d{6}', s):
        try:
            d=int(s[:2]); m=int(s[2:4]); y=int(s[4:])
            y += (2000 if y<50 else 1900) if y<100 else 0
            return datetime(y,m,d)
        except Exception:
            pass
    fmts = ['%d.%m.%Y','%d/%m/%Y','%d-%m-%Y','%d.%m.%y','%d/%m/%y','%d-%m-%y','%Y-%m-%d','%Y/%m/%d','%Y.%m.%d','%d%m%Y','%d%m%y','%Y%m%d','%d.%m','%d/%m','%d-%m']
    for f in fmts:
        try:
            dt = datetime.strptime(s, f)
            if '%Y' not in f and '%y' not in f:
                dt = dt.replace(year=datetime.now().year)
            return dt
        except Exception:
            continue
    nums = re.findall(r'\d+', s)
    if len(nums)>=2:
        try:
            d=int(nums[0]); m=int(nums[1]); y=datetime.now().year
            if len(nums)>=3:
                y=int(nums[2]); y += (2000 if y<50 else 1900) if y<100 else 0
            if m>12 and d<=12: d,m=m,d
            return datetime(y,m,d)
        except Exception:
            pass
    return None

def safe_answer(call: types.CallbackQuery):
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

def show_client_start(chat_id:int, uid:int):
    lang = get_lang(uid)
    db.add_user(uid)
    db.upsert_client(uid, name=(bot.get_chat(uid).first_name if uid else None))
    sites = db.list_sites_for_client(uid)
    name = (bot.get_chat(uid).first_name if uid else "друг")
    bot.send_message(chat_id, T(lang,'client_start', name=name), reply_markup=client_start_kb(sites, T, lang))

def show_admin_menu(chat_id:int, uid:int):
    lang=get_lang(uid)
    bot.send_message(chat_id, T(lang,'admin_menu'),
                     reply_markup=admin_menu_kb(db.count_new_requests(), T, lang,
                                                remind_count=db.count_reminders_due()))

def order_calc_revenue(o: Dict) -> float:
    """Расчётная выручка: сотки×тариф для покоса, фикс. сумма для другой работы."""
    if (o.get('work_type') or 'mow') == 'other':
        return float(o.get('amount') or 0)
    return float(o.get('area_sotki') or 0) * float(o.get('tariff') or 0)

def order_revenue(o: Dict) -> float:
    """Фактическая выручка: сколько заплатили; без этого — по расчёту."""
    paid = o.get('paid_amount')
    if paid is not None:
        return float(paid)
    return order_calc_revenue(o)

def order_money_lines(o: Dict) -> List[str]:
    """Раскладка денег заказа: выручка → помощнику → заработок → проценты (папе) → чистыми, руб/час."""
    m = calc_money(o.get('work_type') or 'mow', order_revenue(o),
                   o.get('helper_pay') or 0, 1 if (o.get('dad_share') is None) else int(o.get('dad_share')))
    calc = order_calc_revenue(o)
    paid = o.get('paid_amount')
    if paid is not None and round(float(paid), 2) != round(calc, 2):
        diff = float(paid) - calc
        sign = '+' if diff > 0 else '−'
        lines = [f"🧮 По расчёту: {fmt_price(calc)} руб",
                 f"💰 Заплатили: <b>{fmt_price(paid)}</b> руб ({sign}{fmt_price(abs(diff))})"]
    else:
        lines = [f"💰 Выручка: <b>{fmt_price(m['revenue'])}</b> руб"]
    if m['helper_pay']:
        who = f" ({o.get('helper_name')})" if o.get('helper_name') else ""
        lines.append(f"🤝 Помощнику{who}: −{fmt_price(m['helper_pay'])} руб")
        lines.append(f"💼 Мой заработок: {fmt_price(m['earn'])} руб")
    dad_note = f" (папе {fmt_price(m['dad'])})" if m['dad'] else ""
    lines.append(f"📉 Проценты {int(m['pct']*100)}%: −{fmt_price(m['percent'])} руб{dad_note}")
    lines.append(f"✅ Чистыми: <b>{fmt_price(m['net'])}</b> руб")
    ph = per_hour(m['revenue'], o.get('duration_min'))
    if ph is not None:
        lines.append(f"⚡ Доход в час: {fmt_price(ph)} руб/ч")
    return lines

def order_card_text(o: Dict, site: Optional[Dict]) -> str:
    is_other = (o.get('work_type') or 'mow') == 'other'
    head = f"🔨 Заказ #{o['id']} — {o.get('work_name') or 'другая работа'}" if is_other else f"🧾 Заказ #{o['id']} — покос"
    lines = [head, f"📍 {site['address'] if site else '—'}"]
    if not is_other:
        if o.get('zones'):
            lines.append(f"🌱 Зоны: {o['zones']}")
        lines.append(f"📏 {fmt_area(o.get('area_sotki'))} сот × {o.get('tariff') or 0} руб/сот")
    lines.append(f"📅 {fmt_date_display(o.get('service_at'))}   ⏳ {o.get('duration') or fmt_minutes(o.get('duration_min'))}")
    lines += order_money_lines(o)
    if o.get('notes'):
        lines.append(f"📝 {o['notes']}")
    return "\n".join(lines)

# ---------------- /start ----------------
@bot.message_handler(commands=['start'])
def start(message: types.Message):
    uid = message.from_user.id
    db.add_user(uid)
    lang = get_lang(uid)
    # always show client start; admins additionally can use /adminreg
    show_client_start(message.chat.id, uid)
    if is_admin(uid):
        show_admin_menu(message.chat.id, uid)

# /cancel и «отмена» — выйти из любого диалога (зарегистрирован раньше state-обработчиков)
@bot.message_handler(commands=['cancel'])
@bot.message_handler(func=lambda m: (m.text or '').strip().lower() in ('отмена','отменить','cancel'))
def cancel_command(message: types.Message):
    uid=message.from_user.id
    temp.pop(uid, None)
    bot.delete_state(uid, message.chat.id)
    if is_admin(uid):
        show_admin_menu(message.chat.id, uid)
    else:
        show_client_start(message.chat.id, uid)

# ---------------- settings (shared) ----------------
@bot.callback_query_handler(func=lambda c: c.data=='settings')
def settings(call: types.CallbackQuery):
    lang = get_lang(call.from_user.id)
    bot.send_message(call.message.chat.id, T(lang,'settings_title'), reply_markup=settings_kb(T,lang))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data in ('set_lang_ru','set_lang_en'))
def set_lang(call: types.CallbackQuery):
    lang = 'ru' if call.data.endswith('ru') else 'en'
    db.set_lang(call.from_user.id, lang)
    if is_admin(call.from_user.id):
        show_admin_menu(call.message.chat.id, call.from_user.id)
    else:
        show_client_start(call.message.chat.id, call.from_user.id)
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data=='noop')
def noop(call: types.CallbackQuery):
    safe_answer(call)

# ---------------- CLIENT FLOW ----------------

@bot.callback_query_handler(func=lambda c: c.data=='cback_sites')
def cback_sites(call: types.CallbackQuery):
    show_client_start(call.message.chat.id, call.from_user.id)
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data=='cnewreq')
def cnewreq(call: types.CallbackQuery):
    uid=call.from_user.id; lang=get_lang(uid)
    temp[uid] = {'flow':'client_request'}
    bot.set_state(uid, ClientRequestStates.address, call.message.chat.id)
    bot.send_message(call.message.chat.id, T(lang,'enter_address'), reply_markup=cancel_kb(T,lang))
    safe_answer(call)

@bot.message_handler(state=ClientRequestStates.address)
def c_enter_address(message: types.Message):
    uid=message.from_user.id; lang=get_lang(uid)
    txt=(message.text or '').strip()
    if txt.lower()==T(lang,'cancel').lower():
        temp.pop(uid,None); bot.delete_state(uid, message.chat.id); show_client_start(message.chat.id, uid); return
    if len(txt) < 3:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    temp.setdefault(uid,{})['address']=txt
    bot.set_state(uid, ClientRequestStates.area, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'enter_area'), reply_markup=cancel_kb(T,lang))

@bot.message_handler(state=ClientRequestStates.area)
def c_enter_area(message: types.Message):
    uid=message.from_user.id; lang=get_lang(uid)
    txt=(message.text or '').strip()
    if txt.lower()==T(lang,'cancel').lower():
        temp.pop(uid,None); bot.delete_state(uid, message.chat.id); show_client_start(message.chat.id, uid); return
    try:
        area=float(txt.replace(',','.'))
        if area<=0: raise ValueError
    except Exception:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    temp.setdefault(uid,{})['area']=area
    bot.set_state(uid, ClientRequestStates.contacts, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'client_enter_contacts'), reply_markup=client_contacts_reply_kb(T,lang))

def _client_comment_kb(lang) -> types.InlineKeyboardMarkup:
    kb=types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("⏭ Пропустить", callback_data="cskip_comment"),
        types.InlineKeyboardButton(T(lang,'cancel'), callback_data="cancel"),
    )
    return kb

@bot.message_handler(content_types=['contact'], state=ClientRequestStates.contacts)
def c_enter_contacts_contact(message: types.Message):
    uid=message.from_user.id; lang=get_lang(uid)
    phone = message.contact.phone_number if message.contact else ''
    temp.setdefault(uid,{})['contacts']=phone
    db.upsert_client(uid, phone=phone)
    bot.set_state(uid, ClientRequestStates.comment, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'client_enter_comment'), reply_markup=_client_comment_kb(lang))

@bot.message_handler(state=ClientRequestStates.contacts)
def c_enter_contacts_text(message: types.Message):
    uid=message.from_user.id; lang=get_lang(uid)
    txt=(message.text or '').strip()
    if txt.lower()==T(lang,'cancel').lower():
        temp.pop(uid,None); bot.delete_state(uid, message.chat.id); show_client_start(message.chat.id, uid); return
    temp.setdefault(uid,{})['contacts']=txt
    bot.set_state(uid, ClientRequestStates.comment, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'client_enter_comment'), reply_markup=_client_comment_kb(lang))

def _client_request_confirm(uid:int, chat_id:int):
    data=temp.get(uid,{})
    summary = "\n".join([
        "🧾 <b>Заявка на покос</b>",
        f"📍 {data.get('address','—')}",
        f"📏 {fmt_area(data.get('area'))} сот.",
        f"☎️ {data.get('contacts','—')}",
        f"💬 {data.get('comment') or '—'}",
    ])
    kb=types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ Отправить", callback_data="csendreq"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="ccancelreq"),
    )
    bot.send_message(chat_id, summary, reply_markup=kb)
    bot.set_state(uid, ClientRequestStates.confirm, chat_id)

@bot.callback_query_handler(func=lambda c: c.data=='cskip_comment', state=ClientRequestStates.comment)
def cskip_comment(call: types.CallbackQuery):
    uid=call.from_user.id
    temp.setdefault(uid,{})['comment']=''
    _client_request_confirm(uid, call.message.chat.id)
    safe_answer(call)

@bot.message_handler(state=ClientRequestStates.comment)
def c_enter_comment(message: types.Message):
    uid=message.from_user.id; lang=get_lang(uid)
    txt=(message.text or '').strip()
    if txt.lower()==T(lang,'cancel').lower():
        temp.pop(uid,None); bot.delete_state(uid, message.chat.id); show_client_start(message.chat.id, uid); return
    temp.setdefault(uid,{})['comment']=txt if txt not in (LANG['ru']['skip'], LANG['en']['skip']) else ''
    _client_request_confirm(uid, message.chat.id)

@bot.callback_query_handler(func=lambda c: c.data in ('csendreq','ccancelreq'), state=ClientRequestStates.confirm)
def c_confirm_req(call: types.CallbackQuery):
    uid=call.from_user.id; lang=get_lang(uid)
    if call.data=='ccancelreq':
        temp.pop(uid,None); bot.delete_state(uid, call.message.chat.id); show_client_start(call.message.chat.id, uid); safe_answer(call); return
    data=temp.get(uid,{})
    site_id = db.create_site(uid, data.get('address'), data.get('area'), data.get('contacts'), created_by='CLIENT')
    rid = db.create_request(uid, site_id, data.get('address'), data.get('area'), data.get('contacts',''), data.get('comment',''))
    # notify admins
    for aid in admin_ids_all():
        try:
            bot.send_message(aid, f"🔔 Новая заявка #{rid}\n📍 {data.get('address')}\n📏 {fmt_area(data.get('area'))} сот.\n☎️ {data.get('contacts','—')}\n💬 {data.get('comment') or '—'}")
        except Exception as e:
            logging.error(f"notify admin {aid}: {e}")
    bot.send_message(call.message.chat.id, T(lang,'client_request_sent'))
    temp.pop(uid,None)
    bot.delete_state(uid, call.message.chat.id)
    show_client_start(call.message.chat.id, uid)
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('csitepick:'))
def csitepick(call: types.CallbackQuery):
    uid=call.from_user.id
    site_id=int(call.data.split(':')[1])
    _show_client_site_card(call.message.chat.id, uid, site_id, 0)
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('csite:'))
def csite_nav(call: types.CallbackQuery):
    uid=call.from_user.id
    _, site_id, idx = call.data.split(':')
    site_id=int(site_id); idx=int(idx)
    _show_client_site_card(call.message.chat.id, uid, site_id, idx)
    safe_answer(call)

def _show_client_site_card(chat_id:int, uid:int, site_id:int, idx:int):
    lang=get_lang(uid)
    site=db.get_site(site_id)
    if not site or site.get('client_tg_id') != uid:
        bot.send_message(chat_id, "❌ Участок не найден."); return
    orders=db.list_service_orders_for_site(site_id, limit=200)
    total=len(orders)
    if total==0:
        text="\n".join([
            f"{T(lang,'client_site_card_title')}",
            f"📍 {site['address']}",
            f"📏 {fmt_area(site.get('area_sotki'))} сот.",
            T(lang,'client_service_count', n=int(site.get('service_count') or 0)),
            T(lang,'client_last_service', date=fmt_date_display(site.get('last_service_at'))),
            "",
            T(lang,'client_history_empty')
        ])
        kb=types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(T(lang,'client_order_again'), callback_data=f"creq:{site_id}"))
        kb.add(types.InlineKeyboardButton(T(lang,'client_back_sites'), callback_data="cback_sites"))
        bot.send_message(chat_id, text, reply_markup=kb)
        return
    idx=max(0,min(idx,total-1))
    o=orders[idx]
    # client hides tariff/duration/price
    text="\n".join([
        f"{T(lang,'client_site_card_title')}",
        f"📍 {site['address']}",
        T(lang,'client_service_count', n=int(site.get('service_count') or 0)),
        T(lang,'client_last_service', date=fmt_date_display(site.get('last_service_at'))),
        "",
        T(lang,'client_order_card', idx=idx+1, total=total, date=fmt_date_display(o.get('service_at'))),
    ])
    photos=db.get_service_order_photos(o['id'])
    kb=client_site_nav_kb(site_id, idx, total, has_photos=bool(photos), t=T, lang=lang)
    bot.send_message(chat_id, text, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith('cphotos:'))
def cphotos(call: types.CallbackQuery):
    uid=call.from_user.id
    _, site_id, idx = call.data.split(':')
    site_id=int(site_id); idx=int(idx)
    site=db.get_site(site_id)
    if not site or site.get('client_tg_id')!=uid:
        safe_answer(call); return
    orders=db.list_service_orders_for_site(site_id, limit=200)
    if not orders:
        safe_answer(call); return
    idx=max(0,min(idx,len(orders)-1))
    order_id=orders[idx]['id']
    photos=db.get_service_order_photos(order_id)
    if not photos:
        bot.send_message(call.message.chat.id, "📭 Фото нет.")
        safe_answer(call); return
    media=[types.InputMediaPhoto(fid) for fid in photos[:10]]
    try:
        bot.send_media_group(call.message.chat.id, media)
    except Exception as e:
        logging.error(e)
        bot.send_message(call.message.chat.id, "❌ Не удалось отправить фото.")
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('creq:'))
def creq_repeat(call: types.CallbackQuery):
    uid=call.from_user.id; lang=get_lang(uid)
    site_id=int(call.data.split(':')[1])
    site=db.get_site(site_id)
    if not site or site.get('client_tg_id')!=uid:
        safe_answer(call); return
    client=db.get_client(uid) or {}
    contacts = client.get('phone') or site.get('contact_phone') or ''
    rid = db.create_request(uid, site_id, site.get('address'), site.get('area_sotki'), contacts, "Повторный заказ")
    for aid in admin_ids_all():
        try:
            bot.send_message(aid, f"🔔 Повторный заказ #{rid}\n📍 {site.get('address')}\n☎️ {contacts or '—'}")
        except Exception as e:
            logging.error(e)
    bot.send_message(call.message.chat.id, T(lang,'client_request_sent'))
    safe_answer(call)

# ---------------- ADMIN FLOW ----------------

@bot.message_handler(commands=['adminreg'])
def adminreg(message: types.Message):
    uid=message.from_user.id; lang=get_lang(uid)
    bot.set_state(uid, AdminRegStates.password, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'admin_enter_password'))

@bot.message_handler(state=AdminRegStates.password)
def adminreg_pwd(message: types.Message):
    uid=message.from_user.id; lang=get_lang(uid)
    if (message.text or '').strip() != str(ADMIN_PASSWORD):
        bot.send_message(message.chat.id, T(lang,'admin_bad_password'))
        bot.delete_state(uid, message.chat.id)
        return
    db.add_admin(uid)
    bot.delete_state(uid, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'admin_ok'))
    show_admin_menu(message.chat.id, uid)

@bot.callback_query_handler(func=lambda c: c.data=='amenu')
def amenu(call: types.CallbackQuery):
    uid=call.from_user.id
    temp.pop(uid, None)
    bot.delete_state(uid, call.message.chat.id)
    show_admin_menu(call.message.chat.id, uid)
    safe_answer(call)

def require_admin_call(call: types.CallbackQuery) -> bool:
    if not is_admin(call.from_user.id):
        lang=get_lang(call.from_user.id)
        bot.send_message(call.message.chat.id, T(lang,'admin_need_reg'))
        safe_answer(call)
        return False
    return True

def require_admin_msg(message: types.Message) -> bool:
    if not is_admin(message.from_user.id):
        lang=get_lang(message.from_user.id)
        bot.send_message(message.chat.id, T(lang,'admin_need_reg'))
        return False
    return True

@bot.callback_query_handler(func=lambda c: c.data=='anotifs')
def anotifs(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    reqs=db.list_requests('NEW', limit=50)
    if not reqs:
        bot.send_message(call.message.chat.id, T(lang,'admin_notifs_empty'),
                         reply_markup=admin_menu_kb(db.count_new_requests(), T, lang,
                                                    remind_count=db.count_reminders_due()))
    else:
        bot.send_message(call.message.chat.id, "🔔 Новые заявки:", reply_markup=admin_requests_list_kb(reqs, T, lang))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('areq:'))
def areq_open(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    req_id=int(call.data.split(':')[1])
    r=db.get_request(req_id)
    if not r:
        bot.send_message(call.message.chat.id, "❌ Заявка не найдена.")
        safe_answer(call); return
    client=f"{r.get('client_tg_id')}"
    text=T(lang,'admin_request_card',
           rid=r['id'], client=client, address=r['address'],
           area=f"{fmt_area(r.get('area_sotki'))} сот.",
           contacts=r.get('contacts') or '—',
           comment=r.get('comment') or '—',
           created=r.get('created_at') or '—')
    bot.send_message(call.message.chat.id, text, reply_markup=admin_request_actions_kb(req_id, T, lang))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('areq_take:'))
def areq_take(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    req_id=int(call.data.split(':')[1])
    db.update_request(req_id, {'status':'IN_PROGRESS','handled_by_admin_tg_id':uid})
    bot.send_message(call.message.chat.id, "✅ Взято в работу.")
    anotifs(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('areq_reject:'))
def areq_reject(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    req_id=int(call.data.split(':')[1])
    db.update_request(req_id, {'status':'REJECTED','handled_by_admin_tg_id':uid})
    bot.send_message(call.message.chat.id, "🗑 Отклонено.")
    anotifs(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('areq_done:'))
def areq_done(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    req_id=int(call.data.split(':')[1])
    r=db.get_request(req_id)
    if not r:
        bot.send_message(call.message.chat.id, "❌ Заявка не найдена.")
        safe_answer(call); return
    site_id = r.get('site_id')
    if not site_id:
        # fallback: create site
        site_id = db.create_site(r.get('client_tg_id'), r.get('address'), r.get('area_sotki'), r.get('contacts'), created_by='ADMIN')
        db.conn.execute("UPDATE requests SET site_id=? WHERE id=?", (site_id, req_id))
        db.conn.commit()
    _start_admin_order(uid, call.message.chat.id, int(site_id), req_id=req_id)
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data=='aneworder')
def aneworder(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    # первый вопрос — что делали (покос/другая работа), участок выбираем после
    temp[uid]={'flow':'admin_order_pick'}
    bot.set_state(uid, AdminOrderStates.work_type, call.message.chat.id)
    bot.send_message(call.message.chat.id, "Что делали?", reply_markup=work_type_kb())
    safe_answer(call)

def _show_site_pick(uid:int, chat_id:int):
    bot.set_state(uid, AdminOrderStates.site_search, chat_id)
    sites=db.list_sites_recent(limit=10)
    text="Выбери участок кнопкой — или просто напиши часть адреса, я найду:" if sites else \
         "Участков пока нет — создай первый:"
    bot.send_message(chat_id, text, reply_markup=site_pick_kb(sites))

@bot.message_handler(state=AdminOrderStates.site_search)
def a_site_search(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id
    q=(message.text or '').strip()
    if q=='-':
        bot.set_state(uid, AdminOrderStates.new_site_address, message.chat.id)
        bot.send_message(message.chat.id, T(get_lang(uid),'admin_new_site_address'))
        return
    sites=db.search_sites(q, limit=20)
    if not sites:
        kb=types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("➕ Создать новый участок", callback_data="aneworder_newsite"))
        kb.add(types.InlineKeyboardButton("↩️ В меню", callback_data="amenu"))
        bot.send_message(message.chat.id, f"По запросу «{q}» ничего не нашёл. Попробуй написать иначе — или создай участок:", reply_markup=kb)
        return
    bot.send_message(message.chat.id, "Нашёл — выбирай:", reply_markup=search_results_kb(sites, "aneworder_site"))

@bot.callback_query_handler(func=lambda c: c.data=='aneworder_newsite')
def aneworder_newsite(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    bot.set_state(uid, AdminOrderStates.new_site_address, call.message.chat.id)
    bot.send_message(call.message.chat.id, T(lang,'admin_new_site_address'), reply_markup=step_nav_kb(back=False))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('aneworder_site:'))
def aneworder_site(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    site_id=int(call.data.split(':')[1])
    _start_admin_order(uid, call.message.chat.id, site_id)
    safe_answer(call)

@bot.message_handler(state=AdminOrderStates.new_site_address)
def a_new_site_address(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    addr=(message.text or '').strip()
    if len(addr)<3:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    temp.setdefault(uid,{})['new_site_address']=addr
    bot.set_state(uid, AdminOrderStates.new_site_area, message.chat.id)
    bot.send_message(message.chat.id, "📏 Площадь участка (сотки). Не знаешь — жми «Пропустить»:", reply_markup=skip_kb("askip_sarea"))

@bot.callback_query_handler(func=lambda c: c.data=='askip_sarea', state=AdminOrderStates.new_site_area)
def a_new_site_area_skip(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    temp.setdefault(uid,{})['new_site_area']=None
    bot.set_state(uid, AdminOrderStates.new_site_name, call.message.chat.id)
    bot.send_message(call.message.chat.id, "👤 Имя клиента (для напоминаний):", reply_markup=skip_kb("askip_sname"))
    safe_answer(call)

@bot.message_handler(state=AdminOrderStates.new_site_area)
def a_new_site_area(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    txt=(message.text or '').strip()
    if txt in ('-','—','?','не знаю','незнаю'):
        area=None
    else:
        try:
            area=float(txt.replace(',','.'))
            if area<=0: raise ValueError
        except Exception:
            bot.send_message(message.chat.id, "❌ Не понял. Введи число (например 2.5) — или жми «Пропустить»:", reply_markup=skip_kb("askip_sarea")); return
    temp.setdefault(uid,{})['new_site_area']=area
    bot.set_state(uid, AdminOrderStates.new_site_name, message.chat.id)
    bot.send_message(message.chat.id, "👤 Имя клиента (для напоминаний):", reply_markup=skip_kb("askip_sname"))

@bot.callback_query_handler(func=lambda c: c.data=='askip_sname', state=AdminOrderStates.new_site_name)
def a_new_site_name_skip(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    temp.setdefault(uid,{})['new_site_name']=None
    bot.set_state(uid, AdminOrderStates.new_site_phone, call.message.chat.id)
    bot.send_message(call.message.chat.id, "☎️ Телефон клиента:", reply_markup=skip_kb("askip_sphone"))
    safe_answer(call)

@bot.message_handler(state=AdminOrderStates.new_site_name)
def a_new_site_name(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id
    temp.setdefault(uid,{})['new_site_name']=(message.text or '').strip() or None
    bot.set_state(uid, AdminOrderStates.new_site_phone, message.chat.id)
    bot.send_message(message.chat.id, "☎️ Телефон клиента:", reply_markup=skip_kb("askip_sphone"))

def _finish_new_site(uid:int, chat_id:int, phone:Optional[str]):
    ctx=temp.get(uid,{})
    site_id=db.create_site(None, ctx.get('new_site_address'), ctx.get('new_site_area'), None,
                           created_by='ADMIN', name=ctx.get('new_site_name'), phone=phone)
    if ctx.get('site_only'):
        # создание из раздела «Участки» — показываем карточку, заказ не начинаем
        temp.pop(uid,None); bot.delete_state(uid, chat_id)
        bot.send_message(chat_id, "✅ Участок создан.")
        asite_show(chat_id, uid, site_id)
        return
    _start_admin_order(uid, chat_id, site_id)

@bot.callback_query_handler(func=lambda c: c.data=='anewsite_only')
def anewsite_only(call: types.CallbackQuery):
    """Новый участок из раздела «Участки» — без создания заказа."""
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    temp[uid]={'flow':'new_site_only','site_only':True}
    bot.set_state(uid, AdminOrderStates.new_site_address, call.message.chat.id)
    bot.send_message(call.message.chat.id, T(lang,'admin_new_site_address'), reply_markup=prompt_cancel_kb("asites"))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data=='askip_sphone', state=AdminOrderStates.new_site_phone)
def a_new_site_phone_skip(call: types.CallbackQuery):
    if not require_admin_call(call): return
    _finish_new_site(call.from_user.id, call.message.chat.id, None)
    safe_answer(call)

@bot.message_handler(state=AdminOrderStates.new_site_phone)
def a_new_site_phone(message: types.Message):
    if not require_admin_msg(message): return
    _finish_new_site(message.from_user.id, message.chat.id, (message.text or '').strip() or None)

# ---------- новый флоу заказа: тип работы → зоны/сумма → тариф → дата → время → помощник → (папа) → заметки → фото ----------

def _start_admin_order(uid:int, chat_id:int, site_id:int, req_id:Optional[int]=None):
    site=db.get_site(site_id)
    if not site:
        bot.send_message(chat_id, "❌ Участок не найден."); return
    # тип работы мог быть выбран ещё до участка (флоу «Создать заказ»)
    prev=temp.get(uid) or {}
    wt=prev.get('work_type') if prev.get('flow')=='admin_order_pick' else None
    temp[uid]={'flow':'admin_order','site_id':site_id,'req_id':req_id,'photos':[],'zone_sel':[]}
    if wt:
        temp[uid]['work_type']=wt
        if wt=='other':
            _ask_work_name(uid, chat_id)
        else:
            _show_zones_screen(uid, chat_id)
    else:
        _ask_work_type(uid, chat_id)

def _ask_work_type(uid:int, chat_id:int):
    site=db.get_site(int(temp.setdefault(uid,{}).get('site_id',0))) or {}
    bot.set_state(uid, AdminOrderStates.work_type, chat_id)
    bot.send_message(chat_id, f"📍 {site.get('address','—')}\nЧто делали?", reply_markup=work_type_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith('awt:'), state=AdminOrderStates.work_type)
def a_work_type(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    wt=call.data.split(':')[1]
    ctx=temp.setdefault(uid,{})
    ctx['work_type']=wt
    if not ctx.get('site_id'):
        # тип выбран до участка — теперь выбираем участок
        _show_site_pick(uid, call.message.chat.id)
    elif wt=='other':
        _ask_work_name(uid, call.message.chat.id)
    else:
        _show_zones_screen(uid, call.message.chat.id)
    safe_answer(call)

def _ask_work_name(uid:int, chat_id:int):
    bot.set_state(uid, AdminOrderStates.work_name, chat_id)
    bot.send_message(chat_id, "🔨 Название работы (например: копка земли):", reply_markup=step_nav_kb())

def _ask_amount(uid:int, chat_id:int):
    bot.set_state(uid, AdminOrderStates.amount, chat_id)
    bot.send_message(chat_id, "💰 Сумма за работу (руб):", reply_markup=step_nav_kb())

@bot.message_handler(state=AdminOrderStates.work_name)
def a_work_name(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    name=(message.text or '').strip()
    if len(name)<2:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    temp.setdefault(uid,{})['work_name']=name
    _ask_amount(uid, message.chat.id)

@bot.message_handler(state=AdminOrderStates.amount)
def a_amount(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    try:
        amount=float((message.text or '').strip().replace(',','.').replace(' ',''))
        if amount<=0: raise ValueError
    except Exception:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    temp.setdefault(uid,{})['amount']=amount
    _ask_date(uid, message.chat.id)

def _zones_ctx(uid:int):
    ctx=temp.setdefault(uid,{})
    zones=db.list_zones(int(ctx.get('site_id',0)))
    sel=set(ctx.get('zone_sel') or [])
    sel_sum=sum(z['area_sotki'] for z in zones if z['id'] in sel)
    return ctx, zones, sel, sel_sum

def _show_zones_screen(uid:int, chat_id:int):
    ctx, zones, sel, sel_sum=_zones_ctx(uid)
    site=db.get_site(int(ctx.get('site_id',0))) or {}
    bot.set_state(uid, AdminOrderStates.zones, chat_id)
    text="🌱 Что косили? Отметь зоны галочками." if zones else \
         "🌱 У участка пока нет зон. Добавь зону, возьми всё целиком или введи площадь вручную."
    bot.send_message(chat_id, text,
                     reply_markup=zones_kb(zones, sel, site.get('area_sotki'), sel_sum))

@bot.callback_query_handler(func=lambda c: c.data.startswith('azt:'), state=AdminOrderStates.zones)
def a_zone_toggle(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    zid=int(call.data.split(':')[1])
    ctx=temp.setdefault(uid,{})
    sel=set(ctx.get('zone_sel') or [])
    sel.symmetric_difference_update({zid})
    ctx['zone_sel']=list(sel)
    _, zones, sel, sel_sum=_zones_ctx(uid)
    site=db.get_site(int(ctx.get('site_id',0))) or {}
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                      reply_markup=zones_kb(zones, sel, site.get('area_sotki'), sel_sum))
    except Exception:
        _show_zones_screen(uid, call.message.chat.id)
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data=='azall', state=AdminOrderStates.zones)
def a_zone_all(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    ctx, zones, _, _=_zones_ctx(uid)
    site=db.get_site(int(ctx.get('site_id',0))) or {}
    area=site.get('area_sotki') or (sum(z['area_sotki'] for z in zones) if zones else None)
    if not area:
        bot.set_state(uid, AdminOrderStates.manual_area, call.message.chat.id)
        bot.send_message(call.message.chat.id, "📏 Площадь участка неизвестна — введи сотки вручную:", reply_markup=step_nav_kb())
        safe_answer(call); return
    ctx['area']=float(area); ctx['zones_label']='всё целиком'
    _ask_tariff(uid, call.message.chat.id)
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data=='aznew', state=AdminOrderStates.zones)
def a_zone_new(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    bot.set_state(uid, AdminOrderStates.zone_new_name, call.message.chat.id)
    bot.send_message(call.message.chat.id, "🌿 Название зоны (например: перед домом):", reply_markup=step_nav_kb())
    safe_answer(call)

@bot.message_handler(state=AdminOrderStates.zone_new_name)
def a_zone_new_name(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    name=(message.text or '').strip()
    if len(name)<2:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    temp.setdefault(uid,{})['zone_new_name']=name
    bot.set_state(uid, AdminOrderStates.zone_new_area, message.chat.id)
    bot.send_message(message.chat.id, "📏 Площадь зоны (сотки):", reply_markup=step_nav_kb())

@bot.message_handler(state=AdminOrderStates.zone_new_area)
def a_zone_new_area(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    try:
        area=float((message.text or '').strip().replace(',','.'))
        if area<=0: raise ValueError
    except Exception:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    ctx=temp.setdefault(uid,{})
    zid=db.add_zone(int(ctx.get('site_id',0)), ctx.pop('zone_new_name','зона'), area)
    # новая зона сразу отмечена
    sel=set(ctx.get('zone_sel') or []); sel.add(zid); ctx['zone_sel']=list(sel)
    _show_zones_screen(uid, message.chat.id)

@bot.callback_query_handler(func=lambda c: c.data=='azman', state=AdminOrderStates.zones)
def a_zone_manual(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    bot.set_state(uid, AdminOrderStates.manual_area, call.message.chat.id)
    bot.send_message(call.message.chat.id, "📏 Введи площадь (сотки, например 2.5):", reply_markup=step_nav_kb())
    safe_answer(call)

@bot.message_handler(state=AdminOrderStates.manual_area)
def a_manual_area(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    try:
        area=float((message.text or '').strip().replace(',','.'))
        if area<=0: raise ValueError
    except Exception:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    ctx=temp.setdefault(uid,{})
    ctx['area']=area; ctx['zones_label']=None
    _ask_tariff(uid, message.chat.id)

@bot.callback_query_handler(func=lambda c: c.data=='azok', state=AdminOrderStates.zones)
def a_zones_ok(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    ctx, zones, sel, sel_sum=_zones_ctx(uid)
    if not sel:
        safe_answer(call); return
    ctx['area']=float(sel_sum)
    ctx['zones_label']=", ".join(z['name'] for z in zones if z['id'] in sel)
    _ask_tariff(uid, call.message.chat.id)
    safe_answer(call)

def _ask_tariff(uid:int, chat_id:int):
    bot.set_state(uid, AdminOrderStates.tariff, chat_id)
    recent=db.recent_tariffs(limit=6)
    bot.send_message(chat_id, "💵 Тариф (руб/сотку) — кнопкой или числом:",
                     reply_markup=tariff_quick_kb(recent))

@bot.callback_query_handler(func=lambda c: c.data.startswith('atrf:'), state=AdminOrderStates.tariff)
def a_tariff_cb(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    temp.setdefault(uid,{})['tariff']=int(call.data.split(':')[1])
    _ask_paid(uid, call.message.chat.id)
    safe_answer(call)

@bot.message_handler(state=AdminOrderStates.tariff)
def a_order_tariff(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    try:
        tariff=int((message.text or '').strip())
        if tariff<=0: raise ValueError
    except Exception:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    temp.setdefault(uid,{})['tariff']=tariff
    _ask_paid(uid, message.chat.id)

def _ask_paid(uid:int, chat_id:int):
    """Сколько заплатили по факту: клиент часто округляет расчётную сумму."""
    ctx=temp.setdefault(uid,{})
    calc=float(ctx.get('area') or 0)*float(ctx.get('tariff') or 0)
    bot.set_state(uid, AdminOrderStates.paid, chat_id)
    bot.send_message(chat_id,
                     f"🧮 По расчёту: <b>{fmt_price(calc)}</b> руб.\n💰 Сколько заплатили в итоге? Кнопкой или напиши сумму:",
                     reply_markup=paid_quick_kb(calc))

def _set_paid(uid:int, chat_id:int, paid:float):
    ctx=temp.setdefault(uid,{})
    calc=round(float(ctx.get('area') or 0)*float(ctx.get('tariff') or 0), 2)
    # ровно по расчёту — не храним, чтобы правки соток/тарифа не расходились с оплатой
    ctx['paid']=None if round(paid,2)==calc else paid
    _ask_date(uid, chat_id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('apaid:'), state=AdminOrderStates.paid)
def a_paid_cb(call: types.CallbackQuery):
    if not require_admin_call(call): return
    _set_paid(call.from_user.id, call.message.chat.id, float(call.data.split(':')[1]))
    safe_answer(call)

@bot.message_handler(state=AdminOrderStates.paid)
def a_paid_text(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    try:
        paid=float((message.text or '').strip().replace(',','.').replace(' ',''))
        if paid<0: raise ValueError
    except Exception:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    _set_paid(uid, message.chat.id, paid)

def _ask_date(uid:int, chat_id:int):
    bot.set_state(uid, AdminOrderStates.date, chat_id)
    bot.send_message(chat_id, "📅 Когда? Кнопкой или датой (15.08.2025, 150825):",
                     reply_markup=date_quick_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith('adate:'), state=AdminOrderStates.date)
def a_date_cb(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    now=datetime.now(TZ)
    d=now if call.data.endswith('today') else now - timedelta(days=1)
    temp.setdefault(uid,{})['date']=d.strftime('%Y-%m-%d')
    _ask_duration(uid, call.message.chat.id)
    safe_answer(call)

@bot.message_handler(state=AdminOrderStates.date)
def a_order_date(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    dt=parse_date((message.text or '').strip())
    if not dt:
        bot.send_message(message.chat.id, T(lang,'err_date')); return
    temp.setdefault(uid,{})['date']=dt.strftime('%Y-%m-%d')
    _ask_duration(uid, message.chat.id)

def _ask_duration(uid:int, chat_id:int):
    bot.set_state(uid, AdminOrderStates.duration, chat_id)
    bot.send_message(chat_id, "⏳ Сколько работали? Кнопкой — или напиши: 2.5, 2ч 30, 2:30, 9:30-12:00",
                     reply_markup=duration_quick_kb())

def _set_duration(uid:int, chat_id:int, mins:int):
    ctx=temp.setdefault(uid,{})
    ctx['duration_min']=mins
    ctx['duration']=fmt_minutes(mins)
    _ask_helper(uid, chat_id)

def _ask_helper(uid:int, chat_id:int):
    bot.set_state(uid, AdminOrderStates.helper, chat_id)
    bot.send_message(chat_id, "🤝 Помощник был?", reply_markup=helper_yn_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith('adur:'), state=AdminOrderStates.duration)
def a_duration_cb(call: types.CallbackQuery):
    if not require_admin_call(call): return
    _set_duration(call.from_user.id, call.message.chat.id, int(call.data.split(':')[1]))
    safe_answer(call)

@bot.message_handler(state=AdminOrderStates.duration)
def a_order_duration(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    mins=parse_duration_minutes((message.text or '').strip())
    if not mins:
        bot.send_message(message.chat.id, T(lang,'err_duration')); return
    _set_duration(uid, message.chat.id, mins)

@bot.callback_query_handler(func=lambda c: c.data.startswith('ahelp:'), state=AdminOrderStates.helper)
def a_helper_yn(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    if call.data.endswith('no'):
        ctx=temp.setdefault(uid,{})
        ctx['helper_name']=None; ctx['helper_pay']=0
        _after_helper(uid, call.message.chat.id)
    else:
        _ask_helper_name(uid, call.message.chat.id)
    safe_answer(call)

def _ask_helper_name(uid:int, chat_id:int):
    names=db.recent_helper_names(limit=8)
    temp.setdefault(uid,{})['helper_names']=names
    bot.set_state(uid, AdminOrderStates.helper_name, chat_id)
    bot.send_message(chat_id, "👤 Кто помогал? Кнопкой или напиши имя:",
                     reply_markup=helper_names_kb(names))

def _ask_helper_pay(uid:int, chat_id:int):
    name=temp.setdefault(uid,{}).get('helper_name') or ''
    bot.set_state(uid, AdminOrderStates.helper_pay, chat_id)
    bot.send_message(chat_id, f"💸 Сколько отдал {name} (руб)?", reply_markup=step_nav_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith('ahname:'), state=AdminOrderStates.helper_name)
def a_helper_name_cb(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    idx=int(call.data.split(':')[1])
    names=temp.setdefault(uid,{}).get('helper_names') or []
    if idx>=len(names):
        safe_answer(call); return
    temp[uid]['helper_name']=names[idx]
    _ask_helper_pay(uid, call.message.chat.id)
    safe_answer(call)

@bot.message_handler(state=AdminOrderStates.helper_name)
def a_helper_name(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    name=(message.text or '').strip()
    if len(name)<2:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    temp.setdefault(uid,{})['helper_name']=name
    _ask_helper_pay(uid, message.chat.id)

@bot.message_handler(state=AdminOrderStates.helper_pay)
def a_helper_pay(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    try:
        pay=float((message.text or '').strip().replace(',','.').replace(' ',''))
        if pay<0: raise ValueError
    except Exception:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    temp.setdefault(uid,{})['helper_pay']=pay
    _after_helper(uid, message.chat.id)

def _after_helper(uid:int, chat_id:int):
    ctx=temp.setdefault(uid,{})
    if ctx.get('work_type')=='other':
        _ask_dad(uid, chat_id)
    else:
        ctx['dad_share']=1
        _ask_notes(uid, chat_id)

def _ask_dad(uid:int, chat_id:int):
    bot.set_state(uid, AdminOrderStates.dad, chat_id)
    bot.send_message(chat_id, "👨 Папина доля с этой работы?", reply_markup=dad_share_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith('adad:'), state=AdminOrderStates.dad)
def a_dad(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    temp.setdefault(uid,{})['dad_share']=1 if call.data.endswith('yes') else 0
    _ask_notes(uid, call.message.chat.id)
    safe_answer(call)

def _ask_notes(uid:int, chat_id:int):
    bot.set_state(uid, AdminOrderStates.notes, chat_id)
    bot.send_message(chat_id, "📝 Заметки:", reply_markup=skip_kb("askip_notes", back=True))

def _ask_photos(uid:int, chat_id:int):
    lang=get_lang(uid)
    temp.setdefault(uid,{}).setdefault('photos',[])
    bot.set_state(uid, AdminOrderStates.photos, chat_id)
    bot.send_message(chat_id, T(lang,'admin_order_photos'),
                     reply_markup=admin_inline_done_kb("aphoto_done", T, lang))

@bot.callback_query_handler(func=lambda c: c.data=='askip_notes', state=AdminOrderStates.notes)
def a_notes_skip(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    ctx=temp.setdefault(uid,{})
    ctx['notes']=''; ctx['photos']=[]
    _ask_photos(uid, call.message.chat.id)
    safe_answer(call)

@bot.message_handler(state=AdminOrderStates.notes)
def a_order_notes(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id
    txt=(message.text or '').strip()
    ctx=temp.setdefault(uid,{})
    ctx['notes']=txt if txt not in (LANG['ru']['skip'], LANG['en']['skip']) else ''
    ctx['photos']=[]
    _ask_photos(uid, message.chat.id)

@bot.message_handler(content_types=['photo'], state=AdminOrderStates.photos)
def a_order_photos(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    fid=message.photo[-1].file_id
    temp.setdefault(uid,{}).setdefault('photos',[]).append(fid)
    bot.send_message(message.chat.id, f"📸 Добавлено фото ({len(temp[uid]['photos'])}).",
                     reply_markup=admin_inline_done_kb("aphoto_done", T, lang))

@bot.message_handler(state=AdminOrderStates.photos)
def a_order_photos_text(message: types.Message):
    """Текст на шаге фото: «готово» завершает шаг, остальное — подсказка."""
    if not require_admin_msg(message): return
    txt=(message.text or '').strip().lower()
    if txt in ('готово','done','ок','ok','всё','все'):
        _order_summary(message.from_user.id, message.chat.id)
        return
    lang=get_lang(message.from_user.id)
    bot.send_message(message.chat.id, "📸 Пришли фото или нажми «Готово».",
                     reply_markup=admin_inline_done_kb("aphoto_done", T, lang))

def _draft_as_order(data: Dict) -> Dict:
    """Черновик из temp в формате заказа — для order_money_lines."""
    return {
        'work_type': data.get('work_type') or 'mow',
        'work_name': data.get('work_name'),
        'amount': data.get('amount'),
        'area_sotki': data.get('area'),
        'tariff': data.get('tariff'),
        'helper_name': data.get('helper_name'),
        'helper_pay': data.get('helper_pay') or 0,
        'dad_share': data.get('dad_share', 1),
        'duration_min': data.get('duration_min'),
        'zones': data.get('zones_label'),
        'paid_amount': data.get('paid'),
    }

@bot.callback_query_handler(func=lambda c: c.data=='aphoto_done', state=AdminOrderStates.photos)
def aphoto_done(call: types.CallbackQuery):
    if not require_admin_call(call): return
    _order_summary(call.from_user.id, call.message.chat.id)
    safe_answer(call)

def _order_summary(uid:int, chat_id:int):
    data=temp.get(uid,{})
    site=db.get_site(data.get('site_id',0))
    if not site:
        bot.send_message(chat_id, "❌ Участок не найден.")
        return
    o=_draft_as_order(data)
    is_other=o['work_type']=='other'
    lines=["📌 <b>Сводка заказа</b>",
           f"{'🔨 ' + (o.get('work_name') or 'Другая работа') if is_other else '🌱 Покос'}",
           f"📍 {site['address']}"]
    if not is_other:
        if o.get('zones'):
            lines.append(f"🌱 Зоны: {o['zones']}")
        lines.append(f"📏 {fmt_area(o.get('area_sotki'))} сот × {o.get('tariff')} руб/сот")
    lines.append(f"📅 {fmt_date_display(data.get('date'))}   ⏳ {data.get('duration')}")
    lines += order_money_lines(o)
    lines.append(f"📸 Фото: {len(data.get('photos') or [])}")
    lines.append(f"📝 {data.get('notes') or '—'}")
    kb=types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ Создать", callback_data="aconfirm_order"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="acancel_order"),
    )
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="aback"))
    bot.send_message(chat_id, "\n".join(lines), reply_markup=kb)
    bot.set_state(uid, AdminOrderStates.confirm, chat_id)

@bot.callback_query_handler(func=lambda c: c.data in ('aconfirm_order','acancel_order'), state=AdminOrderStates.confirm)
def aconfirm_order(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    if call.data=='acancel_order':
        temp.pop(uid,None); bot.delete_state(uid, call.message.chat.id); show_admin_menu(call.message.chat.id, uid); safe_answer(call); return
    data=temp.get(uid,{})
    site_id=int(data.get('site_id',0))
    is_other=(data.get('work_type') or 'mow')=='other'
    oid=db.create_service_order(
        site_id=site_id,
        service_at=data.get('date'),
        area_sotki=None if is_other else data.get('area'),
        tariff=None if is_other else data.get('tariff'),
        duration=data.get('duration'),
        notes=data.get('notes'),
        admin_tg_id=uid,
        photo_file_ids=data.get('photos') or [],
        work_type='other' if is_other else 'mow',
        work_name=data.get('work_name'),
        amount=data.get('amount'),
        helper_name=data.get('helper_name'),
        helper_pay=data.get('helper_pay') or 0,
        dad_share=int(data.get('dad_share', 1)),
        zones=data.get('zones_label'),
        duration_min=data.get('duration_min'),
        paid_amount=data.get('paid'),
    )
    # link to request if present
    req_id=data.get('req_id')
    if req_id:
        db.update_request(int(req_id), {'status':'DONE','handled_by_admin_tg_id':uid,'linked_order_id':oid})
    bot.send_message(call.message.chat.id, T(lang,'order_created', oid=oid))
    # notify client (if known) — только про покосы
    site=db.get_site(site_id)
    if site and site.get('client_tg_id') and not is_other:
        try:
            cu=int(site['client_tg_id'])
            bot.send_message(cu, f"✅ Покос выполнен: {site.get('address')}\n📅 {fmt_date_display(data.get('date'))}\nОткрой участок — там фотоотчёт.",
                             reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("📍 Открыть участок", callback_data=f"csitepick:{site_id}")))
        except Exception as e:
            logging.error(e)
    temp.pop(uid,None)
    bot.delete_state(uid, call.message.chat.id)
    show_admin_menu(call.message.chat.id, uid)
    safe_answer(call)

# ---------------- NEW: кнопка «⬅️ Назад» в мастере заказа ----------------

@bot.callback_query_handler(func=lambda c: c.data=='aback')
def order_step_back(call: types.CallbackQuery):
    """Вернуться на предыдущий шаг мастера — по текущему state."""
    if not require_admin_call(call): return
    uid=call.from_user.id; chat_id=call.message.chat.id
    try:
        state=str(bot.get_state(uid, chat_id) or '')
    except Exception:
        state=''
    ctx=temp.get(uid) or {}
    # шаги управления зонами из карточки участка
    if state in (AdminZoneManageStates.name.name, AdminZoneManageStates.area.name):
        site_id=int(ctx.get('site_id',0))
        temp.pop(uid,None); bot.delete_state(uid, chat_id)
        _show_zones_manage(chat_id, site_id)
        safe_answer(call); return
    is_other=(ctx.get('work_type')=='other')
    S=AdminOrderStates
    back_map={
        S.work_name.name: _ask_work_type,
        S.amount.name: _ask_work_name,
        S.zones.name: _ask_work_type,
        S.zone_new_name.name: _show_zones_screen,
        S.zone_new_area.name: _show_zones_screen,
        S.manual_area.name: _show_zones_screen,
        S.tariff.name: _show_zones_screen,
        S.paid.name: _ask_tariff,
        S.date.name: _ask_amount if is_other else _ask_paid,
        S.duration.name: _ask_date,
        S.helper.name: _ask_duration,
        S.helper_name.name: _ask_helper,
        S.helper_pay.name: _ask_helper_name,
        S.dad.name: _ask_helper,
        S.notes.name: _ask_dad if is_other else _ask_helper,
        S.photos.name: _ask_notes,
        S.confirm.name: _ask_photos,
    }
    fn=back_map.get(state)
    if not fn or ctx.get('flow') not in ('admin_order','admin_order_pick'):
        temp.pop(uid,None); bot.delete_state(uid, chat_id)
        show_admin_menu(chat_id, uid)
    else:
        fn(uid, chat_id)
    safe_answer(call)

# ---------------- NEW: раздел «Участки» ----------------

@bot.callback_query_handler(func=lambda c: c.data=='asites')
def asites(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    temp.pop(uid,None)
    bot.set_state(uid, AdminSitesStates.search, call.message.chat.id)
    sites=db.list_sites_recent(limit=20)
    text="🏡 Участки (свежие сверху). Открой кнопкой — или напиши часть адреса для поиска:" if sites else \
         "🏡 Участков пока нет — создай первый:"
    bot.send_message(call.message.chat.id, text, reply_markup=sites_browse_kb(sites))
    safe_answer(call)

@bot.message_handler(state=AdminSitesStates.search)
def asites_search(message: types.Message):
    if not require_admin_msg(message): return
    q=(message.text or '').strip()
    sites=db.search_sites(q, limit=20)
    if not sites:
        kb=types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("➕ Новый участок", callback_data="anewsite_only"))
        kb.add(types.InlineKeyboardButton("↩️ В меню", callback_data="amenu"))
        bot.send_message(message.chat.id, f"По запросу «{q}» ничего не нашёл:", reply_markup=kb)
        return
    bot.send_message(message.chat.id, "Нашёл — выбирай:", reply_markup=search_results_kb(sites, "asite", back_cb="asites", new_site_cb="anewsite_only"))

# ---------------- NEW: зоны из карточки участка ----------------

def _show_zones_manage(chat_id:int, site_id:int):
    zones=db.list_zones(site_id)
    site=db.get_site(site_id) or {}
    total=sum(z['area_sotki'] for z in zones)
    text=(f"🌱 Зоны участка «{site.get('address','—')}»\n"
          + (f"Всего зон: {len(zones)}, суммарно {total:g} сот.\n" if zones else "Зон пока нет.\n")
          + "Нажми на зону, чтобы удалить её:")
    bot.send_message(chat_id, text, reply_markup=zones_manage_kb(zones, site_id))

@bot.callback_query_handler(func=lambda c: c.data.startswith('azones:'))
def azones(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    temp.pop(uid,None); bot.delete_state(uid, call.message.chat.id)
    _show_zones_manage(call.message.chat.id, int(call.data.split(':')[1]))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('azdelq:'))
def azdelq(call: types.CallbackQuery):
    """Спросить подтверждение перед удалением зоны."""
    if not require_admin_call(call): return
    zone=db.get_zone(int(call.data.split(':')[1]))
    if not zone:
        safe_answer(call); return
    bot.send_message(call.message.chat.id,
                     f"⚠️ Удалить зону «{zone['name']}» ({zone['area_sotki']:g} сот)?",
                     reply_markup=confirm_action_kb("🗑 Да, удалить зону", f"azdel:{zone['id']}", f"azones:{zone['site_id']}"))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('azdel:'))
def azdel(call: types.CallbackQuery):
    if not require_admin_call(call): return
    zone=db.get_zone(int(call.data.split(':')[1]))
    if zone:
        db.delete_zone(zone['id'])
        _show_zones_manage(call.message.chat.id, zone['site_id'])
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('azadd:'))
def azadd(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    site_id=int(call.data.split(':')[1])
    temp[uid]={'flow':'zone_manage','site_id':site_id}
    bot.set_state(uid, AdminZoneManageStates.name, call.message.chat.id)
    bot.send_message(call.message.chat.id, "🌿 Название зоны (например: перед домом):",
                     reply_markup=prompt_cancel_kb(f"azones:{site_id}"))
    safe_answer(call)

@bot.message_handler(state=AdminZoneManageStates.name)
def azadd_name(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    name=(message.text or '').strip()
    if len(name)<2:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    temp.setdefault(uid,{})['zone_name']=name
    bot.set_state(uid, AdminZoneManageStates.area, message.chat.id)
    bot.send_message(message.chat.id, "📏 Площадь зоны (сотки):",
                     reply_markup=prompt_cancel_kb(f"azones:{int(temp.get(uid,{}).get('site_id',0))}"))

@bot.message_handler(state=AdminZoneManageStates.area)
def azadd_area(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    try:
        area=float((message.text or '').strip().replace(',','.'))
        if area<=0: raise ValueError
    except Exception:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    ctx=temp.pop(uid,{})
    bot.delete_state(uid, message.chat.id)
    site_id=int(ctx.get('site_id',0))
    db.add_zone(site_id, ctx.get('zone_name','зона'), area)
    _show_zones_manage(message.chat.id, site_id)

# ---------------- NEW: удаление участка (с подтверждением кнопкой) ----------------

@bot.callback_query_handler(func=lambda c: c.data.startswith('asitedel:'))
def asitedel(call: types.CallbackQuery):
    if not require_admin_call(call): return
    site_id=int(call.data.split(':')[1])
    site=db.get_site(site_id)
    if not site:
        safe_answer(call); return
    n=db.count_orders_for_site(site_id)
    bot.send_message(call.message.chat.id,
                     f"⚠️ Удалить участок «{site['address']}» насовсем?\nВместе с ним удалятся {n} заказ(ов), фото и зоны.",
                     reply_markup=confirm_action_kb("🗑 Да, удалить участок", f"asitedel_yes:{site_id}", f"asite:{site_id}"))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('asitedel_yes:'))
def asitedel_yes(call: types.CallbackQuery):
    if not require_admin_call(call): return
    site_id=int(call.data.split(':')[1])
    ok=db.delete_site(site_id)
    bot.send_message(call.message.chat.id, "🗑 Участок удалён." if ok else "❌ Не удалось удалить.")
    asites(call)

@bot.callback_query_handler(func=lambda c: c.data=='amore')
def amore(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    temp.pop(uid,None); bot.delete_state(uid, call.message.chat.id)
    bot.send_message(call.message.chat.id, "⋯ Ещё:", reply_markup=admin_more_kb(T,lang))
    safe_answer(call)

# Легаси-кнопка «Архив» со старых сообщений — ведёт в «Ещё»
@bot.callback_query_handler(func=lambda c: c.data=='aarchive')
def aarchive(call: types.CallbackQuery):
    amore(call)

@bot.callback_query_handler(func=lambda c: c.data=='astats_all')
def astats_all(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    s=db.stats_all_service_orders()
    text="\n".join([
        "📊 <b>Статистика по всем заказам</b>",
        f"🔢 Заказов: <b>{int(s['total_orders'])}</b>",
        f"📏 Площадь: <b>{fmt_area(s['total_area'])}</b> сот.",
        f"💰 Выручка: <b>{fmt_price(s['total_income'])}</b> руб",
        f"📈 Средний заказ: <b>{fmt_price(s['avg_order_price'])}</b> руб",
    ])
    bot.send_message(call.message.chat.id, text, reply_markup=admin_more_kb(T,lang))
    safe_answer(call)

# шаги поиска: (state, ключ, вопрос, кнопка «пропустить»)
_FIND_STEPS=[
    (AdminFindStates.address,   'f_addr',  "🔎 Адрес (можно часть):",  'afsk_addr'),
    (AdminFindStates.date_from, 'f_dfrom', "📅 Дата ОТ:",              'afsk_dfrom'),
    (AdminFindStates.date_to,   'f_dto',   "📅 Дата ДО:",              'afsk_dto'),
    (AdminFindStates.price_min, 'f_pmin',  "💰 Сумма ОТ (руб):",       'afsk_pmin'),
    (AdminFindStates.price_max, 'f_pmax',  "💰 Сумма ДО (руб):",       'afsk_pmax'),
]

def _find_ask(uid:int, chat_id:int, step:int):
    state, _, prompt, skip_cb=_FIND_STEPS[step]
    temp.setdefault(uid,{})['f_step']=step
    bot.set_state(uid, state, chat_id)
    bot.send_message(chat_id, prompt, reply_markup=skip_kb(skip_cb))

def _find_next(uid:int, chat_id:int):
    step=temp.setdefault(uid,{}).get('f_step',0)
    if step+1 < len(_FIND_STEPS):
        _find_ask(uid, chat_id, step+1)
    else:
        _find_run(uid, chat_id)

def _find_run(uid:int, chat_id:int):
    lang=get_lang(uid)
    ctx=temp.get(uid,{})
    res=db.find_service_orders(
        address_like=ctx.get('f_addr'),
        date_from=ctx.get('f_dfrom'),
        date_to=ctx.get('f_dto'),
        price_min=ctx.get('f_pmin'),
        price_max=ctx.get('f_pmax'),
        limit=50
    )
    bot.delete_state(uid, chat_id)
    temp.pop(uid,None)
    if not res:
        bot.send_message(chat_id, T(lang,'find_results_empty'), reply_markup=admin_more_kb(T,lang)); return
    kb=types.InlineKeyboardMarkup()
    lines=["🔎 <b>Результаты</b>:"]
    for it in res:
        lines.append(f"#{it['id']} • {fmt_date_display(it['service_at'])} • {it['address']} • {fmt_price(it['total'])} руб")
        kb.add(types.InlineKeyboardButton(f"🧾 #{it['id']} — {it['address']}", callback_data=f"aorder:{it['id']}"))
    kb.add(types.InlineKeyboardButton(T(lang,'admin_back_menu'), callback_data="amenu"))
    bot.send_message(chat_id, "\n".join(lines[:60]), reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data=='afind')
def afind(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    temp[uid]={'flow':'find'}
    _find_ask(uid, call.message.chat.id, 0)
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('afsk_'))
def afind_skip(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    step=temp.setdefault(uid,{}).get('f_step',0)
    temp[uid][_FIND_STEPS[step][1]]=None
    _find_next(uid, call.message.chat.id)
    safe_answer(call)

@bot.message_handler(state=AdminFindStates.address)
def afind_addr(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id
    txt=(message.text or '').strip()
    temp.setdefault(uid,{})['f_addr']=txt if txt!='-' else None
    _find_next(uid, message.chat.id)

@bot.message_handler(state=AdminFindStates.date_from)
def afind_dfrom(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id
    txt=(message.text or '').strip()
    dt=parse_date(txt) if txt!='-' else None
    temp.setdefault(uid,{})['f_dfrom']=dt.strftime('%Y-%m-%d') if dt else None
    _find_next(uid, message.chat.id)

@bot.message_handler(state=AdminFindStates.date_to)
def afind_dto(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id
    txt=(message.text or '').strip()
    dt=parse_date(txt) if txt!='-' else None
    temp.setdefault(uid,{})['f_dto']=dt.strftime('%Y-%m-%d') if dt else None
    _find_next(uid, message.chat.id)

@bot.message_handler(state=AdminFindStates.price_min)
def afind_pmin(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id
    txt=(message.text or '').strip()
    pmin=None
    if txt!='-':
        try: pmin=float(txt.replace(',','.'))
        except Exception: pmin=None
    temp.setdefault(uid,{})['f_pmin']=pmin
    _find_next(uid, message.chat.id)

@bot.message_handler(state=AdminFindStates.price_max)
def afind_pmax(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id
    txt=(message.text or '').strip()
    pmax=None
    if txt!='-':
        try: pmax=float(txt.replace(',','.'))
        except Exception: pmax=None
    temp.setdefault(uid,{})['f_pmax']=pmax
    _find_next(uid, message.chat.id)

def asite_show(chat_id:int, uid:int, site_id:int):
    lang=get_lang(uid)
    s=db.get_site(site_id)
    if not s:
        bot.send_message(chat_id, "❌ Участок не найден.")
        return
    contacts = "—"
    if s.get('contact_phone') or s.get('contact_name'):
        contacts = f"{s.get('contact_name') or ''} {s.get('contact_phone') or ''}".strip()
    text=T(lang,'admin_site_card',
           sid=s['id'],
           address=s['address'],
           area=f"{fmt_area(s.get('area_sotki'))} сот.",
           contacts=contacts,
           last=fmt_date_display(s.get('last_service_at')),
           n=int(s.get('service_count') or 0))
    text += f"\n⏰ Напоминание: раз в {int(s.get('remind_days') or 30)} дн."
    bot.send_message(chat_id, text, reply_markup=admin_site_actions_kb(site_id, T, lang))

@bot.callback_query_handler(func=lambda c: c.data.startswith('asite:'))
def asite(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    temp.pop(uid,None); bot.delete_state(uid, call.message.chat.id)
    asite_show(call.message.chat.id, uid, int(call.data.split(':')[1]))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('asite_orders:'))
def asite_orders(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    site_id=int(call.data.split(':')[1])
    orders=db.list_service_orders_for_site(site_id, limit=100)
    if not orders:
        bot.send_message(call.message.chat.id, "📭 История пуста.", reply_markup=admin_site_actions_kb(site_id, T, lang))
    else:
        bot.send_message(call.message.chat.id, "📜 История участка:", reply_markup=admin_orders_list_kb(site_id, orders, T, lang))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('aorder:'))
def aorder_open(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    temp.pop(uid,None); bot.delete_state(uid, call.message.chat.id)
    oid=int(call.data.split(':')[1])
    o=db.get_service_order(oid)
    if not o:
        bot.send_message(call.message.chat.id, "❌ Заказ не найден.")
        safe_answer(call); return
    site=db.get_site(o['site_id'])
    bot.send_message(call.message.chat.id, order_card_text(o, site), reply_markup=admin_order_actions_kb(oid, T, lang))
    # send photos (optional)
    photos=db.get_service_order_photos(oid)
    if photos:
        try:
            bot.send_media_group(call.message.chat.id, [types.InputMediaPhoto(fid) for fid in photos[:10]])
        except Exception as e:
            logging.error(e)
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('adel:'))
def adel(call: types.CallbackQuery):
    if not require_admin_call(call): return
    oid=int(call.data.split(':')[1])
    bot.send_message(call.message.chat.id, f"⚠️ Удалить заказ #{oid}?",
                     reply_markup=confirm_action_kb("🗑 Да, удалить", f"adel_yes:{oid}", f"aorder:{oid}"))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('adel_yes:'))
def adel_yes(call: types.CallbackQuery):
    if not require_admin_call(call): return
    oid=int(call.data.split(':')[1])
    o=db.get_service_order(oid)
    ok=db.delete_service_order(oid)
    bot.send_message(call.message.chat.id, "🗑 Удалено." if ok else "❌ Не удалось удалить.")
    if o:
        asite_show(call.message.chat.id, call.from_user.id, o['site_id'])
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('adelall:'))
def adelall(call: types.CallbackQuery):
    if not require_admin_call(call): return
    site_id=int(call.data.split(':')[1])
    site=db.get_site(site_id)
    if not site:
        safe_answer(call); return
    n=db.count_orders_for_site(site_id)
    bot.send_message(call.message.chat.id,
                     f"⚠️ Удалить все заказы ({n} шт.) по участку «{site['address']}»? Сам участок останется.",
                     reply_markup=confirm_action_kb("🗑 Да, удалить все", f"adelall_yes:{site_id}", f"asite:{site_id}"))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('adelall_yes:'))
def adelall_yes(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    site_id=int(call.data.split(':')[1])
    n=db.delete_all_orders_for_site(site_id)
    bot.send_message(call.message.chat.id, T(lang,'admin_deleted_all', n=n))
    asite_show(call.message.chat.id, uid, site_id)
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('asite_edit:'))
def asite_edit(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    site_id=int(call.data.split(':')[1])
    bot.send_message(call.message.chat.id, "Что изменить в участке?", reply_markup=admin_edit_site_kb(site_id, T, lang))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('asite_edit_field:'))
def asite_edit_field(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    _, field, site_id = call.data.split(':')
    site_id=int(site_id)
    temp[uid]={'flow':'edit_site','site_id':site_id,'field':field}
    bot.set_state(uid, AdminEditSiteStates.field, call.message.chat.id)
    prompts={'address':"📍 Новый адрес:","area":"📏 Новая площадь (сотки):",
             'name':"👤 Имя клиента:","contacts":"☎️ Телефон клиента:",
             'remind':"⏰ Через сколько дней напоминать о покосе (сейчас по умолчанию 30):"}
    bot.send_message(call.message.chat.id, prompts.get(field,'Введите значение:'),
                     reply_markup=prompt_cancel_kb(f"asite:{site_id}"))
    safe_answer(call)

@bot.message_handler(state=AdminEditSiteStates.field)
def asite_edit_apply(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    ctx=temp.get(uid,{})
    site_id=int(ctx.get('site_id',0)); field=ctx.get('field')
    txt=(message.text or '').strip()
    fields={}
    try:
        if field=='address':
            if len(txt)<3: raise ValueError
            fields['address']=txt
        elif field=='area':
            fields['area_sotki']=float(txt.replace(',','.'))
        elif field=='name':
            if not txt: raise ValueError
            fields['contact_name']=txt
        elif field=='contacts':
            # store only phone string for now
            fields['contact_phone']=txt
        elif field=='remind':
            days=int(txt)
            if days<=0: raise ValueError
    except Exception:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    if field=='remind':
        ok=db.set_remind_days(site_id, int(txt))
    else:
        ok=db.update_site(site_id, fields)
    temp.pop(uid,None); bot.delete_state(uid, message.chat.id)
    bot.send_message(message.chat.id, "✅ Обновлено." if ok else "❌ Не удалось обновить.")
    asite_show(message.chat.id, uid, site_id)

@bot.callback_query_handler(func=lambda c: c.data.startswith('aorder_edit:'))
def aorder_edit(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    oid=int(call.data.split(':')[1])
    o=db.get_service_order(oid)
    wt=(o.get('work_type') if o else 'mow') or 'mow'
    bot.send_message(call.message.chat.id, "Что изменить в заказе?", reply_markup=admin_edit_order_kb(oid, T, lang, work_type=wt))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('aorder_edit_field:'))
def aorder_edit_field(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    _, field, oid = call.data.split(':')
    oid=int(oid)
    temp[uid]={'flow':'edit_order','order_id':oid,'field':field}
    bot.set_state(uid, AdminEditServiceOrderStates.field, call.message.chat.id)
    prompts={'area':"📏 Новая площадь (сотки):",
             'tariff':"💵 Новый тариф (руб/сот):",
             'amount':"💰 Новая сумма за работу (руб, для «другой работы»):",
             'paid':"💸 Сколько заплатили по факту (руб)? 0 — вернуть «ровно по расчёту»:",
             'helper':"🤝 Сколько отдал помощнику (руб, 0 — если не было):",
             'date':"📅 Новая дата:",
             'duration':"⏳ Новая длительность (2.5, 2:30, 9:30-12:00):",
             'notes':"📝 Новые заметки:"}
    bot.send_message(call.message.chat.id, prompts.get(field,'Введите значение:'),
                     reply_markup=prompt_cancel_kb(f"aorder:{oid}"))
    safe_answer(call)

@bot.message_handler(state=AdminEditServiceOrderStates.field)
def aorder_edit_apply(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    ctx=temp.get(uid,{})
    oid=int(ctx.get('order_id',0)); field=ctx.get('field')
    txt=(message.text or '').strip()
    fields={}
    try:
        if field=='area':
            fields['area_sotki']=float(txt.replace(',','.'))
        elif field=='tariff':
            fields['tariff']=int(txt)
        elif field=='amount':
            fields['amount']=float(txt.replace(',','.').replace(' ',''))
        elif field=='paid':
            v=float(txt.replace(',','.').replace(' ',''))
            if v<0: raise ValueError
            fields['paid_amount']=None if v==0 else v
        elif field=='helper':
            fields['helper_pay']=float(txt.replace(',','.').replace(' ',''))
        elif field=='date':
            dt=parse_date(txt)
            if not dt: raise ValueError
            fields['service_at']=dt.strftime('%Y-%m-%d')
        elif field=='duration':
            mins=parse_duration_minutes(txt)
            if not mins: raise ValueError
            fields['duration']=fmt_minutes(mins)
            fields['duration_min']=mins
        elif field=='notes':
            fields['notes']=txt
    except Exception:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    ok=db.update_service_order(oid, fields)
    temp.pop(uid,None); bot.delete_state(uid, message.chat.id)
    bot.send_message(message.chat.id, "✅ Обновлено." if ok else "❌ Не удалось обновить.")
    # show order again
    o=db.get_service_order(oid)
    if o:
        site=db.get_site(o['site_id'])
        bot.send_message(message.chat.id, order_card_text(o, site), reply_markup=admin_order_actions_kb(oid, T, lang))
    else:
        show_admin_menu(message.chat.id, uid)

# ---------------- NEW: статистика с деньгами ----------------

PERIOD_TITLES={'week':'неделя','month':'месяц','year':'год','all':'всё время'}

def build_stats_text(period:str) -> str:
    orders=db.list_orders_for_period(period)
    mows=[o for o in orders if (o.get('work_type') or 'mow')!='other']
    others=[o for o in orders if (o.get('work_type') or 'mow')=='other']
    revenue=helpers=percent=dad=net=0.0
    total_min=0
    for o in orders:
        m=calc_money(o.get('work_type') or 'mow', order_revenue(o),
                     o.get('helper_pay') or 0, 1 if o.get('dad_share') is None else int(o.get('dad_share')))
        revenue+=m['revenue']; helpers+=m['helper_pay']; percent+=m['percent']; dad+=m['dad']; net+=m['net']
        total_min+=int(o.get('duration_min') or 0)
    area=sum(float(o.get('area_sotki') or 0) for o in mows)
    lines=[f"📊 <b>Статистика ({PERIOD_TITLES.get(period, period)})</b>",
           f"🌱 Покосов: <b>{len(mows)}</b>" + (f"   🔨 Других работ: <b>{len(others)}</b>" if others else ""),
           f"📏 Соток покошено: <b>{fmt_area(area)}</b>",
           "",
           f"💰 Оборот: <b>{fmt_price(revenue)}</b> руб",
           f"🤝 Помощникам: −{fmt_price(helpers)} руб",
           f"📉 Проценты: −{fmt_price(percent)} руб",
           f"👨 Папе: {fmt_price(dad)} руб",
           f"✅ Чистая прибыль: <b>{fmt_price(net)}</b> руб"]
    ph=per_hour(revenue, total_min)
    if ph is not None:
        lines.append(f"⚡ Средний доход в час: {fmt_price(ph)} руб/ч")
    return "\n".join(lines)

@bot.callback_query_handler(func=lambda c: c.data=='astats_menu')
def astats_menu(call: types.CallbackQuery):
    if not require_admin_call(call): return
    bot.send_message(call.message.chat.id, "📊 За какой период?", reply_markup=stats_period_kb())
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('astats:'))
def astats_period(call: types.CallbackQuery):
    if not require_admin_call(call): return
    period=call.data.split(':')[1]
    bot.send_message(call.message.chat.id, build_stats_text(period), reply_markup=stats_period_kb())
    safe_answer(call)

# ---------------- NEW: напоминания о покосе ----------------

def _remind_site_text(r: Dict) -> str:
    who=r.get('contact_name') or '—'
    phone=r.get('contact_phone') or '—'
    return (f"📍 {r['address']}\n"
            f"👤 {who}   ☎️ {phone}\n"
            f"🌱 Последний покос: {fmt_date_display(r.get('last_mow'))} — <b>{int(r.get('days_ago') or 0)} дн. назад</b>"
            f" (интервал {int(r.get('remind_days') or 30)} дн.)")

@bot.callback_query_handler(func=lambda c: c.data=='aremind')
def aremind(call: types.CallbackQuery):
    if not require_admin_call(call): return
    due=db.reminders_due(limit=20)
    if not due:
        bot.send_message(call.message.chat.id, "⏰ Напоминаний нет — всё покошено вовремя. 🌱")
        safe_answer(call); return
    bot.send_message(call.message.chat.id, f"⏰ Пора звонить — {len(due)} участок(ов):")
    for r in due:
        bot.send_message(call.message.chat.id, _remind_site_text(r), reply_markup=remind_actions_kb(r['id']))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('armd_call:'))
def armd_call(call: types.CallbackQuery):
    if not require_admin_call(call): return
    site_id=int(call.data.split(':')[1])
    db.snooze_site(site_id, 7)
    bot.send_message(call.message.chat.id, "📞 Отлично! Если покос не запишешь — напомню снова через 7 дней.")
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('armd_month:'))
def armd_month(call: types.CallbackQuery):
    if not require_admin_call(call): return
    site_id=int(call.data.split(':')[1])
    db.snooze_site(site_id, 30)
    bot.send_message(call.message.chat.id, "🗓 Отложил на месяц.")
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('armd_days:'))
def armd_days(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    temp[uid]={'flow':'remind_snooze','site_id':int(call.data.split(':')[1])}
    bot.set_state(uid, AdminRemindStates.snooze_days, call.message.chat.id)
    bot.send_message(call.message.chat.id, "⏲ На сколько дней отложить?", reply_markup=prompt_cancel_kb("amenu"))
    safe_answer(call)

@bot.message_handler(state=AdminRemindStates.snooze_days)
def armd_days_apply(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    try:
        days=int((message.text or '').strip())
        if days<=0 or days>365: raise ValueError
    except Exception:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    site_id=int(temp.get(uid,{}).get('site_id',0))
    db.snooze_site(site_id, days)
    temp.pop(uid,None); bot.delete_state(uid, message.chat.id)
    bot.send_message(message.chat.id, f"⏲ Отложил на {days} дн.")

# ---------------- NEW: утренний дайджест и бэкап базы ----------------

def send_daily_digest():
    due=db.reminders_due(limit=20)
    if not due:
        return
    for aid in admin_ids_all():
        try:
            bot.send_message(aid, f"☀️ Доброе утро! ⏰ Пора звонить — {len(due)} участок(ов):")
            for r in due:
                bot.send_message(aid, _remind_site_text(r), reply_markup=remind_actions_kb(r['id']))
        except Exception as e:
            logging.error(f"digest to {aid}: {e}")

def send_daily_backup():
    tmp=os.path.join(tempfile.gettempdir(), 'grass_orders_backup.db')
    try:
        db.backup_to(tmp)
    except Exception as e:
        logging.error(f"backup failed: {e}")
        return
    stamp=datetime.now(TZ).strftime('%Y-%m-%d')
    for aid in admin_ids_all():
        try:
            with open(tmp,'rb') as f:
                bot.send_document(aid, f, caption=f"💾 Бэкап базы за {stamp}",
                                  visible_file_name=f"grass_orders_{stamp}.db")
        except Exception as e:
            logging.error(f"backup to {aid}: {e}")

def scheduler_loop():
    """Раз в день в DIGEST_HOUR по BOT_TZ: напоминания + бэкап. Дата отправки хранится в базе."""
    while True:
        try:
            now=datetime.now(TZ)
            today=now.strftime('%Y-%m-%d')
            if now.hour>=DIGEST_HOUR and db.meta_get('digest_sent') != today:
                db.meta_set('digest_sent', today)
                send_daily_digest()
                send_daily_backup()
        except Exception as e:
            logging.error(f"scheduler: {e}")
        time.sleep(60)

# ---------------- LEGACY EXECUTOR FEATURES (optional) ----------------
# Existing bot functionality kept as-is and available for everyone, but you can restrict it:
# For now, keep it available ONLY for admins (so clients won't see executor stats/orders).

def _deny_if_not_admin(call_or_msg) -> bool:
    uid = call_or_msg.from_user.id if hasattr(call_or_msg, 'from_user') else call_or_msg.from_user.id
    if not is_admin(uid):
        lang=get_lang(uid)
        if hasattr(call_or_msg, 'message'):
            bot.send_message(call_or_msg.message.chat.id, T(lang,'admin_need_reg'))
        else:
            bot.send_message(call_or_msg.chat.id, T(lang,'admin_need_reg'))
        return False
    return True

# --- Legacy menu entry point ---
# Старые кнопки (new_order / order_history / statistics / main_menu) раньше висели
# без обработчиков — теперь ведут в актуальные разделы админки.
@bot.callback_query_handler(func=lambda c: c.data=='main_menu')
def legacy_main_menu(call: types.CallbackQuery):
    if not require_admin_call(call): return
    show_admin_menu(call.message.chat.id, call.from_user.id)
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data=='new_order')
def legacy_new_order(call: types.CallbackQuery):
    aneworder(call)

@bot.callback_query_handler(func=lambda c: c.data=='order_history')
def legacy_order_history(call: types.CallbackQuery):
    aarchive(call)

@bot.callback_query_handler(func=lambda c: c.data=='statistics')
def legacy_statistics(call: types.CallbackQuery):
    astats_menu(call)

# Legacy cancel (shared)
@bot.callback_query_handler(func=lambda c: c.data=='cancel')
def cancel(call: types.CallbackQuery):
    uid = call.from_user.id
    temp.pop(uid, None)
    bot.delete_state(uid, call.message.chat.id)
    # return to correct menu
    if is_admin(uid):
        show_admin_menu(call.message.chat.id, uid)
    else:
        show_client_start(call.message.chat.id, uid)
    safe_answer(call)

# ---------------- Fallback: любой текст вне диалога → меню ----------------
# Регистрируется последним: срабатывает, только если ни один обработчик выше не подошёл.
@bot.message_handler(func=lambda m: True, content_types=['text'])
def fallback_text(message: types.Message):
    uid=message.from_user.id
    try:
        state=bot.get_state(uid, message.chat.id)
    except Exception:
        state=None
    if state:
        # человек в диалоге, где ждём кнопку — подскажем, а не собьём
        bot.send_message(message.chat.id, "☝️ Жду нажатия кнопки выше. Начать заново — /cancel")
        return
    if is_admin(uid):
        show_admin_menu(message.chat.id, uid)
    else:
        show_client_start(message.chat.id, uid)

# ---------------- Run ----------------
if __name__ == '__main__':
    print("Bot running...")
    try:
        # Fix 409 conflict: if webhook was set, remove it before polling
        bot.remove_webhook()
    except Exception as e:
        logging.error(f"remove_webhook: {e}")
    threading.Thread(target=scheduler_loop, daemon=True).start()
    bot.infinity_polling(skip_pending=True)
