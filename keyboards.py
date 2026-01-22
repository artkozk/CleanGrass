from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from typing import List, Tuple, Optional, Dict

# ---- Existing (legacy) ----
def main_menu(t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(lang, 'new_order'), callback_data="new_order"),
        InlineKeyboardButton(t(lang, 'history'), callback_data="order_history"),
        InlineKeyboardButton(t(lang, 'stats'), callback_data="statistics"),
        InlineKeyboardButton(t(lang, 'settings'), callback_data="settings"),
    )
    return kb

def cancel_kb(t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(t(lang, 'cancel'), callback_data="cancel"))
    return kb

def tariffs_kb(t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        *[InlineKeyboardButton(f"{tariff}", callback_data=f"tariff_{tariff}") 
          for tariff in [300, 350, 400, 450, 500]],
        InlineKeyboardButton(t(lang, 'other_tariff'), callback_data="custom_tariff"),
        InlineKeyboardButton(t(lang, 'cancel'), callback_data="cancel")
    )
    return kb

def addresses_kb(addresses: List[Tuple[str, int]], t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for address, count in addresses:
        # NOTE: address can contain underscores; callback_data limit is 64.
        # Keep legacy behaviour for now.
        kb.add(InlineKeyboardButton(f"📍 {address} ({count}x)", callback_data=f"address_{address}"))
    kb.add(
        InlineKeyboardButton("📝", callback_data="new_address"),
        InlineKeyboardButton(t(lang, 'cancel'), callback_data="cancel")
    )
    return kb

def confirm_kb(t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(lang, 'confirm'), callback_data="confirm"),
        InlineKeyboardButton(t(lang, 'cancel'), callback_data="cancel")
    )
    return kb

def period_kb(action: str, t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton(t(lang, 'period_week'), callback_data=f"{action}_week"),
        InlineKeyboardButton(t(lang, 'period_month'), callback_data=f"{action}_month"),
        InlineKeyboardButton(t(lang, 'period_year'), callback_data=f"{action}_year"),
        InlineKeyboardButton(t(lang, 'period_range'), callback_data=f"{action}_range"),
        InlineKeyboardButton(t(lang, 'period_all'), callback_data=f"{action}_all"),
        InlineKeyboardButton(t(lang, 'back'), callback_data="main_menu"),
        InlineKeyboardButton(t(lang, 'cancel'), callback_data="cancel"),
    )
    return kb

def order_actions_kb(order_id: int, t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton(t(lang, 'edit'), callback_data=f"edit_{order_id}"),
        InlineKeyboardButton(t(lang, 'delete'), callback_data=f"delete_{order_id}"),
        InlineKeyboardButton(t(lang, 'back'), callback_data="order_history"),
    )
    return kb

def delete_confirm_kb(order_id: int, t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅", callback_data=f"confirm_delete_{order_id}"),
        InlineKeyboardButton("❌", callback_data=f"order_details_{order_id}")
    )
    return kb

def stats_filters_kb(t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(lang, 'flt_tariff'), callback_data="sflt_tariff"),
        InlineKeyboardButton(t(lang, 'flt_area'), callback_data="sflt_area"),
        InlineKeyboardButton(t(lang, 'flt_dates'), callback_data="sflt_dates"),
    )
    kb.add(
        InlineKeyboardButton(t(lang, 'build_report'), callback_data="sflt_build"),
        InlineKeyboardButton(t(lang, 'back'), callback_data="main_menu"),
    )
    return kb

def edit_order_kb(order_id: int, t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📏", callback_data=f"edit_area_{order_id}"),
        InlineKeyboardButton("💵", callback_data=f"edit_tariff_{order_id}"),
        InlineKeyboardButton("📅", callback_data=f"edit_date_{order_id}"),
        InlineKeyboardButton("⏳", callback_data=f"edit_duration_{order_id}"),
        InlineKeyboardButton("📝", callback_data=f"edit_notes_{order_id}"),
    )
    kb.add(InlineKeyboardButton(t(lang, 'apply'), callback_data=f"order_details_{order_id}"))
    return kb

def settings_kb(t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(lang, 'lang_ru'), callback_data="set_lang_ru"),
        InlineKeyboardButton(t(lang, 'lang_en'), callback_data="set_lang_en"),
    )
    kb.add(InlineKeyboardButton(t(lang, 'back'), callback_data="main_menu"))
    return kb

# ---- NEW: client/admin ----

def client_start_kb(sites: List[Dict], t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    if sites:
        for s in sites[:30]:
            kb.add(InlineKeyboardButton(f"📍 {s['address']}", callback_data=f"csitepick:{s['id']}"))
    kb.add(InlineKeyboardButton(t(lang,'client_new_request'), callback_data="cnewreq"))
    if not sites:
        kb.add(InlineKeyboardButton(t(lang,'admin_need_reg'), callback_data="noop"))
    return kb

def client_site_nav_kb(site_id:int, idx:int, total:int, has_photos:bool, t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=3)
    prev_cb = f"csite:{site_id}:{idx-1}" if idx>0 else "noop"
    next_cb = f"csite:{site_id}:{idx+1}" if idx<total-1 else "noop"
    kb.add(
        InlineKeyboardButton("⬅️", callback_data=prev_cb),
        InlineKeyboardButton(t(lang,'client_order_again'), callback_data=f"creq:{site_id}"),
        InlineKeyboardButton("➡️", callback_data=next_cb),
    )
    if has_photos:
        kb.add(InlineKeyboardButton(t(lang,'client_show_photos'), callback_data=f"cphotos:{site_id}:{idx}"))
    kb.add(InlineKeyboardButton(t(lang,'client_back_sites'), callback_data="cback_sites"))
    return kb

def client_contacts_reply_kb(t, lang) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("📞 Отправить номер", request_contact=True))
    kb.add(KeyboardButton(t(lang,'cancel')))
    return kb

def admin_menu_kb(new_count:int, t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(lang,'admin_create_order'), callback_data="aneworder"),
        InlineKeyboardButton(t(lang,'admin_archive'), callback_data="aarchive"),
        InlineKeyboardButton(f"{t(lang,'admin_notifications')} ({new_count})", callback_data="anotifs"),
        InlineKeyboardButton(t(lang,'settings'), callback_data="settings"),
    )
    return kb

def admin_requests_list_kb(requests: List[Dict], t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for r in requests[:30]:
        kb.add(InlineKeyboardButton(f"🆕 #{r['id']} • {r['address']}", callback_data=f"areq:{r['id']}"))
    kb.add(InlineKeyboardButton(t(lang,'admin_back_menu'), callback_data="amenu"))
    return kb

def admin_request_actions_kb(req_id:int, t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(lang,'admin_take'), callback_data=f"areq_take:{req_id}"),
        InlineKeyboardButton(t(lang,'admin_done'), callback_data=f"areq_done:{req_id}"),
        InlineKeyboardButton(t(lang,'admin_reject'), callback_data=f"areq_reject:{req_id}"),
    )
    kb.add(InlineKeyboardButton(t(lang,'admin_back_menu'), callback_data="anotifs"))
    return kb

def admin_archive_kb(t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(lang,'find_orders'), callback_data="afind"),
        InlineKeyboardButton(t(lang,'stats_all'), callback_data="astats_all"),
    )
    kb.add(InlineKeyboardButton(t(lang,'admin_back_menu'), callback_data="amenu"))
    return kb

def admin_sites_kb(sites: List[Dict], t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for s in sites[:30]:
        kb.add(InlineKeyboardButton(f"📍 {s['address']}", callback_data=f"asite:{s['id']}"))
    kb.add(InlineKeyboardButton(t(lang,'admin_back_menu'), callback_data="amenu"))
    return kb

def admin_site_actions_kb(site_id:int, t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(t(lang,'admin_create_order'), callback_data=f"aneworder_site:{site_id}"),
        InlineKeyboardButton(t(lang,'admin_site_orders'), callback_data=f"asite_orders:{site_id}"),
        InlineKeyboardButton(t(lang,'admin_site_edit'), callback_data=f"asite_edit:{site_id}"),
        InlineKeyboardButton(t(lang,'admin_site_delete_all'), callback_data=f"adelall:{site_id}"),
        InlineKeyboardButton(t(lang,'admin_back_menu'), callback_data="aarchive"),
    )
    return kb

def admin_orders_list_kb(site_id:int, orders: List[Dict], t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    for o in orders[:30]:
        kb.add(InlineKeyboardButton(f"🧾 #{o['id']} • {o['service_at']}", callback_data=f"aorder:{o['id']}"))
    kb.add(InlineKeyboardButton(t(lang,'back'), callback_data=f"asite:{site_id}"))
    return kb

def admin_order_actions_kb(order_id:int, t, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(lang,'admin_edit_order'), callback_data=f"aorder_edit:{order_id}"),
        InlineKeyboardButton(t(lang,'admin_delete_order'), callback_data=f"adel:{order_id}"),
    )
    kb.add(InlineKeyboardButton(t(lang,'admin_back_menu'), callback_data="aarchive"))
    return kb

def admin_edit_site_kb(site_id:int, t, lang) -> InlineKeyboardMarkup:
    kb=InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📍 Адрес", callback_data=f"asite_edit_field:address:{site_id}"),
        InlineKeyboardButton("📏 Сотки", callback_data=f"asite_edit_field:area:{site_id}"),
        InlineKeyboardButton("☎️ Контакты", callback_data=f"asite_edit_field:contacts:{site_id}"),
    )
    kb.add(InlineKeyboardButton(t(lang,'back'), callback_data=f"asite:{site_id}"))
    return kb

def admin_edit_order_kb(order_id:int, t, lang) -> InlineKeyboardMarkup:
    kb=InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📏", callback_data=f"aorder_edit_field:area:{order_id}"),
        InlineKeyboardButton("💵", callback_data=f"aorder_edit_field:tariff:{order_id}"),
        InlineKeyboardButton("📅", callback_data=f"aorder_edit_field:date:{order_id}"),
        InlineKeyboardButton("⏳", callback_data=f"aorder_edit_field:duration:{order_id}"),
        InlineKeyboardButton("📝", callback_data=f"aorder_edit_field:notes:{order_id}"),
    )
    kb.add(InlineKeyboardButton(t(lang,'back'), callback_data=f"aorder:{order_id}"))
    return kb

def admin_inline_done_kb(done_cb:str, t, lang) -> InlineKeyboardMarkup:
    kb=InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(t(lang,'admin_photos_done'), callback_data=done_cb))
    kb.add(InlineKeyboardButton(t(lang,'cancel'), callback_data="amenu"))
    return kb
