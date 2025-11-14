"""Модели базы данных."""
from sqlalchemy import Column, Integer, BigInteger, String, Float, DateTime, ForeignKey, Text, JSON, Boolean, Date, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum
from database.connection import Base


class TransactionType(str, enum.Enum):
    """Тип транзакции."""
    INCOME = "income"
    EXPENSE = "expense"


class BudgetPeriod(str, enum.Enum):
    """Период бюджета."""
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class User(Base):
    """Модель пользователя."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    settings = Column(JSON, default={})
    
    # Связи
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    categories = relationship("Category", back_populates="user", cascade="all, delete-orphan")
    budgets = relationship("Budget", back_populates="user", cascade="all, delete-orphan")


class Category(Base):
    """Модель категории."""
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    type = Column(SQLEnum(TransactionType), nullable=False)
    icon = Column(String(10), default="📁")
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Связи
    user = relationship("User", back_populates="categories")
    transactions = relationship("Transaction", back_populates="category")
    budgets = relationship("Budget", back_populates="category")


class Transaction(Base):
    """Модель транзакции."""
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(SQLEnum(TransactionType), nullable=False)
    amount = Column(Float, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    date = Column(Date, nullable=False, default=func.current_date())
    description = Column(Text, nullable=True)
    receipt_photo_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Связи
    user = relationship("User", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")
    receipt = relationship("Receipt", back_populates="transaction", uselist=False)


class Budget(Base):
    """Модель бюджета."""
    __tablename__ = "budgets"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    limit_amount = Column(Float, nullable=False)
    period = Column(SQLEnum(BudgetPeriod), nullable=False)
    start_date = Column(Date, nullable=False, default=func.current_date())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Связи
    user = relationship("User", back_populates="budgets")
    category = relationship("Category", back_populates="budgets")


class MerchantRule(Base):
    """Модель правила автокатегоризации мерчанта."""
    __tablename__ = "merchant_rules"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    merchant_name = Column(String(255), nullable=False, index=True)  # Нормализованное название (например "перекрёсток")
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    default_description = Column(Text, nullable=True)  # Шаблон описания
    tags = Column(JSON, default={})  # Дополнительные теги (для будущего расширения)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Связи
    user = relationship("User")
    category = relationship("Category")


class Receipt(Base):
    """Модель чека."""
    __tablename__ = "receipts"
    
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)  # Может быть не привязан к транзакции
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Данные чека
    store_name = Column(String(255), nullable=True)  # Название магазина
    receipt_date = Column(DateTime, nullable=True)  # Дата и время чека
    total_amount = Column(Float, nullable=False)  # Общая сумма
    vat_amount = Column(Float, nullable=True)  # НДС
    receipt_number = Column(String(100), nullable=True)  # Номер чека
    
    # Изображение чека
    image_data = Column(Text, nullable=True)  # base64 изображения
    
    # Структурированные данные
    items = Column(JSON, nullable=True)  # Список товаров [{name, price, quantity, total}]
    raw_data = Column(JSON, nullable=True)  # Полные данные от OCR
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Связи
    transaction = relationship("Transaction", back_populates="receipt")
    user = relationship("User")

