"""CRUD операции для работы с базой данных."""
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from database.models import User, Transaction, Category, Budget, TransactionType, BudgetPeriod
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
            # Проверяем на дубликаты (по сумме, дате и описанию)
            existing = db.query(Transaction).filter(
                Transaction.user_id == user_id,
                Transaction.amount == trans_data["amount"],
                Transaction.date == trans_data["date"],
                Transaction.description == trans_data.get("description")
            ).first()
            
            if existing:
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

