"""Клавиатуры для Telegram бота."""
from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from database.models import TransactionType


def get_main_menu_keyboard():
    """Главное меню бота."""
    keyboard = [
        [
            KeyboardButton("➕ Добавить доход"),
            KeyboardButton("➖ Добавить расход")
        ],
        [
            KeyboardButton("💰 Баланс"),
            KeyboardButton("📊 Категории")
        ],
        [
            KeyboardButton("📜 История"),
            KeyboardButton("📈 Статистика")
        ],
        [
            KeyboardButton("🤖 AI Ассистент"),
            KeyboardButton("⚙️ Настройки")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_categories_inline_keyboard(categories, transaction_type: TransactionType = None):
    """Inline клавиатура с категориями."""
    buttons = []
    for category in categories:
        if transaction_type is None or category.type == transaction_type:
            callback_data = f"category_{category.id}"
            buttons.append([InlineKeyboardButton(
                f"{category.icon} {category.name}",
                callback_data=callback_data
            )])
    
    if not buttons:
        buttons.append([InlineKeyboardButton("Нет категорий", callback_data="no_categories")])
    
    return InlineKeyboardMarkup(buttons)


def get_confirmation_keyboard():
    """Клавиатура подтверждения."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"),
            InlineKeyboardButton("✏️ Изменить", callback_data="edit")
        ],
        [
            InlineKeyboardButton("❌ Отменить", callback_data="cancel")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_period_keyboard():
    """Клавиатура выбора периода."""
    keyboard = [
        [
            InlineKeyboardButton("Сегодня", callback_data="period_today"),
            InlineKeyboardButton("Неделя", callback_data="period_week")
        ],
        [
            InlineKeyboardButton("Месяц", callback_data="period_month"),
            InlineKeyboardButton("Год", callback_data="period_year")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_transaction_actions_keyboard(transaction_id: int):
    """Клавиатура действий с транзакцией."""
    keyboard = [
        [
            InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_transaction_{transaction_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_transaction_{transaction_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_edit_transaction_keyboard():
    """Клавиатура выбора поля для редактирования транзакции."""
    keyboard = [
        [
            InlineKeyboardButton("💰 Сумма", callback_data="edit_field_amount"),
            InlineKeyboardButton("📊 Категория", callback_data="edit_field_category")
        ],
        [
            InlineKeyboardButton("📅 Дата", callback_data="edit_field_date"),
            InlineKeyboardButton("💬 Описание", callback_data="edit_field_description")
        ],
        [
            InlineKeyboardButton("✅ Сохранить", callback_data="edit_save"),
            InlineKeyboardButton("❌ Отменить", callback_data="edit_cancel")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_settings_keyboard():
    """Клавиатура настроек."""
    keyboard = [
        [
            InlineKeyboardButton("💱 Валюта", callback_data="setting_currency")
        ],
        [
            InlineKeyboardButton("📅 Начало месяца", callback_data="setting_month_start")
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data="settings_back")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_currency_keyboard():
    """Клавиатура выбора валюты."""
    currencies = [
        ("₽", "RUB"),
        ("$", "USD"),
        ("€", "EUR"),
        ("₴", "UAH"),
        ("₸", "KZT")
    ]
    keyboard = []
    for symbol, code in currencies:
        keyboard.append([InlineKeyboardButton(
            f"{symbol} {code}",
            callback_data=f"currency_{code}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="settings_back")])
    return InlineKeyboardMarkup(keyboard)


def get_month_start_keyboard():
    """Клавиатура выбора начала месяца."""
    keyboard = []
    # Группируем по 5 кнопок в ряд
    for i in range(0, 31, 5):
        row = []
        for j in range(i + 1, min(i + 6, 32)):
            row.append(InlineKeyboardButton(str(j), callback_data=f"month_start_{j}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="settings_back")])
    return InlineKeyboardMarkup(keyboard)

