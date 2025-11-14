"""CRUD операции для работы с базой данных."""
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from database.models import User, Transaction, Category, Budget, TransactionType, BudgetPeriod, MerchantRule, Receipt
from loguru import logger


# ========== User CRUD ==========

def get_user_by_telegram_id(db: Session, telegram_id: int) -> Optional[User]:
    """Получить пользователя по Telegram ID."""
    return db.query(User).filter(User.telegram_id == telegram_id).first()


def create_user(db: Session, telegram_id: int, username: Optional[str] = None) -> User:
    """Создать нового пользователя."""
    user = User(telegram_id=telegram_id, username=username)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_or_create_user(db: Session, telegram_id: int, username: Optional[str] = None) -> User:
    """Получить пользователя или создать нового."""
    user = get_user_by_telegram_id(db, telegram_id)
    if not user:
        user = create_user(db, telegram_id, username)
    return user


def update_user_settings(db: Session, user_id: int, settings: dict) -> User:
    """Обновить настройки пользователя."""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        current_settings = user.settings if user.settings else {}
        current_settings.update(settings)
        user.settings = current_settings
        db.commit()
        db.refresh(user)
    return user


def get_user_settings(db: Session, user_id: int) -> dict:
    """Получить настройки пользователя."""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        return user.settings if user.settings else {}
    return {}


# ========== Category CRUD ==========

def get_categories_by_user(db: Session, user_id: int, transaction_type: Optional[TransactionType] = None) -> List[Category]:
    """Получить категории пользователя."""
    query = db.query(Category).filter(Category.user_id == user_id)
    if transaction_type:
        query = query.filter(Category.type == transaction_type)
    return query.all()


def get_category_by_id(db: Session, category_id: int) -> Optional[Category]:
    """Получить категорию по ID."""
    return db.query(Category).filter(Category.id == category_id).first()


def create_category(db: Session, user_id: int, name: str, transaction_type: TransactionType, icon: str = "📁", is_default: bool = False) -> Category:
    """Создать категорию."""
    category = Category(
        user_id=user_id,
        name=name,
        type=transaction_type,
        icon=icon,
        is_default=is_default
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def delete_category(db: Session, category_id: int) -> bool:
    """Удалить категорию."""
    category = db.query(Category).filter(Category.id == category_id).first()
    if category:
        db.delete(category)
        db.commit()
        return True
    return False


# ========== Transaction CRUD ==========

def create_transaction(
    db: Session,
    user_id: int,
    transaction_type: TransactionType,
    amount: float,
    category_id: Optional[int] = None,
    date: Optional[date] = None,
    description: Optional[str] = None,
    receipt_photo_url: Optional[str] = None
) -> Transaction:
    """Создать транзакцию."""
    if date is None:
        date = datetime.now().date()
    
    transaction = Transaction(
        user_id=user_id,
        type=transaction_type,
        amount=amount,
        category_id=category_id,
        date=date,
        description=description,
        receipt_photo_url=receipt_photo_url
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


def get_transactions_by_user(
    db: Session,
    user_id: int,
    transaction_type: Optional[TransactionType] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    category_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Transaction]:
    """Получить транзакции пользователя с фильтрами."""
    query = db.query(Transaction).filter(Transaction.user_id == user_id)
    
    if transaction_type:
        query = query.filter(Transaction.type == transaction_type)
    
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    
    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    
    return query.order_by(Transaction.date.desc(), Transaction.created_at.desc()).limit(limit).offset(offset).all()


def get_transaction_by_id(db: Session, transaction_id: int) -> Optional[Transaction]:
    """Получить транзакцию по ID."""
    return db.query(Transaction).filter(Transaction.id == transaction_id).first()


def update_transaction(
    db: Session,
    transaction_id: int,
    amount: Optional[float] = None,
    category_id: Optional[int] = None,
    date: Optional[date] = None,
    description: Optional[str] = None
) -> Optional[Transaction]:
    """Обновить транзакцию."""
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if transaction:
        if amount is not None:
            transaction.amount = amount
        if category_id is not None:
            transaction.category_id = category_id
        if date is not None:
            transaction.date = date
        if description is not None:
            transaction.description = description
        db.commit()
        db.refresh(transaction)
        return transaction
    return None


def delete_transaction(db: Session, transaction_id: int) -> bool:
    """Удалить транзакцию."""
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if transaction:
        db.delete(transaction)
        db.commit()
        return True
    return False


def bulk_create_transactions(
    db: Session,
    user_id: int,
    transactions_data: List[Dict[str, Any]]
) -> tuple[int, int]:
    """Массовое создание транзакций.
    
    Returns:
        tuple: (количество созданных, количество пропущенных из-за дубликатов)
    """
    created_count = 0
    skipped_count = 0
    
    for trans_data in transactions_data:
        try:
            # Проверяем на дубликаты (по сумме, дате, типу и описанию)
            # Важно: учитываем тип транзакции, так как одна и та же сумма может быть и доходом и расходом
            transaction_type = TransactionType(trans_data["type"])
            existing = db.query(Transaction).filter(
                Transaction.user_id == user_id,
                Transaction.type == transaction_type,
                Transaction.amount == trans_data["amount"],
                Transaction.date == trans_data["date"],
                Transaction.description == trans_data.get("description", "")
            ).first()
            
            if existing:
                logger.debug(f"Пропущена дубликат транзакции: {trans_data.get('description', '')[:50]} - {trans_data['amount']} на {trans_data['date']}")
                skipped_count += 1
                continue
            
            # Находим категорию по имени
            category_id = None
            if trans_data.get("category_name"):
                category = db.query(Category).filter(
                    Category.user_id == user_id,
                    Category.name == trans_data["category_name"]
                ).first()
                if category:
                    category_id = category.id
            
            # Создаем транзакцию
            transaction = Transaction(
                user_id=user_id,
                type=TransactionType(trans_data["type"]),
                amount=trans_data["amount"],
                category_id=category_id,
                date=trans_data["date"],
                description=trans_data.get("description")
            )
            db.add(transaction)
            created_count += 1
            
        except Exception as e:
            logger.error(f"Ошибка при создании транзакции: {e}")
            skipped_count += 1
            continue
    
    db.commit()
    return created_count, skipped_count


def get_balance(db: Session, user_id: int, start_date: Optional[date] = None, end_date: Optional[date] = None) -> dict:
    """Получить баланс пользователя."""
    query = db.query(
        Transaction.type,
        func.sum(Transaction.amount).label('total')
    ).filter(Transaction.user_id == user_id)
    
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    
    results = query.group_by(Transaction.type).all()
    
    income = sum(r.total for r in results if r.type == TransactionType.INCOME)
    expense = sum(r.total for r in results if r.type == TransactionType.EXPENSE)
    
    return {
        "income": float(income) if income else 0.0,
        "expense": float(expense) if expense else 0.0,
        "balance": float(income - expense) if income and expense else (float(income) if income else -float(expense) if expense else 0.0)
    }


# ========== Budget CRUD ==========

def create_budget(
    db: Session,
    user_id: int,
    limit_amount: float,
    period: BudgetPeriod,
    category_id: Optional[int] = None,
    start_date: Optional[date] = None
) -> Budget:
    """Создать бюджет."""
    if start_date is None:
        start_date = datetime.now().date()
    
    budget = Budget(
        user_id=user_id,
        category_id=category_id,
        limit_amount=limit_amount,
        period=period,
        start_date=start_date
    )
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget


def get_budgets_by_user(db: Session, user_id: int) -> List[Budget]:
    """Получить бюджеты пользователя."""
    return db.query(Budget).filter(Budget.user_id == user_id).all()


def delete_budget(db: Session, budget_id: int) -> bool:
    """Удалить бюджет."""
    budget = db.query(Budget).filter(Budget.id == budget_id).first()
    if budget:
        db.delete(budget)
        db.commit()
        return True
    return False


# ========== Statistics ==========

def get_statistics_by_category(
    db: Session,
    user_id: int,
    transaction_type: TransactionType,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> List[dict]:
    """Получить статистику по категориям."""
    query = db.query(
        Category.name,
        Category.icon,
        func.sum(Transaction.amount).label('total'),
        func.count(Transaction.id).label('count')
    ).join(
        Transaction, Transaction.category_id == Category.id
    ).filter(
        Transaction.user_id == user_id,
        Transaction.type == transaction_type
    )
    
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    
    results = query.group_by(Category.id, Category.name, Category.icon).order_by(func.sum(Transaction.amount).desc()).all()
    
    return [
        {
            "name": r.name,
            "icon": r.icon,
            "total": float(r.total),
            "count": r.count
        }
        for r in results
    ]


def get_average_daily_expense(
    db: Session,
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> float:
    """Получить средний дневной расход."""
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = date(end_date.year, end_date.month, 1)
    
    days = (end_date - start_date).days + 1
    if days == 0:
        return 0.0
    
    expenses = get_balance(db, user_id, start_date, end_date)["expense"]
    return expenses / days if days > 0 else 0.0


# ========== MerchantRule CRUD ==========

def get_merchant_rule(db: Session, user_id: int, merchant_name: str) -> Optional[MerchantRule]:
    """Получить правило автокатегоризации для мерчанта."""
    # Нормализуем название мерчанта для поиска (lowercase)
    normalized_name = merchant_name.lower().strip()
    return db.query(MerchantRule).filter(
        MerchantRule.user_id == user_id,
        func.lower(MerchantRule.merchant_name) == normalized_name
    ).first()


def create_merchant_rule(
    db: Session,
    user_id: int,
    merchant_name: str,
    category_id: int,
    default_description: Optional[str] = None
) -> MerchantRule:
    """Создать правило автокатегоризации для мерчанта."""
    # Нормализуем название мерчанта (lowercase, trim)
    normalized_name = merchant_name.lower().strip()
    
    # Проверяем, есть ли уже правило для этого мерчанта
    existing_rule = get_merchant_rule(db, user_id, normalized_name)
    if existing_rule:
        # Обновляем существующее правило
        existing_rule.category_id = category_id
        existing_rule.default_description = default_description
        existing_rule.updated_at = datetime.now()
        db.commit()
        db.refresh(existing_rule)
        return existing_rule
    
    # Создаём новое правило
    rule = MerchantRule(
        user_id=user_id,
        merchant_name=normalized_name,
        category_id=category_id,
        default_description=default_description
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    logger.info(f"Создано правило для мерчанта '{merchant_name}' пользователя {user_id}")
    return rule


def get_all_merchant_rules(db: Session, user_id: int) -> List[MerchantRule]:
    """Получить все правила автокатегоризации пользователя."""
    return db.query(MerchantRule).filter(MerchantRule.user_id == user_id).all()


def delete_merchant_rule(db: Session, rule_id: int) -> bool:
    """Удалить правило автокатегоризации."""
    rule = db.query(MerchantRule).filter(MerchantRule.id == rule_id).first()
    if rule:
        db.delete(rule)
        db.commit()
        return True
    return False


# ========== Receipt CRUD ==========

def create_receipt(
    db: Session,
    user_id: int,
    total_amount: float,
    store_name: Optional[str] = None,
    receipt_date: Optional[datetime] = None,
    vat_amount: Optional[float] = None,
    receipt_number: Optional[str] = None,
    image_data: Optional[str] = None,
    items: Optional[List[Dict]] = None,
    raw_data: Optional[Dict] = None,
    transaction_id: Optional[int] = None
) -> Receipt:
    """Создать чек."""
    receipt = Receipt(
        user_id=user_id,
        transaction_id=transaction_id,
        store_name=store_name,
        receipt_date=receipt_date,
        total_amount=total_amount,
        vat_amount=vat_amount,
        receipt_number=receipt_number,
        image_data=image_data,
        items=items,
        raw_data=raw_data
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    logger.info(f"Создан чек ID:{receipt.id} для пользователя {user_id}, сумма {total_amount}")
    return receipt


def get_receipt_by_id(db: Session, receipt_id: int) -> Optional[Receipt]:
    """Получить чек по ID."""
    return db.query(Receipt).filter(Receipt.id == receipt_id).first()


def get_receipts_by_user(
    db: Session,
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 50
) -> List[Receipt]:
    """Получить чеки пользователя."""
    query = db.query(Receipt).filter(Receipt.user_id == user_id)
    
    if start_date:
        query = query.filter(Receipt.receipt_date >= start_date)
    if end_date:
        query = query.filter(Receipt.receipt_date <= end_date)
    
    return query.order_by(Receipt.receipt_date.desc()).limit(limit).all()


def get_receipt_by_transaction(db: Session, transaction_id: int) -> Optional[Receipt]:
    """Получить чек по ID транзакции."""
    return db.query(Receipt).filter(Receipt.transaction_id == transaction_id).first()


def find_matching_transactions(
    db: Session,
    user_id: int,
    amount: float,
    receipt_date: date,
    tolerance_percent: float = 5.0,
    date_tolerance_days: int = 1
) -> List[Transaction]:
    """
    Найти транзакции, соответствующие чеку.
    
    Args:
        user_id: ID пользователя
        amount: Сумма чека
        receipt_date: Дата чека
        tolerance_percent: Допустимое отклонение суммы в процентах
        date_tolerance_days: Допустимое отклонение даты в днях
    
    Returns:
        List[Transaction]: Список подходящих транзакций
    """
    # Рассчитываем границы суммы
    amount_min = amount * (1 - tolerance_percent / 100)
    amount_max = amount * (1 + tolerance_percent / 100)
    
    # Рассчитываем границы даты
    date_min = receipt_date - timedelta(days=date_tolerance_days)
    date_max = receipt_date + timedelta(days=date_tolerance_days)
    
    # Ищем транзакции
    transactions = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.amount >= amount_min,
        Transaction.amount <= amount_max,
        Transaction.date >= date_min,
        Transaction.date <= date_max,
        Transaction.type == TransactionType.EXPENSE  # Чеки обычно для расходов
    ).order_by(
        # Сортируем по близости суммы и даты
        func.abs(Transaction.amount - amount),
        func.abs(func.extract('epoch', Transaction.date - receipt_date))
    ).all()
    
    return transactions


def attach_receipt_to_transaction(db: Session, receipt_id: int, transaction_id: int) -> Receipt:
    """Прикрепить чек к транзакции."""
    receipt = get_receipt_by_id(db, receipt_id)
    if receipt:
        receipt.transaction_id = transaction_id
        db.commit()
        db.refresh(receipt)
        logger.info(f"Чек {receipt_id} прикреплён к транзакции {transaction_id}")
    return receipt


def delete_receipt(db: Session, receipt_id: int) -> bool:
    """Удалить чек."""
    receipt = get_receipt_by_id(db, receipt_id)
    if receipt:
        db.delete(receipt)
        db.commit()
        logger.info(f"Удалён чек {receipt_id}")
        return True
    return False

