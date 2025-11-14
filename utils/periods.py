"""Утилиты для работы с расчётными периодами."""
from datetime import date, timedelta
from typing import Tuple, Dict, Any
from dateutil.relativedelta import relativedelta


def get_period_boundaries(period_type: str, month_start: int = 1, reference_date: date = None) -> Tuple[date, date]:
    """
    Получить границы периода с учётом начала расчётного месяца.
    
    Args:
        period_type: Тип периода ('current', 'previous', 'all_time', 'today', 'week', 'year')
        month_start: День начала расчётного месяца (1-31)
        reference_date: Дата для расчёта (по умолчанию сегодня)
    
    Returns:
        tuple: (start_date, end_date)
    """
    if reference_date is None:
        reference_date = date.today()
    
    if period_type == "today":
        return reference_date, reference_date
    
    elif period_type == "week":
        # Последние 7 дней
        start_date = reference_date - timedelta(days=6)
        return start_date, reference_date
    
    elif period_type == "current":
        # Текущий расчётный месяц
        start_date = get_period_start_date(reference_date, month_start)
        return start_date, reference_date
    
    elif period_type == "previous":
        # Предыдущий расчётный месяц (полный)
        current_period_start = get_period_start_date(reference_date, month_start)
        # Вычитаем 1 день, чтобы попасть в предыдущий период
        previous_period_end = current_period_start - timedelta(days=1)
        previous_period_start = get_period_start_date(previous_period_end, month_start)
        return previous_period_start, previous_period_end
    
    elif period_type == "year":
        # Текущий год
        start_date = date(reference_date.year, 1, 1)
        return start_date, reference_date
    
    elif period_type == "all_time":
        # За всё время (начиная с 2020 года или ранее)
        start_date = date(2020, 1, 1)
        return start_date, reference_date
    
    else:
        # По умолчанию - текущий месяц
        start_date = get_period_start_date(reference_date, month_start)
        return start_date, reference_date


def get_period_start_date(reference_date: date, month_start: int) -> date:
    """
    Получить дату начала расчётного периода для заданной даты.
    
    Args:
        reference_date: Дата, для которой нужно определить начало периода
        month_start: День начала расчётного месяца (1-31)
    
    Returns:
        date: Дата начала периода
    
    Examples:
        >>> get_period_start_date(date(2025, 11, 14), 1)
        date(2025, 11, 1)
        
        >>> get_period_start_date(date(2025, 11, 14), 10)
        date(2025, 11, 10)
        
        >>> get_period_start_date(date(2025, 11, 5), 10)
        date(2025, 10, 10)
    """
    # Если текущий день >= month_start, то период начался в этом месяце
    if reference_date.day >= month_start:
        try:
            return date(reference_date.year, reference_date.month, month_start)
        except ValueError:
            # Если day не существует в этом месяце (например, 31 февраля)
            # Берём последний день месяца
            next_month = reference_date.replace(day=1) + relativedelta(months=1)
            last_day = (next_month - timedelta(days=1)).day
            return date(reference_date.year, reference_date.month, min(month_start, last_day))
    else:
        # Период начался в прошлом месяце
        prev_month = reference_date.replace(day=1) - timedelta(days=1)
        try:
            return date(prev_month.year, prev_month.month, month_start)
        except ValueError:
            # Если day не существует в прошлом месяце
            last_day = prev_month.day
            return date(prev_month.year, prev_month.month, min(month_start, last_day))


def get_period_name(period_type: str, start_date: date, end_date: date) -> str:
    """
    Получить читаемое название периода.
    
    Args:
        period_type: Тип периода
        start_date: Дата начала
        end_date: Дата окончания
    
    Returns:
        str: Название периода
    """
    if period_type == "today":
        return "Сегодня"
    
    elif period_type == "week":
        return "Последние 7 дней"
    
    elif period_type == "current":
        if start_date.month == end_date.month:
            return f"Текущий период ({start_date.day}-{end_date.day} {get_month_name(end_date.month)})"
        else:
            return f"Текущий период ({start_date.day} {get_month_name(start_date.month)} - {end_date.day} {get_month_name(end_date.month)})"
    
    elif period_type == "previous":
        if start_date.month == end_date.month:
            return f"Прошлый период ({start_date.day}-{end_date.day} {get_month_name(end_date.month)})"
        else:
            return f"Прошлый период ({start_date.day} {get_month_name(start_date.month)} - {end_date.day} {get_month_name(end_date.month)})"
    
    elif period_type == "year":
        return f"Текущий год ({start_date.year})"
    
    elif period_type == "all_time":
        return "За всё время"
    
    else:
        return f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"


def get_month_name(month: int) -> str:
    """Получить название месяца на русском."""
    months = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
    }
    return months.get(month, "")


def calculate_period_comparison(
    current_stats: Dict[str, Any],
    previous_stats: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Рассчитать сравнение текущего и предыдущего периодов.
    
    Args:
        current_stats: Статистика текущего периода
        previous_stats: Статистика предыдущего периода
    
    Returns:
        dict: Данные сравнения с процентами изменений
    """
    comparison = {
        "income_change": 0,
        "income_change_percent": 0,
        "expense_change": 0,
        "expense_change_percent": 0,
        "balance_change": 0,
        "balance_change_percent": 0,
    }
    
    current_income = current_stats.get("income", 0)
    current_expense = current_stats.get("expense", 0)
    current_balance = current_income - current_expense
    
    previous_income = previous_stats.get("income", 0)
    previous_expense = previous_stats.get("expense", 0)
    previous_balance = previous_income - previous_expense
    
    # Изменение доходов
    comparison["income_change"] = current_income - previous_income
    if previous_income > 0:
        comparison["income_change_percent"] = (comparison["income_change"] / previous_income) * 100
    
    # Изменение расходов
    comparison["expense_change"] = current_expense - previous_expense
    if previous_expense > 0:
        comparison["expense_change_percent"] = (comparison["expense_change"] / previous_expense) * 100
    
    # Изменение баланса
    comparison["balance_change"] = current_balance - previous_balance
    if abs(previous_balance) > 0:
        comparison["balance_change_percent"] = (comparison["balance_change"] / abs(previous_balance)) * 100
    
    return comparison


def format_comparison_text(comparison: Dict[str, Any], user_settings: Dict = None) -> str:
    """
    Форматировать текст сравнения периодов.
    
    Args:
        comparison: Данные сравнения
        user_settings: Настройки пользователя
    
    Returns:
        str: Форматированный текст
    """
    from utils.helpers import format_amount
    
    lines = []
    
    # Доходы
    income_change = comparison["income_change"]
    income_percent = comparison["income_change_percent"]
    if income_change != 0:
        emoji = "📈" if income_change > 0 else "📉"
        sign = "+" if income_change > 0 else ""
        lines.append(
            f"{emoji} Доходы: {sign}{format_amount(abs(income_change), user_settings=user_settings)} "
            f"({sign}{income_percent:.1f}%)"
        )
    else:
        lines.append("➖ Доходы: без изменений")
    
    # Расходы
    expense_change = comparison["expense_change"]
    expense_percent = comparison["expense_change_percent"]
    if expense_change != 0:
        # Для расходов: рост - это плохо (📈 красный), падение - хорошо (📉 зелёный)
        emoji = "📈" if expense_change > 0 else "📉"
        sign = "+" if expense_change > 0 else ""
        lines.append(
            f"{emoji} Расходы: {sign}{format_amount(abs(expense_change), user_settings=user_settings)} "
            f"({sign}{expense_percent:.1f}%)"
        )
    else:
        lines.append("➖ Расходы: без изменений")
    
    # Баланс
    balance_change = comparison["balance_change"]
    balance_percent = comparison["balance_change_percent"]
    if balance_change != 0:
        emoji = "📈" if balance_change > 0 else "📉"
        sign = "+" if balance_change > 0 else ""
        lines.append(
            f"{emoji} Баланс: {sign}{format_amount(abs(balance_change), user_settings=user_settings)} "
            f"({sign}{balance_percent:.1f}%)"
        )
    else:
        lines.append("➖ Баланс: без изменений")
    
    return "\n".join(lines)

