import os
from dotenv import load_dotenv

load_dotenv()

# Token: set env BOT_TOKEN, do NOT hardcode in repo
BOT_TOKEN = os.getenv('BOT_TOKEN', '')

# Optional: seed admins via env (comma-separated telegram ids)
ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip().isdigit()]

# Admin registration password (/adminreg)
ADMIN_PASSWORD = os.getenv('BOT_ADMIN_PASSWORD', '123')

DB_NAME = os.getenv('DB_NAME', 'grass_orders.db')

# Часовой пояс и час утреннего дайджеста (напоминания + бэкап базы)
BOT_TZ = os.getenv('BOT_TZ', 'Europe/Moscow')
DIGEST_HOUR = int(os.getenv('DIGEST_HOUR', '8'))

# i18n texts (existing)
LANG = {
  'ru': {
    'start': "🌱 Добро пожаловать! Это бот учёта заказов покоса.",
    'main_menu': "Главное меню:",
    'new_order': "🌱 Новый заказ",
    'history': "📜 История заказов",
    'stats': "📊 Статистика",
    'settings': "⚙️ Настройки",
    'cancel': "❌ Отменить действие",
    'no_orders': "📭 Список заказов пуст",
    'enter_address': "🌿 Введите адрес покоса:",
    'choose_address': "🌿 Выберите адрес из списка или введите новый:",
    'enter_area': "📏 Введите площадь участка в сотках (например: 2.5):",
    'enter_tariff': "💰 Введите ваш тариф (руб/сотку):",
    'choose_tariff': "💰 Выберите тариф:",
    'other_tariff': "📝 Другой тариф",
    'enter_date': "📅 Введите дату (любой формат, например: 15.08.2025, 150825):",
    'enter_duration': "⏳ Введите длительность (примеры: 2.5, 2ч 30мин, 2:30, 2 40):",
    'before_photo': "📸 Пришлите фото ДО покоса (или нажмите 'Пропустить'):",
    'after_photo': "📸 Пришлите фото ПОСЛЕ покоса (или нажмите 'Пропустить'):",
    'notes': "📝 Введите заметки (или нажмите 'Пропустить'):",
    'skip': "Пропустить",
    'confirm': "✅ Подтвердить",
    'confirm_summary_title': "📌 <b>Сводка заказа:</b>",
    'summary_address': "📍 Адрес: {address}",
    'summary_area': "📏 Площадь: <b>{area}</b> сот.",
    'summary_tariff': "💰 Тариф: {tariff} руб/сотку",
    'summary_date': "📅 Дата: {date}",
    'summary_duration': "⏳ Длительность: <b>{duration}</b>",
    'summary_total': "💵 Итого: <b>{total}</b> руб",
    'summary_notes': "📝 Заметки: {notes}",
    'order_created': "✅ Заказ #{oid} успешно создан!",
    'order_deleted': "🗑️ Заказ успешно удалён!",
    'delete_error': "❌ Ошибка при удалении заказа.",
    'history_period': "📜 Выберите период для просмотра истории:",
    'stats_period': "📊 Выберите период для статистики:",
    'period_week': "📅 Неделя",
    'period_month': "📅 Месяц",
    'period_year': "📅 Год",
    'period_all': "📅 Все время",
    'period_range': "🗓️ Выбрать даты",
    'range_from': "📅 Введите дату <b>ОТ</b> (любой формат):",
    'range_to': "📅 Введите дату <b>ДО</b> (любой формат):",
    'range_applied': "✅ Применён период: {dfrom} — {dto}",
    'details_cmd': "🆔 Детали: <code>/order_{oid}</code>",
    'order_not_found': "❌ Заказ не найден",
    'back': "↩️ Назад",
    'delete': "🗑️ Удалить",
    'edit': "✏️ Изменить",
    'apply': "✅ Готово",
    'edit_which': "Что изменить в заказе #{oid}?",
    'edit_area': "📏 Введите новую площадь (сотки, например 3.5):",
    'edit_tariff': "💵 Введите новый тариф (целое число):",
    'edit_date': "📅 Введите новую дату (любой формат):",
    'edit_duration': "⏳ Введите новую длительность (например 2:30 или 2.5):",
    'edit_notes': "📝 Введите новые заметки (можно оставить пусто):",
    'edited_ok': "✏️ Заказ обновлён.",
    'stats_adv': "🧮 Тонкая статистика",
    'stats_filters_title': "🧮 Тонкая статистика — выберите фильтры или сформируйте отчёт:",
    'flt_tariff': "💵 Тариф",
    'flt_area': "📏 Площадь",
    'flt_dates': "📅 Период",
    'build_report': "🧮 Сформировать отчёт",
    'set_tariff_range': "💵 Введите диапазон тарифа руб/сотку (пример: 300-500):",
    'set_area_range': "📏 Введите диапазон площади (сотки, пример: 0-20):",
    'stats_header': "📊 Статистика ({period}):",
    'stats_items_header': "🔽 Список заказов:",
    'stats_totals': "🔢 Заказов: <b>{orders}</b>\n📏 Общая площадь: <b>{area:.2f}</b> сот.\n💰 Заработок: <b>{income}</b> руб\n📈 Средний заказ: <b>{avg_price}</b> руб\n🌱 Средняя площадь: <b>{avg_area:.2f}</b> сот.\n💵 Средний тариф: <b>{avg_tariff:.2f}</b> руб/сотку",
    'settings_title': "⚙️ Настройки",
    'lang': "Язык",
    'lang_ru': "🇷🇺 Русский",
    'lang_en': "🇬🇧 English",
    'saved': "✅ Сохранено.",
    'reuse_prompt': "🔁 Подставить данные из последнего заказа по этому адресу? ({area} сот., {tariff} руб/сот.)",
    'yes': "Да",
    'no': "Нет",
    'err_value': "❌ Некорректное значение. Попробуйте ещё раз.",
    'err_date': "❌ Не удалось распознать дату. Примеры: 15.08.2025, 150825",
    'err_duration': "❌ Неверный формат. Примеры: 2.5, 2ч 30мин, 2:30, 2 40",

    # --- NEW: client/admin texts (RU only for now; EN falls back) ---
    'client_start': "Привет, {name}! Ты можешь заказать услуги покоса.",
    'client_choose_site': "Выбери участок:",
    'client_new_request': "🧾 Создать новый заказ",
    'client_sites_empty': "Пока нет участков. Создай первый заказ.",
    'client_enter_contacts': "Введите контактные данные (телефон/как связаться):",
    'client_enter_comment': "Комментарий (необязательно):",
    'client_request_sent': "✅ Заявка отправлена. Я уведомил исполнителя.",
    'client_site_card_title': "🌿 Участок",
    'client_last_service': "Последний покос: <b>{date}</b>",
    'client_service_count': "Сколько раз косили: <b>{n}</b>",
    'client_history_empty': "История по этому участку пока пустая.",
    'client_order_card': "🧾 Покос {idx}/{total}\n📅 {date}",
    'client_show_photos': "📸 Показать фото",
    'client_order_again': "🟩 Заказать покос",
    'client_back_sites': "↩️ К списку участков",

    'admin_need_reg': "",
    'admin_enter_password': "Введи пароль администратора:",
    'admin_bad_password': "❌ Неверный пароль.",
    'admin_ok': "✅ Админ доступ включён.",
    'admin_menu': "Админ-меню:",
    'admin_create_order': "🧾 Создать новый заказ",
    'admin_archive': "🗂 Архив заказов",
    'admin_notifications': "🔔 Уведомления",
    'admin_notifs_empty': "Новых заявок нет.",
    'admin_request_card': "🆕 Заявка #{rid}\n👤 {client}\n📍 {address}\n📏 {area}\n☎️ {contacts}\n💬 {comment}\n🕒 {created}",
    'admin_take': "Взять в работу",
    'admin_done': "Выполнено",
    'admin_reject': "Отклонить",
    'admin_back_menu': "↩️ В меню",
    'admin_search_site': "Введите часть адреса, чтобы найти участок (или отправьте '-' чтобы создать новый):",
    'admin_pick_site': "Выбери участок:",
    'admin_new_site_address': "Введите адрес участка:",
    'admin_new_site_area': "Введите площадь участка (сотки):",
    'admin_new_site_contacts': "Контакты клиента (имя/телефон):",
    'admin_order_photos': "Пришлите фотоотчёт (можно несколько). Когда закончите — нажмите «Готово».",
    'admin_photos_done': "Готово",
    'admin_site_card': "🏡 Участок #{sid}\n📍 {address}\n📏 {area}\n☎️ {contacts}\nПоследний покос: {last}\nКосили: {n} раз",
    'admin_site_edit': "✏️ Изменить участок",
    'admin_site_orders': "📜 История участка",
    'admin_site_delete_all': "🗑 Удалить все покосы по адресу",
    'admin_order_card': "🧾 Заказ #{oid}\n📍 {address}\n📏 {area} сот\n💵 {tariff} руб/сот\n📅 {date}\n⏳ {dur}\n💬 {notes}",
    'admin_edit_order': "✏️ Изменить заказ",
    'admin_delete_order': "🗑 Удалить заказ",
    'admin_confirm_phrase': "Напиши <b>да, хочу удалить</b> чтобы подтвердить удаление:",
    'admin_deleted_all': "🗑 Удалено: {n} заказ(ов).",

    'find_orders': "🔎 Найти заказ",
    'find_enter_address': "Адрес (можно часть, или '-' чтобы пропустить):",
    'find_enter_date_from': "Дата ОТ (или '-' чтобы пропустить):",
    'find_enter_date_to': "Дата ДО (или '-' чтобы пропустить):",
    'find_enter_price_min': "Сумма ОТ (или '-' чтобы пропустить):",
    'find_enter_price_max': "Сумма ДО (или '-' чтобы пропустить):",
    'find_results_empty': "Ничего не найдено.",
    'stats_all': "Статистика по всем заказам",
  },
  'en': {}
}

# Copy EN from previous if missing - keep simple fallback
from copy import deepcopy
if not LANG.get('en'):
    LANG['en'] = deepcopy(LANG['ru'])

def T(lang: str, key: str, **kwargs) -> str:
    lang = lang if lang in LANG else 'ru'
    s = LANG[lang].get(key, LANG['ru'].get(key, key))
    return s.format(**kwargs) if kwargs else s
