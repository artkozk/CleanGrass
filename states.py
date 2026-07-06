from telebot.handler_backends import StatesGroup, State

# Legacy executor flow (kept)
class OrderStates(StatesGroup):
    address = State()
    area = State()
    tariff = State()
    date = State()
    duration = State()
    before_photo = State()
    after_photo = State()
    notes = State()
    confirm = State()

class DeleteStates(StatesGroup):
    confirmation = State()

class HistoryRangeStates(StatesGroup):
    date_from = State()
    date_to = State()

class StatsFilterStates(StatesGroup):
    tariff = State()
    area = State()
    date_from = State()
    date_to = State()

class EditOrderStates(StatesGroup):
    field = State()

# --- NEW: roles ---
class AdminRegStates(StatesGroup):
    password = State()

class ClientRequestStates(StatesGroup):
    address = State()
    area = State()
    contacts = State()
    comment = State()
    confirm = State()

class AdminOrderStates(StatesGroup):
    site_search = State()
    new_site_address = State()
    new_site_area = State()
    new_site_contacts = State()  # legacy, не используется в новом флоу
    new_site_name = State()
    new_site_phone = State()
    work_type = State()      # 🌱 покос / 🔨 другая работа (callback)
    work_name = State()      # название другой работы
    amount = State()         # фиксированная сумма другой работы
    zones = State()          # выбор зон галочками (callback)
    zone_new_name = State()  # добавление новой зоны на ходу
    zone_new_area = State()
    manual_area = State()    # ввод площади вручную без зон
    area = State()           # legacy, не используется в новом флоу
    tariff = State()
    date = State()
    duration = State()
    helper = State()         # был ли помощник (callback)
    helper_name = State()
    helper_pay = State()
    dad = State()            # папина доля для другой работы (callback)
    notes = State()
    photos = State()
    confirm = State()

class AdminDeleteAllStates(StatesGroup):
    confirm_phrase = State()

class AdminFindStates(StatesGroup):
    address = State()
    date_from = State()
    date_to = State()
    price_min = State()
    price_max = State()

class AdminEditSiteStates(StatesGroup):
    field = State()

class AdminEditServiceOrderStates(StatesGroup):
    field = State()

class AdminRemindStates(StatesGroup):
    snooze_days = State()  # «отложить на N дней»
