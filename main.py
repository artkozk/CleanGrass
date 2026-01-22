import logging
import re
from typing import Dict, Optional, List
from datetime import datetime

import telebot
from telebot import types
from telebot.custom_filters import StateFilter

from config import DB_NAME, LANG, T, BOT_TOKEN, ADMIN_IDS, ADMIN_PASSWORD
from database import Database
from states import (
    OrderStates, DeleteStates, HistoryRangeStates, StatsFilterStates, EditOrderStates,
    AdminRegStates, ClientRequestStates, AdminOrderStates, AdminDeleteAllStates,
    AdminFindStates, AdminEditSiteStates, AdminEditServiceOrderStates
)
from keyboards import (
    main_menu, cancel_kb, tariffs_kb, addresses_kb, confirm_kb, period_kb,
    order_actions_kb, delete_confirm_kb, stats_filters_kb, edit_order_kb, settings_kb,
    client_start_kb, client_site_nav_kb, client_contacts_reply_kb,
    admin_menu_kb, admin_requests_list_kb, admin_request_actions_kb, admin_archive_kb,
    admin_site_actions_kb, admin_sites_kb, admin_orders_list_kb, admin_order_actions_kb,
    admin_edit_site_kb, admin_edit_order_kb, admin_inline_done_kb
)

logging.basicConfig(level=logging.INFO, filename='bot.log', format='%(asctime)s %(levelname)s %(message)s')

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is empty. Set env BOT_TOKEN in your .env or environment.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')
bot.add_custom_filter(StateFilter(bot))

db = Database(DB_NAME)

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
    bot.send_message(chat_id, T(lang,'admin_menu'), reply_markup=admin_menu_kb(db.count_new_requests(), T, lang))

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

@bot.message_handler(content_types=['contact'], state=ClientRequestStates.contacts)
def c_enter_contacts_contact(message: types.Message):
    uid=message.from_user.id; lang=get_lang(uid)
    phone = message.contact.phone_number if message.contact else ''
    temp.setdefault(uid,{})['contacts']=phone
    db.upsert_client(uid, phone=phone)
    bot.set_state(uid, ClientRequestStates.comment, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'client_enter_comment'), reply_markup=cancel_kb(T,lang))

@bot.message_handler(state=ClientRequestStates.contacts)
def c_enter_contacts_text(message: types.Message):
    uid=message.from_user.id; lang=get_lang(uid)
    txt=(message.text or '').strip()
    if txt.lower()==T(lang,'cancel').lower():
        temp.pop(uid,None); bot.delete_state(uid, message.chat.id); show_client_start(message.chat.id, uid); return
    temp.setdefault(uid,{})['contacts']=txt
    bot.set_state(uid, ClientRequestStates.comment, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'client_enter_comment'), reply_markup=cancel_kb(T,lang))

@bot.message_handler(state=ClientRequestStates.comment)
def c_enter_comment(message: types.Message):
    uid=message.from_user.id; lang=get_lang(uid)
    txt=(message.text or '').strip()
    if txt.lower()==T(lang,'cancel').lower():
        temp.pop(uid,None); bot.delete_state(uid, message.chat.id); show_client_start(message.chat.id, uid); return
    temp.setdefault(uid,{})['comment']=txt if txt not in (LANG['ru']['skip'], LANG['en']['skip']) else ''
    # confirm
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
    bot.send_message(message.chat.id, summary, reply_markup=kb)
    bot.set_state(uid, ClientRequestStates.confirm, message.chat.id)

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
    show_admin_menu(call.message.chat.id, call.from_user.id)
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
        bot.send_message(call.message.chat.id, T(lang,'admin_notifs_empty'), reply_markup=admin_menu_kb(db.count_new_requests(), T, lang))
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
    temp[uid] = {'flow':'admin_order', 'site_id':int(site_id), 'req_id':req_id, 'photos':[]}
    bot.set_state(uid, AdminOrderStates.area, call.message.chat.id)
    bot.send_message(call.message.chat.id, f"📏 Площадь (сотки). Можно '-' чтобы оставить {fmt_area(r.get('area_sotki'))}:")
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data=='aneworder')
def aneworder(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    temp[uid]={'flow':'admin_order_pick'}
    bot.set_state(uid, AdminOrderStates.site_search, call.message.chat.id)
    bot.send_message(call.message.chat.id, T(lang,'admin_search_site'))
    safe_answer(call)

@bot.message_handler(state=AdminOrderStates.site_search)
def a_site_search(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    q=(message.text or '').strip()
    if q.lower()==T(lang,'cancel').lower():
        temp.pop(uid,None); bot.delete_state(uid, message.chat.id); show_admin_menu(message.chat.id, uid); return
    if q=='-':
        bot.set_state(uid, AdminOrderStates.new_site_address, message.chat.id)
        bot.send_message(message.chat.id, T(lang,'admin_new_site_address'))
        return
    sites=db.search_sites(q, limit=20)
    if not sites:
        bot.send_message(message.chat.id, "Ничего не найдено. Отправь '-' чтобы создать новый участок.")
        return
    kb=types.InlineKeyboardMarkup()
    for s in sites:
        kb.add(types.InlineKeyboardButton(f"📍 {s['address']}", callback_data=f"aneworder_site:{s['id']}"))
    kb.add(types.InlineKeyboardButton("➕ Новый участок", callback_data="aneworder_newsite"))
    kb.add(types.InlineKeyboardButton(T(lang,'admin_back_menu'), callback_data="amenu"))
    bot.send_message(message.chat.id, T(lang,'admin_pick_site'), reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data=='aneworder_newsite')
def aneworder_newsite(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    bot.set_state(uid, AdminOrderStates.new_site_address, call.message.chat.id)
    bot.send_message(call.message.chat.id, T(lang,'admin_new_site_address'))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('aneworder_site:'))
def aneworder_site(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id
    site_id=int(call.data.split(':')[1])
    temp[uid]={'flow':'admin_order','site_id':site_id,'photos':[]}
    bot.set_state(uid, AdminOrderStates.area, call.message.chat.id)
    site=db.get_site(site_id)
    bot.send_message(call.message.chat.id, f"📏 Площадь (сотки). Можно '-' чтобы оставить {fmt_area(site.get('area_sotki'))}:")
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
    bot.send_message(message.chat.id, T(lang,'admin_new_site_area'))

@bot.message_handler(state=AdminOrderStates.new_site_area)
def a_new_site_area(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    try:
        area=float((message.text or '').strip().replace(',','.'))
        if area<=0: raise ValueError
    except Exception:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    temp.setdefault(uid,{})['new_site_area']=area
    bot.set_state(uid, AdminOrderStates.new_site_contacts, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'admin_new_site_contacts'))

@bot.message_handler(state=AdminOrderStates.new_site_contacts)
def a_new_site_contacts(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id
    contacts=(message.text or '').strip()
    addr=temp.get(uid,{}).get('new_site_address')
    area=temp.get(uid,{}).get('new_site_area')
    site_id=db.create_site(None, addr, area, contacts, created_by='ADMIN')
    # start order flow on this site
    temp[uid]={'flow':'admin_order','site_id':site_id,'photos':[]}
    bot.set_state(uid, AdminOrderStates.area, message.chat.id)
    bot.send_message(message.chat.id, f"📏 Площадь (сотки). Можно '-' чтобы оставить {fmt_area(area)}:")

@bot.message_handler(state=AdminOrderStates.area)
def a_order_area(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    site=db.get_site(temp.get(uid,{}).get('site_id',0))
    txt=(message.text or '').strip()
    if txt=='-' and site:
        area=site.get('area_sotki')
    else:
        try:
            area=float(txt.replace(',','.'))
            if area<=0: raise ValueError
        except Exception:
            bot.send_message(message.chat.id, T(lang,'err_value')); return
    temp.setdefault(uid,{})['area']=area
    bot.set_state(uid, AdminOrderStates.tariff, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'enter_tariff'))

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
    bot.set_state(uid, AdminOrderStates.date, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'enter_date'))

@bot.message_handler(state=AdminOrderStates.date)
def a_order_date(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    dt=parse_date((message.text or '').strip())
    if not dt:
        bot.send_message(message.chat.id, T(lang,'err_date')); return
    temp.setdefault(uid,{})['date']=dt.strftime('%Y-%m-%d')
    bot.set_state(uid, AdminOrderStates.duration, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'enter_duration'))

@bot.message_handler(state=AdminOrderStates.duration)
def a_order_duration(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    d=parse_duration((message.text or '').strip())
    if not d:
        bot.send_message(message.chat.id, T(lang,'err_duration')); return
    temp.setdefault(uid,{})['duration']=d
    bot.set_state(uid, AdminOrderStates.notes, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'notes'))

@bot.message_handler(state=AdminOrderStates.notes)
def a_order_notes(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    txt=(message.text or '').strip()
    temp.setdefault(uid,{})['notes']=txt if txt not in (LANG['ru']['skip'], LANG['en']['skip']) else ''
    temp.setdefault(uid,{})['photos']=[]
    bot.set_state(uid, AdminOrderStates.photos, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'admin_order_photos'), reply_markup=admin_inline_done_kb("aphoto_done", T, lang))

@bot.message_handler(content_types=['photo'], state=AdminOrderStates.photos)
def a_order_photos(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id
    fid=message.photo[-1].file_id
    temp.setdefault(uid,{}).setdefault('photos',[]).append(fid)
    bot.send_message(message.chat.id, f"📸 Добавлено фото ({len(temp[uid]['photos'])}).")

@bot.callback_query_handler(func=lambda c: c.data=='aphoto_done', state=AdminOrderStates.photos)
def aphoto_done(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    data=temp.get(uid,{})
    site=db.get_site(data.get('site_id',0))
    if not site:
        bot.send_message(call.message.chat.id, "❌ Участок не найден.")
        safe_answer(call); return
    total=fmt_price((data.get('area') or 0)*(data.get('tariff') or 0))
    text="\n".join([
        "📌 <b>Сводка заказа</b>",
        f"📍 {site['address']}",
        f"📏 {fmt_area(data.get('area'))} сот.",
        f"💵 {data.get('tariff')} руб/сот.",
        f"📅 {fmt_date_display(data.get('date'))}",
        f"⏳ {data.get('duration')}",
        f"💰 {total} руб",
        f"📸 Фото: {len(data.get('photos') or [])}",
        f"📝 {data.get('notes') or '—'}"
    ])
    kb=types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ Создать", callback_data="aconfirm_order"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="acancel_order"),
    )
    bot.send_message(call.message.chat.id, text, reply_markup=kb)
    bot.set_state(uid, AdminOrderStates.confirm, call.message.chat.id)
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data in ('aconfirm_order','acancel_order'), state=AdminOrderStates.confirm)
def aconfirm_order(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    if call.data=='acancel_order':
        temp.pop(uid,None); bot.delete_state(uid, call.message.chat.id); show_admin_menu(call.message.chat.id, uid); safe_answer(call); return
    data=temp.get(uid,{})
    site_id=int(data.get('site_id',0))
    oid=db.create_service_order(
        site_id=site_id,
        service_at=data.get('date'),
        area_sotki=data.get('area'),
        tariff=data.get('tariff'),
        duration=data.get('duration'),
        notes=data.get('notes'),
        admin_tg_id=uid,
        photo_file_ids=data.get('photos') or []
    )
    # link to request if present
    req_id=data.get('req_id')
    if req_id:
        db.update_request(int(req_id), {'status':'DONE','handled_by_admin_tg_id':uid,'linked_order_id':oid})
    bot.send_message(call.message.chat.id, T(lang,'order_created', oid=oid))
    # notify client (if known)
    site=db.get_site(site_id)
    if site and site.get('client_tg_id'):
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

@bot.callback_query_handler(func=lambda c: c.data=='aarchive')
def aarchive(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    bot.send_message(call.message.chat.id, "🗂 Архив:", reply_markup=admin_archive_kb(T,lang))
    safe_answer(call)

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
    bot.send_message(call.message.chat.id, text, reply_markup=admin_archive_kb(T,lang))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data=='afind')
def afind(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    temp[uid]={'flow':'find'}
    bot.set_state(uid, AdminFindStates.address, call.message.chat.id)
    bot.send_message(call.message.chat.id, T(lang,'find_enter_address'))
    safe_answer(call)

@bot.message_handler(state=AdminFindStates.address)
def afind_addr(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    temp.setdefault(uid,{})['f_addr']=(message.text or '').strip()
    bot.set_state(uid, AdminFindStates.date_from, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'find_enter_date_from'))

@bot.message_handler(state=AdminFindStates.date_from)
def afind_dfrom(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    txt=(message.text or '').strip()
    dt=parse_date(txt) if txt!='-' else None
    temp.setdefault(uid,{})['f_dfrom']=dt.strftime('%Y-%m-%d') if dt else None
    bot.set_state(uid, AdminFindStates.date_to, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'find_enter_date_to'))

@bot.message_handler(state=AdminFindStates.date_to)
def afind_dto(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    txt=(message.text or '').strip()
    dt=parse_date(txt) if txt!='-' else None
    temp.setdefault(uid,{})['f_dto']=dt.strftime('%Y-%m-%d') if dt else None
    bot.set_state(uid, AdminFindStates.price_min, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'find_enter_price_min'))

@bot.message_handler(state=AdminFindStates.price_min)
def afind_pmin(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    txt=(message.text or '').strip()
    pmin=None
    if txt!='-':
        try: pmin=float(txt.replace(',','.'))
        except Exception: pmin=None
    temp.setdefault(uid,{})['f_pmin']=pmin
    bot.set_state(uid, AdminFindStates.price_max, message.chat.id)
    bot.send_message(message.chat.id, T(lang,'find_enter_price_max'))

@bot.message_handler(state=AdminFindStates.price_max)
def afind_pmax(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    txt=(message.text or '').strip()
    pmax=None
    if txt!='-':
        try: pmax=float(txt.replace(',','.'))
        except Exception: pmax=None
    ctx=temp.get(uid,{})
    res=db.find_service_orders(
        address_like=ctx.get('f_addr'),
        date_from=ctx.get('f_dfrom'),
        date_to=ctx.get('f_dto'),
        price_min=ctx.get('f_pmin'),
        price_max=pmax,
        limit=50
    )
    bot.delete_state(uid, message.chat.id)
    temp.pop(uid,None)
    if not res:
        bot.send_message(message.chat.id, T(lang,'find_results_empty'), reply_markup=admin_archive_kb(T,lang)); return
    kb=types.InlineKeyboardMarkup()
    lines=["🔎 <b>Результаты</b>:"]
    for it in res:
        lines.append(f"#{it['id']} • {fmt_date_display(it['service_at'])} • {it['address']} • {fmt_price(it['total'])} руб")
        kb.add(types.InlineKeyboardButton(f"🧾 #{it['id']} — {it['address']}", callback_data=f"aorder:{it['id']}"))
    kb.add(types.InlineKeyboardButton(T(lang,'admin_back_menu'), callback_data="aarchive"))
    bot.send_message(message.chat.id, "\n".join(lines[:60]), reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith('asite:'))
def asite(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    site_id=int(call.data.split(':')[1])
    s=db.get_site(site_id)
    if not s:
        bot.send_message(call.message.chat.id, "❌ Участок не найден.")
        safe_answer(call); return
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
    bot.send_message(call.message.chat.id, text, reply_markup=admin_site_actions_kb(site_id, T, lang))
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
    oid=int(call.data.split(':')[1])
    o=db.get_service_order(oid)
    if not o:
        bot.send_message(call.message.chat.id, "❌ Заказ не найден.")
        safe_answer(call); return
    site=db.get_site(o['site_id'])
    text=T(lang,'admin_order_card',
           oid=o['id'],
           address=site['address'] if site else '—',
           area=fmt_area(o.get('area_sotki')),
           tariff=o.get('tariff') or 0,
           date=fmt_date_display(o.get('service_at')),
           dur=o.get('duration') or '—',
           notes=o.get('notes') or '—')
    bot.send_message(call.message.chat.id, text, reply_markup=admin_order_actions_kb(oid, T, lang))
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
    ok=db.delete_service_order(oid)
    bot.send_message(call.message.chat.id, "🗑 Удалено." if ok else "❌ Не удалось удалить.")
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('adelall:'))
def adelall(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    site_id=int(call.data.split(':')[1])
    temp[uid]={'flow':'delall','site_id':site_id}
    bot.set_state(uid, AdminDeleteAllStates.confirm_phrase, call.message.chat.id)
    bot.send_message(call.message.chat.id, T(lang,'admin_confirm_phrase'))
    safe_answer(call)

@bot.message_handler(state=AdminDeleteAllStates.confirm_phrase)
def adelall_confirm(message: types.Message):
    if not require_admin_msg(message): return
    uid=message.from_user.id; lang=get_lang(uid)
    phrase=(message.text or '').strip().lower()
    if phrase != 'да, хочу удалить':
        bot.send_message(message.chat.id, "❌ Не подтверждено. Отмена.")
        temp.pop(uid,None); bot.delete_state(uid, message.chat.id); show_admin_menu(message.chat.id, uid); return
    site_id=int(temp.get(uid,{}).get('site_id',0))
    n=db.delete_all_orders_for_site(site_id)
    bot.send_message(message.chat.id, T(lang,'admin_deleted_all', n=n))
    temp.pop(uid,None); bot.delete_state(uid, message.chat.id); show_admin_menu(message.chat.id, uid)

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
    _, _, field, site_id = call.data.split(':')
    site_id=int(site_id)
    temp[uid]={'flow':'edit_site','site_id':site_id,'field':field}
    bot.set_state(uid, AdminEditSiteStates.field, call.message.chat.id)
    prompts={'address':"📍 Новый адрес:","area":"📏 Новая площадь (сотки):","contacts":"☎️ Новые контакты:"}
    bot.send_message(call.message.chat.id, prompts.get(field,'Введите значение:'))
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
        elif field=='contacts':
            # store only phone string for now
            fields['contact_phone']=txt
    except Exception:
        bot.send_message(message.chat.id, T(lang,'err_value')); return
    ok=db.update_site(site_id, fields)
    temp.pop(uid,None); bot.delete_state(uid, message.chat.id)
    bot.send_message(message.chat.id, "✅ Обновлено." if ok else "❌ Не удалось обновить.")
    # show site card
    s=db.get_site(site_id)
    if s:
        contacts=(s.get('contact_phone') or '—')
        bot.send_message(message.chat.id, T(lang,'admin_site_card',
                                           sid=s['id'], address=s['address'],
                                           area=f"{fmt_area(s.get('area_sotki'))} сот.",
                                           contacts=contacts,
                                           last=fmt_date_display(s.get('last_service_at')),
                                           n=int(s.get('service_count') or 0)),
                         reply_markup=admin_site_actions_kb(site_id, T, lang))
    else:
        show_admin_menu(message.chat.id, uid)

@bot.callback_query_handler(func=lambda c: c.data.startswith('aorder_edit:'))
def aorder_edit(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    oid=int(call.data.split(':')[1])
    bot.send_message(call.message.chat.id, "Что изменить в заказе?", reply_markup=admin_edit_order_kb(oid, T, lang))
    safe_answer(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith('aorder_edit_field:'))
def aorder_edit_field(call: types.CallbackQuery):
    if not require_admin_call(call): return
    uid=call.from_user.id; lang=get_lang(uid)
    _, _, field, oid = call.data.split(':')
    oid=int(oid)
    temp[uid]={'flow':'edit_order','order_id':oid,'field':field}
    bot.set_state(uid, AdminEditServiceOrderStates.field, call.message.chat.id)
    prompts={'area':"📏 Новая площадь (сотки):",
             'tariff':"💵 Новый тариф (руб/сот):",
             'date':"📅 Новая дата:",
             'duration':"⏳ Новая длительность:",
             'notes':"📝 Новые заметки:"}
    bot.send_message(call.message.chat.id, prompts.get(field,'Введите значение:'))
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
        elif field=='date':
            dt=parse_date(txt)
            if not dt: raise ValueError
            fields['service_at']=dt.strftime('%Y-%m-%d')
        elif field=='duration':
            d=parse_duration(txt)
            if not d: raise ValueError
            fields['duration']=d
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
        text=T(lang,'admin_order_card',
               oid=o['id'],
               address=site['address'] if site else '—',
               area=fmt_area(o.get('area_sotki')),
               tariff=o.get('tariff') or 0,
               date=fmt_date_display(o.get('service_at')),
               dur=o.get('duration') or '—',
               notes=o.get('notes') or '—')
        bot.send_message(message.chat.id, text, reply_markup=admin_order_actions_kb(oid, T, lang))
    else:
        show_admin_menu(message.chat.id, uid)

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
@bot.callback_query_handler(func=lambda c: c.data=='main_menu')
def legacy_main_menu(call: types.CallbackQuery):
    if not require_admin_call(call): return
    lang=get_lang(call.from_user.id)
    bot.send_message(call.message.chat.id, T(lang,'main_menu'), reply_markup=main_menu(T,lang))
    safe_answer(call)

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

# ---------------- Run ----------------
if __name__ == '__main__':
    print("Bot running...")
    try:
        # Fix 409 conflict: if webhook was set, remove it before polling
        bot.remove_webhook()
    except Exception as e:
        logging.error(f"remove_webhook: {e}")
    bot.infinity_polling(skip_pending=True)
