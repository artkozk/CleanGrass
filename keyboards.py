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

def admin_menu_kb(new_count:int, t, lang, remind_count:int=0) -> InlineKeyboardMarkup:
    """Минимальное меню: только быстрые действия. Срочное (напоминания/заявки)
    появляется отдельным рядом, лишь когда есть что показать. Остальное — в «Ещё»."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("🧾 Новый заказ", callback_data="aneworder"))
    kb.add(
        InlineKeyboardButton("🏡 Участки", callback_data="asites"),
        InlineKeyboardButton("📊 Статистика", callback_data="astats_menu"),
    )
    alerts=[]
    if remind_count:
        alerts.append(InlineKeyboardButton(f"⏰ Напоминания ({remind_count})", callback_data="aremind"))
    if new_count:
        alerts.append(InlineKeyboardButton(f"🔔 Заявки ({new_count})", callback_data="anotifs"))
    if alerts:
        kb.add(*alerts)
    kb.add(InlineKeyboardButton("⋯ Ещё", callback_data="amore"))
    return kb

def admin_more_kb(t, lang) -> InlineKeyboardMarkup:
    """Раздел «Ещё»: всё нечастое."""
    kb=InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔎 Найти заказ", callback_data="afind"),
        InlineKeyboardButton("🔔 Заявки", callback_data="anotifs"),
        InlineKeyboardButton("⏰ Напоминания", callback_data="aremind"),
        InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
    )
    kb.add(InlineKeyboardButton("↩️ В меню", callback_data="amenu"))
    return kb

def site_pick_kb(sites) -> InlineKeyboardMarkup:
    """Выбор участка для нового заказа: последние кнопками, поиск текстом."""
    kb = InlineKeyboardMarkup(row_width=1)
    for s in sites[:10]:
        kb.add(InlineKeyboardButton(f"📍 {s['address']}", callback_data=f"aneworder_site:{s['id']}"))
    kb.add(InlineKeyboardButton("➕ Новый участок", callback_data="aneworder_newsite"))
    kb.add(InlineKeyboardButton("↩️ В меню", callback_data="amenu"))
    return kb

def sites_browse_kb(sites) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    for s in sites[:20]:
        kb.add(InlineKeyboardButton(f"📍 {s['address']}", callback_data=f"asite:{s['id']}"))
    kb.add(InlineKeyboardButton("➕ Новый участок", callback_data="anewsite_only"))
    kb.add(InlineKeyboardButton("↩️ В меню", callback_data="amenu"))
    return kb

def search_results_kb(sites, pick_prefix:str, back_cb:str="amenu", new_site_cb:str="aneworder_newsite") -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    for s in sites[:20]:
        kb.add(InlineKeyboardButton(f"📍 {s['address']}", callback_data=f"{pick_prefix}:{s['id']}"))
    kb.add(InlineKeyboardButton("➕ Новый участок", callback_data=new_site_cb))
    kb.add(InlineKeyboardButton("↩️ В меню", callback_data=back_cb))
    return kb

def zones_manage_kb(zones, site_id:int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    for z in zones[:30]:
        kb.add(InlineKeyboardButton(f"🗑 {z['name']} ({z['area_sotki']:g} сот)", callback_data=f"azdelq:{z['id']}"))
    kb.add(InlineKeyboardButton("➕ Добавить зону", callback_data=f"azadd:{site_id}"))
    kb.add(InlineKeyboardButton("↩️ К участку", callback_data=f"asite:{site_id}"))
    return kb

def confirm_action_kb(yes_label:str, yes_cb:str, back_cb:str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(yes_label, callback_data=yes_cb),
        InlineKeyboardButton("↩️ Отмена", callback_data=back_cb),
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
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(t(lang,'admin_create_order'), callback_data=f"aneworder_site:{site_id}"),
        InlineKeyboardButton(t(lang,'admin_site_orders'), callback_data=f"asite_orders:{site_id}"),
        InlineKeyboardButton("🌱 Зоны", callback_data=f"azones:{site_id}"),
        InlineKeyboardButton(t(lang,'admin_site_edit'), callback_data=f"asite_edit:{site_id}"),
        InlineKeyboardButton(t(lang,'admin_site_delete_all'), callback_data=f"adelall:{site_id}"),
        InlineKeyboardButton("🗑 Удалить участок", callback_data=f"asitedel:{site_id}"),
    )
    kb.add(InlineKeyboardButton("↩️ К участкам", callback_data="asites"))
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
    kb.add(InlineKeyboardButton(t(lang,'admin_back_menu'), callback_data="amenu"))
    return kb

def admin_edit_site_kb(site_id:int, t, lang) -> InlineKeyboardMarkup:
    kb=InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📍 Адрес", callback_data=f"asite_edit_field:address:{site_id}"),
        InlineKeyboardButton("📏 Сотки", callback_data=f"asite_edit_field:area:{site_id}"),
        InlineKeyboardButton("👤 Имя клиента", callback_data=f"asite_edit_field:name:{site_id}"),
        InlineKeyboardButton("☎️ Телефон", callback_data=f"asite_edit_field:contacts:{site_id}"),
        InlineKeyboardButton("⏰ Интервал напоминаний", callback_data=f"asite_edit_field:remind:{site_id}"),
    )
    kb.add(InlineKeyboardButton(t(lang,'back'), callback_data=f"asite:{site_id}"))
    return kb

def admin_edit_order_kb(order_id:int, t, lang, work_type:str='mow') -> InlineKeyboardMarkup:
    kb=InlineKeyboardMarkup(row_width=2)
    if (work_type or 'mow') == 'other':
        # другая работа: сумма вместо соток/тарифа
        kb.add(InlineKeyboardButton("💰 Сумма", callback_data=f"aorder_edit_field:amount:{order_id}"))
    else:
        # покос: площадь и тариф
        kb.add(
            InlineKeyboardButton("📏 Сотки", callback_data=f"aorder_edit_field:area:{order_id}"),
            InlineKeyboardButton("💵 Тариф", callback_data=f"aorder_edit_field:tariff:{order_id}"),
        )
    kb.add(
        InlineKeyboardButton("💸 Заплатили", callback_data=f"aorder_edit_field:paid:{order_id}"),
        InlineKeyboardButton("🤝 Помощнику", callback_data=f"aorder_edit_field:helper:{order_id}"),
        InlineKeyboardButton("📅 Дата", callback_data=f"aorder_edit_field:date:{order_id}"),
        InlineKeyboardButton("⏳ Время", callback_data=f"aorder_edit_field:duration:{order_id}"),
        InlineKeyboardButton("📝 Заметки", callback_data=f"aorder_edit_field:notes:{order_id}"),
    )
    kb.add(InlineKeyboardButton(t(lang,'back'), callback_data=f"aorder:{order_id}"))
    return kb

def admin_inline_done_kb(done_cb:str, t, lang) -> InlineKeyboardMarkup:
    kb=InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ " + t(lang,'admin_photos_done'), callback_data=done_cb))
    _nav_row(kb)
    return kb

# ---- NEW: тип работы, зоны, помощник, папина доля, дата/тариф кнопками ----

def _nav_row(kb: InlineKeyboardMarkup, back: bool = True):
    """Общий ряд навигации шага заказа: Назад + Отмена."""
    if back:
        kb.add(
            InlineKeyboardButton("⬅️ Назад", callback_data="aback"),
            InlineKeyboardButton("❌ Отмена", callback_data="amenu"),
        )
    else:
        kb.add(InlineKeyboardButton("❌ Отмена", callback_data="amenu"))

def work_type_kb() -> InlineKeyboardMarkup:
    kb=InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🌱 Покос", callback_data="awt:mow"),
        InlineKeyboardButton("🔨 Другая работа", callback_data="awt:other"),
    )
    _nav_row(kb, back=False)
    return kb

def zones_kb(zones, selected_ids, site_area, sel_sum) -> InlineKeyboardMarkup:
    """Выбор зон галочками. zones — список dict(id,name,area_sotki)."""
    kb=InlineKeyboardMarkup(row_width=1)
    for z in zones[:30]:
        mark = "✅" if z['id'] in selected_ids else "⬜"
        area = f"{z['area_sotki']:g}"
        kb.add(InlineKeyboardButton(f"{mark} {z['name']} ({area} сот)", callback_data=f"azt:{z['id']}"))
    whole = f" ({site_area:g} сот)" if site_area else ""
    kb.add(InlineKeyboardButton(f"🌍 Всё целиком{whole}", callback_data="azall"))
    kb.add(InlineKeyboardButton("➕ Новая зона", callback_data="aznew"))
    kb.add(InlineKeyboardButton("✍️ Ввести площадь вручную", callback_data="azman"))
    if selected_ids:
        kb.add(InlineKeyboardButton(f"▶️ Далее ({sel_sum:g} сот)", callback_data="azok"))
    _nav_row(kb)
    return kb

DEFAULT_TARIFFS = [300, 350, 400, 450, 500]

def tariff_quick_kb(tariffs) -> InlineKeyboardMarkup:
    kb=InlineKeyboardMarkup(row_width=3)
    vals = tariffs[:6] if tariffs else DEFAULT_TARIFFS
    kb.add(*[InlineKeyboardButton(f"{v} руб", callback_data=f"atrf:{v}") for v in vals])
    _nav_row(kb)
    return kb

def date_quick_kb() -> InlineKeyboardMarkup:
    kb=InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📅 Сегодня", callback_data="adate:today"),
        InlineKeyboardButton("📅 Вчера", callback_data="adate:yesterday"),
    )
    _nav_row(kb)
    return kb

def paid_quick_kb(calc: float) -> InlineKeyboardMarkup:
    """Фактическая оплата: ровно по расчёту или округления, свою сумму — текстом."""
    kb=InlineKeyboardMarkup(row_width=1)
    calc=round(float(calc), 2)
    variants=[]
    exact=int(calc) if calc==int(calc) else calc
    variants.append((f"✅ Ровно {exact:g} руб", calc))
    down=(int(calc)//100)*100
    up=down+100 if calc>down else down
    for v in (down, up):
        if v>0 and round(float(v),2)!=calc and all(round(float(v),2)!=x[1] for x in variants):
            variants.append((f"💰 {v} руб", float(v)))
    for label, val in variants:
        kb.add(InlineKeyboardButton(label, callback_data=f"apaid:{val:g}"))
    _nav_row(kb)
    return kb

def duration_quick_kb() -> InlineKeyboardMarkup:
    """Быстрые кнопки длительности (значение — минуты)."""
    kb=InlineKeyboardMarkup(row_width=3)
    presets = [("30мин",30), ("1ч",60), ("1.5ч",90), ("2ч",120), ("2.5ч",150), ("3ч",180)]
    kb.add(*[InlineKeyboardButton(label, callback_data=f"adur:{mins}") for label, mins in presets])
    _nav_row(kb)
    return kb

def helper_yn_kb() -> InlineKeyboardMarkup:
    kb=InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🤝 Был", callback_data="ahelp:yes"),
        InlineKeyboardButton("🙅 Не было", callback_data="ahelp:no"),
    )
    _nav_row(kb)
    return kb

def helper_names_kb(names) -> InlineKeyboardMarkup:
    """Имена — по индексу, чтобы не упираться в лимит callback_data."""
    kb=InlineKeyboardMarkup(row_width=2)
    if names:
        kb.add(*[InlineKeyboardButton(n, callback_data=f"ahname:{i}") for i, n in enumerate(names[:8])])
    _nav_row(kb)
    return kb

def dad_share_kb() -> InlineKeyboardMarkup:
    kb=InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("👨 Папина доля: да", callback_data="adad:yes"),
        InlineKeyboardButton("Без папы", callback_data="adad:no"),
    )
    _nav_row(kb)
    return kb

def skip_kb(cb:str="askip", back:bool=False) -> InlineKeyboardMarkup:
    kb=InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⏭ Пропустить", callback_data=cb))
    _nav_row(kb, back=back)
    return kb

def step_nav_kb(back:bool=True) -> InlineKeyboardMarkup:
    """Клавиатура для текстовых шагов заказа: Назад + Отмена."""
    kb=InlineKeyboardMarkup()
    _nav_row(kb, back=back)
    return kb

def prompt_cancel_kb(back_cb:str, label:str="↩️ Отмена") -> InlineKeyboardMarkup:
    """Одна кнопка возврата для одиночных текстовых промптов (редактирование и т.п.)."""
    kb=InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(label, callback_data=back_cb))
    return kb

# ---- NEW: статистика и напоминания ----

def stats_period_kb() -> InlineKeyboardMarkup:
    kb=InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📅 Неделя", callback_data="astats:week"),
        InlineKeyboardButton("📅 Месяц", callback_data="astats:month"),
        InlineKeyboardButton("📅 Год", callback_data="astats:year"),
        InlineKeyboardButton("📅 Всё время", callback_data="astats:all"),
    )
    kb.add(InlineKeyboardButton("↩️ В меню", callback_data="amenu"))
    return kb

def remind_actions_kb(site_id:int) -> InlineKeyboardMarkup:
    kb=InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📞 Позвонил — покос назначен", callback_data=f"armd_call:{site_id}"),
        InlineKeyboardButton("🗓 Отложить на месяц", callback_data=f"armd_month:{site_id}"),
        InlineKeyboardButton("⏲ Отложить на N дней", callback_data=f"armd_days:{site_id}"),
    )
    return kb
