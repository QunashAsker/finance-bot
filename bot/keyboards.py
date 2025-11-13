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

