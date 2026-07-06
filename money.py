"""Чистая логика денег и времени: без telebot и без базы, чтобы легко тестировать."""
import re
from typing import Dict, Optional

MOW_PCT = 0.15        # процент с покоса (в него входит папина доля)
OTHER_PCT_DAD = 0.15  # другая работа с папиной долей
OTHER_PCT_NO_DAD = 0.10
DAD_PCT = 0.05        # папина доля (входит в общий процент)


def parse_duration_minutes(text: str) -> Optional[int]:
    """Понимает: '2.5', '2,5', '2', '2:30', '2ч 30', '2ч 30мин', '2 40', '45мин',
    а также интервал времени работы '9:30-12:00' (в т.ч. через полночь '23:00-1:30')."""
    s = (text or '').strip().lower().replace('—', '-').replace('–', '-')
    if not s:
        return None

    # интервал "9:30-12:00", "9-12"
    m = re.fullmatch(r'(\d{1,2})(?::(\d{1,2}))?\s*-\s*(\d{1,2})(?::(\d{1,2}))?', s)
    if m:
        h1, m1, h2, m2 = int(m[1]), int(m[2] or 0), int(m[3]), int(m[4] or 0)
        if h1 > 23 or h2 > 23 or m1 > 59 or m2 > 59:
            return None
        start, end = h1 * 60 + m1, h2 * 60 + m2
        if end <= start:
            end += 24 * 60  # работа через полночь
        return end - start

    # "2:30" — часы:минуты
    m = re.fullmatch(r'(\d{1,2}):(\d{1,2})', s)
    if m:
        mins = int(m[2])
        if mins > 59:
            return None
        return int(m[1]) * 60 + mins

    # "2.5" / "2,5" / "2" — часы
    m = re.fullmatch(r'(\d+(?:[.,]\d+)?)', s)
    if m:
        return int(round(float(m[1].replace(',', '.')) * 60))

    # "2ч 30", "2ч 30мин", "2 ч", "2h30m"
    m = re.fullmatch(r'(\d+)\s*[чh]\.?\s*(?:(\d+)\s*(?:мин|м|m)?\.?)?', s)
    if m:
        return int(m[1]) * 60 + int(m[2] or 0)

    # "45мин", "45 м"
    m = re.fullmatch(r'(\d+)\s*(?:мин|м|m)\.?', s)
    if m:
        return int(m[1])

    # "2 40" — часы и минуты через пробел
    m = re.fullmatch(r'(\d{1,2})\s+(\d{1,2})', s)
    if m:
        return int(m[1]) * 60 + int(m[2])

    return None


def fmt_minutes(total: Optional[int]) -> str:
    if not total or total <= 0:
        return '—'
    h, m = divmod(int(total), 60)
    if h and m:
        return f"{h}ч {m}мин"
    if h:
        return f"{h}ч"
    return f"{m}мин"


def calc_money(work_type: str, revenue: float, helper_pay: float = 0, dad_share: int = 1) -> Dict[str, float]:
    """Раскладка денег по заказу.

    revenue    — грязная выручка (сотки×тариф для покоса, фикс. сумма для другой работы)
    helper_pay — сколько отдано помощнику
    dad_share  — участвует ли папина доля (для покоса всегда 1)

    База для процентов — заработок после вычета помощника.
    Покос: −15%, из них 5% папе. Другая работа: с папой −15% (5% папе), без папы −10%.
    """
    revenue = float(revenue or 0)
    helper_pay = float(helper_pay or 0)
    earn = revenue - helper_pay
    if work_type == 'other' and not dad_share:
        pct, dad = OTHER_PCT_NO_DAD, 0.0
    else:
        pct, dad = MOW_PCT, round(earn * DAD_PCT, 2)
    percent = round(earn * pct, 2)
    net = round(earn - percent, 2)
    return {
        'revenue': revenue,
        'helper_pay': helper_pay,
        'earn': earn,
        'percent': percent,
        'dad': dad,
        'net': net,
        'pct': pct,
    }


def per_hour(revenue: float, duration_min: Optional[int]) -> Optional[float]:
    """Доход в час — от грязной выручки."""
    if not duration_min or duration_min <= 0:
        return None
    return round(float(revenue or 0) * 60.0 / duration_min, 2)
