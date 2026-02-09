"""
Утилиты и валидация ParkingBot
"""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PHONE_REGEX = r'^(\+7|7|8)?[\s\-]?\(?[489][0-9]{2}\)?[\s\-]?[0-9]{3}[\s\-]?[0-9]{2}[\s\-]?[0-9]{2}$'

def validate_name(name: str):
    # Требуем "Имя Фамилия" (минимум 2 слова)
    name = re.sub(r"\s+", " ", (name or "").strip())
    if len(name) < 3:
        return False, "❌ Введите имя и фамилию (пример: Иван Иванов)"
    if len(name) > 60:
        return False, "❌ Слишком длинно (макс. 60 символов)"
    parts = name.split(" ")
    if len(parts) < 2:
        return False, "❌ Нужно имя и фамилия (пример: Иван Иванов)"
    for p in parts:
        if not re.match(r"^[A-Za-zА-Яа-яЁё\-]+$", p):
            return False, "❌ Используйте только буквы и дефис (пример: Иван Иванов)"
    return True, name

def validate_phone(phone):
    cleaned = re.sub(r'[^\d+]', '', phone)
    if not re.match(PHONE_REGEX, phone):
        return False, "❌ Неверный формат. +7XXXXXXXXXX или 8XXXXXXXXXX"
    if cleaned.startswith('+7'): cleaned = '8' + cleaned[2:]
    elif cleaned.startswith('7') and len(cleaned) == 11: cleaned = '8' + cleaned[1:]
    if len(cleaned) != 11: return False, "❌ Номер должен содержать 11 цифр"
    return True, cleaned

def luhn_check(card):
    digits = [int(d) for d in card]
    odd = digits[-1::-2]; even = digits[-2::-2]
    total = sum(odd) + sum(d*2-9 if d*2>9 else d*2 for d in even)
    return total % 10 == 0

def validate_card(card):
    cleaned = re.sub(r"\D", "", card or "")
    if len(cleaned) != 16:
        return False, "❌ Номер карты: 16 цифр"
    from config import STRICT_CARD_VALIDATION, MIR_ONLY, ALLOWED_TEST_CARDS
    if STRICT_CARD_VALIDATION and not luhn_check(cleaned):
        return False, "❌ Неверный номер карты"
    if MIR_ONLY:
        prefix = int(cleaned[:4])
        is_mir = 2200 <= prefix <= 2204
        if (not is_mir) and (cleaned not in ALLOWED_TEST_CARDS):
            return False, "❌ Только карты МИР (начинается на 2200–2204)"
    return True, cleaned

def validate_date(date_str):
    if not re.match(r'^(0[1-9]|[12]\d|3[01])\.(0[1-9]|1[0-2])\.\d{4}$', date_str):
        return False, None
    try:
        parsed = datetime.strptime(date_str, "%d.%m.%Y")
        if parsed.date() < datetime.now().date(): return False, None
        return True, parsed
    except ValueError: return False, None

def validate_time(time_str):
    if not re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', time_str): return False, None
    return True, time_str

def validate_spot_number(s):
    s = s.strip()
    if len(s) < 1: return False, "❌ Номер не может быть пустым"
    if len(s) > 10: return False, "❌ Максимум 10 символов"
    return True, s

def validate_license_plate(p):
    # Формат: А123ВС77 или A123BC777 (буквы + 3 цифры + 2 буквы + регион 2-3 цифры)
    p = p.strip().upper().replace(" ", "").replace("-", "")
    allowed = "ABEKMHOPCTYXАВЕКМНОРСТУХ"
    import re
    if not re.fullmatch(rf"[{allowed}]\d{{3}}[{allowed}]{{2}}\d{{2,3}}", p):
        return False, "❌ Номер должен быть в формате А123ВС77 (регион 2–3 цифры)"
    return True, p
def validate_car_brand(b):
    b = b.strip()
    if len(b) < 2: return False, "❌ Слишком короткое"
    if len(b) > 50: return False, "❌ Слишком длинное"
    return True, b

def validate_car_color(c):
    c = c.strip()
    if len(c) < 2: return False, "❌ Слишком короткий"
    if len(c) > 30: return False, "❌ Слишком длинный"
    return True, c

def format_datetime(dt):
    if isinstance(dt, str): dt = datetime.fromisoformat(dt)
    return dt.strftime("%d.%m.%Y %H:%M")

def format_date(dt):
    if isinstance(dt, str): dt = datetime.fromisoformat(dt)
    return dt.strftime("%d.%m.%Y")

def parse_datetime(date_str, time_str):
    try: return datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
    except ValueError: return None

def get_next_days(count=7):
    today = datetime.now()
    return [(today + timedelta(days=i)).strftime("%d.%m.%Y") for i in range(count)]

def get_price_per_hour(hours):
    """Возвращает цену за час по тарифу"""
    from config import PRICE_TIERS, PRICE_DEFAULT
    for max_h, price in PRICE_TIERS:
        if hours <= max_h:
            return price
    return PRICE_DEFAULT

def calculate_price(start, end):
    """Считает цену по фиксированным тарифам"""
    h = (end - start).total_seconds() / 3600
    if h <= 0: return 0
    rate = get_price_per_hour(h)
    return round(rate * h)

def format_price_info():
    """Строка с тарифами для показа пользователю"""
    return (
        "💰 <b>Тарифы:</b>\n"
        "• 1-3ч → 150₽/ч\n"
        "• 4-6ч → 120₽/ч\n"
        "• 7-10ч → 90₽/ч\n"
        "• 11-24ч → 60₽/ч\n"
        "• 24ч+ → 60₽/ч"
    )

def mask_card(card):
    if card and len(card) >= 4: return f"****{card[-4:]}"
    return "—"

def now_local():
    """Текущее локальное время в TZ из config.TIMEZONE (naive datetime)."""
    from config import TIMEZONE
    tz = ZoneInfo(TIMEZONE)
    return datetime.now(tz).replace(tzinfo=None, second=0, microsecond=0)

def normalize_dt(dt: datetime) -> datetime:
    """Нормализует datetime: обнуляет секунды/микросекунды."""
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return dt.replace(second=0, microsecond=0)



def now_tz(tz_name: str):
    return datetime.now(ZoneInfo(tz_name))

def round_to_step(dt: datetime, step_minutes: int):
    """Округляет вниз к шагу step_minutes."""
    dt = dt.replace(second=0, microsecond=0)
    minutes = (dt.minute // step_minutes) * step_minutes
    return dt.replace(minute=minutes)

def parse_hhmm(s: str):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s.strip())
    if not m:
        raise ValueError("Invalid HH:MM")
    h = int(m.group(1)); mi = int(m.group(2))
    if h<0 or h>23 or mi<0 or mi>59:
        raise ValueError("Invalid HH:MM")
    return h, mi

def is_within_working_hours(start_dt: datetime, end_dt: datetime, start_hhmm: str, end_hhmm: str):
    sh, sm = parse_hhmm(start_hhmm)
    eh, em = parse_hhmm(end_hhmm)
    day_start = start_dt.replace(hour=sh, minute=sm, second=0, microsecond=0)
    day_end = start_dt.replace(hour=eh, minute=em, second=0, microsecond=0)
    # если end меньше start (ночной режим) — не поддерживаем
    if day_end <= day_start:
        return False
    return start_dt >= day_start and end_dt <= day_end

def validate_interval(start_dt: datetime, end_dt: datetime, now_dt: datetime, min_minutes: int,
                      working_start: str, working_end: str):
    if end_dt <= start_dt:
        return False, "❌ Время окончания должно быть позже начала"
    if start_dt < now_dt:
        return False, "❌ Нельзя выбрать время в прошлом"
    dur_min = int((end_dt - start_dt).total_seconds() // 60)
    if dur_min < min_minutes:
        return False, f"❌ Минимальная длительность {min_minutes} минут"
    if not is_within_working_hours(start_dt, end_dt, working_start, working_end):
        return False, f"❌ Доступно только в часы {working_start}–{working_end}"
    return True, ""
