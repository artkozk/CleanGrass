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
    new_site_contacts = State()
    area = State()
    tariff = State()
    date = State()
    duration = State()
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
