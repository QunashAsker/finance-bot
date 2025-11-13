"""Вспомогательные функции."""
from datetime import datetime, date
from typing import Optional


def format_amount(amount: float, currency: str = "₽") -> str:
    """Форматировать сумму с валютой."""
    return f"{amount:,.2f} {currency}".replace(",", " ")


def format_date(d: date) -> str:
    """Форматировать дату."""
    return d.strftime("%d.%m.%Y")


def format_datetime(dt: datetime) -> str:
    """Форматировать дату и время."""
    return dt.strftime("%d.%m.%Y %H:%M")


def parse_amount(text: str) -> Optional[float]:
    """Парсить сумму из текста."""
    try:
        # Удаляем все символы кроме цифр, точки и запятой
        cleaned = "".join(c for c in text if c.isdigit() or c in ".,")
        # Заменяем запятую на точку
        cleaned = cleaned.replace(",", ".")
        return float(cleaned)
    except (ValueError, AttributeError):
        return None

