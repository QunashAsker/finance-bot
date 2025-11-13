"""Предустановленные категории."""
from database.models import TransactionType

# Категории доходов по умолчанию
DEFAULT_INCOME_CATEGORIES = [
    {"name": "Зарплата", "icon": "💼", "type": TransactionType.INCOME},
    {"name": "Фриланс", "icon": "💻", "type": TransactionType.INCOME},
    {"name": "Подарки", "icon": "🎁", "type": TransactionType.INCOME},
    {"name": "Прочее", "icon": "💰", "type": TransactionType.INCOME},
]

# Категории расходов по умолчанию
DEFAULT_EXPENSE_CATEGORIES = [
    {"name": "Продукты", "icon": "🛒", "type": TransactionType.EXPENSE},
    {"name": "Транспорт", "icon": "🚗", "type": TransactionType.EXPENSE},
    {"name": "Развлечения", "icon": "🎬", "type": TransactionType.EXPENSE},
    {"name": "Здоровье", "icon": "🏥", "type": TransactionType.EXPENSE},
    {"name": "Связь", "icon": "📱", "type": TransactionType.EXPENSE},
    {"name": "Кафе", "icon": "☕", "type": TransactionType.EXPENSE},
    {"name": "Одежда", "icon": "👕", "type": TransactionType.EXPENSE},
    {"name": "Прочее", "icon": "📦", "type": TransactionType.EXPENSE},
]


def create_default_categories(db, user_id: int):
    """Создать категории по умолчанию для пользователя."""
    from database.crud import create_category
    
    categories = []
    for cat_data in DEFAULT_INCOME_CATEGORIES + DEFAULT_EXPENSE_CATEGORIES:
        category = create_category(
            db=db,
            user_id=user_id,
            name=cat_data["name"],
            transaction_type=cat_data["type"],
            icon=cat_data["icon"],
            is_default=True
        )
        categories.append(category)
    
    return categories

