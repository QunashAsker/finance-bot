"""Основной файл Telegram бота."""
import asyncio
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)
from telegram.constants import ParseMode
from database.connection import SessionLocal
from database.crud import (
    get_or_create_user,
    get_categories_by_user,
    get_category_by_id,
    create_transaction,
    get_transactions_by_user,
    get_balance,
    get_statistics_by_category,
    get_average_daily_expense,
    update_user_settings,
    get_user_settings,
    get_transaction_by_id,
    update_transaction,
    delete_transaction,
    bulk_create_transactions
)
from database.models import TransactionType as TType
from utils.default_categories import create_default_categories
from utils.helpers import format_amount, format_date, parse_amount
from utils.statement_parser import (
    parse_pdf_statement,
    parse_csv_statement,
    parse_excel_statement,
    categorize_transactions_batch
)
from bot.keyboards import (
    get_main_menu_keyboard,
    get_categories_inline_keyboard,
    get_confirmation_keyboard,
    get_period_keyboard,
    get_transaction_actions_keyboard,
    get_edit_transaction_keyboard,
    get_settings_keyboard,
    get_currency_keyboard,
    get_month_start_keyboard
)
from config.settings import settings
from loguru import logger
from datetime import datetime, date, timedelta
from typing import Dict, Any
from ai.claude_client import ClaudeClient

# Состояния для ConversationHandler
AMOUNT, CATEGORY, DESCRIPTION, CONFIRM = range(4)
# Состояния для редактирования транзакции
EDIT_AMOUNT, EDIT_CATEGORY, EDIT_DATE, EDIT_DESCRIPTION, EDIT_CONFIRM = range(4, 9)


class BotState:
    """Хранилище состояния бота."""
    def __init__(self):
        self.pending_transactions: Dict[int, Dict[str, Any]] = {}
    
    def set_pending(self, user_id: int, data: Dict[str, Any]):
        """Сохранить данные транзакции."""
        self.pending_transactions[user_id] = data
    
    def get_pending(self, user_id: int) -> Dict[str, Any]:
        """Получить данные транзакции."""
        return self.pending_transactions.get(user_id, {})
    
    def clear_pending(self, user_id: int):
        """Очистить данные транзакции."""
        self.pending_transactions.pop(user_id, None)


bot_state = BotState()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    db = SessionLocal()
    try:
        user = update.effective_user
        db_user = get_or_create_user(db, user.id, user.username)
        
        # Создаем категории по умолчанию, если их нет
        categories = get_categories_by_user(db, db_user.id)
        if not categories:
            create_default_categories(db, db_user.id)
            await update.message.reply_text(
                "✅ Созданы категории по умолчанию!"
            )
        
        welcome_text = f"""
👋 Привет, {user.first_name}!

Я помогу тебе управлять личными финансами.

📋 *Доступные функции:*
• ➕ Добавление доходов и расходов
• 📊 Категоризация транзакций
• 💰 Отслеживание баланса
• 📈 Статистика и аналитика
• 🤖 AI-ассистент для анализа
• 📸 Распознавание чеков

Выбери действие из меню ниже 👇
        """
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка в команде /start: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуй позже.")
    finally:
        db.close()


async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать баланс пользователя."""
    db = SessionLocal()
    try:
        user = update.effective_user
        db_user = get_or_create_user(db, user.id)
        
        # Общий баланс
        total_balance = get_balance(db, db_user.id)
        
        # Баланс за текущий месяц
        today = date.today()
        first_day = date(today.year, today.month, 1)
        month_balance = get_balance(db, db_user.id, start_date=first_day, end_date=today)
        
        # Последние 5 транзакций
        recent_transactions = get_transactions_by_user(db, db_user.id, limit=5)
        
        balance_text = f"""
💰 *Твой баланс*

*Общий баланс:*
{format_amount(total_balance['balance'])}

*За текущий месяц:*
Доходы: {format_amount(month_balance['income'])}
Расходы: {format_amount(month_balance['expense'])}
Баланс: {format_amount(month_balance['balance'])}

*Последние операции:*
        """
        
        if recent_transactions:
            for trans in recent_transactions:
                icon = "➕" if trans.type == TType.INCOME else "➖"
                category_name = trans.category.name if trans.category else "Без категории"
                balance_text += f"\n{icon} {format_amount(trans.amount)} - {category_name}"
                if trans.description:
                    balance_text += f" ({trans.description})"
                balance_text += f"\n   {format_date(trans.date)}"
        else:
            balance_text += "\nНет операций"
        
        await update.message.reply_text(
            balance_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при показе баланса: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуй позже.")
    finally:
        db.close()


async def add_income_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать добавление дохода."""
    context.user_data["transaction_type"] = TType.INCOME
    await update.message.reply_text(
        "💵 *Добавление дохода*\n\nВведи сумму:",
        parse_mode=ParseMode.MARKDOWN
    )
    return AMOUNT


async def add_expense_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать добавление расхода."""
    context.user_data["transaction_type"] = TType.EXPENSE
    await update.message.reply_text(
        "💸 *Добавление расхода*\n\nВведи сумму:",
        parse_mode=ParseMode.MARKDOWN
    )
    return AMOUNT


async def process_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработать ввод суммы."""
    amount = parse_amount(update.message.text)
    
    if amount is None or amount <= 0:
        await update.message.reply_text("❌ Неверная сумма. Попробуй еще раз:")
        return AMOUNT
    
    # Определяем тип транзакции из контекста
    transaction_type = context.user_data.get("transaction_type")
    
    if transaction_type is None:
        await update.message.reply_text("❌ Ошибка. Начни заново.")
        return ConversationHandler.END
    
    # Сохраняем сумму
    bot_state.set_pending(update.effective_user.id, {
        "type": transaction_type,
        "amount": amount,
        "category_id": None,
        "description": None
    })
    
    # Показываем категории
    db = SessionLocal()
    try:
        db_user = get_or_create_user(db, update.effective_user.id)
        categories = get_categories_by_user(db, db_user.id, transaction_type=transaction_type)
        
        if not categories:
            await update.message.reply_text("❌ Нет категорий. Сначала создай категории.")
            db.close()
            return ConversationHandler.END
        
        await update.message.reply_text(
            "Выбери категорию:",
            reply_markup=get_categories_inline_keyboard(categories, transaction_type)
        )
    except Exception as e:
        logger.error(f"Ошибка при выборе категории: {e}")
        await update.message.reply_text("❌ Произошла ошибка.")
    finally:
        db.close()
    
    return CATEGORY


async def process_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработать выбор категории."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "no_categories":
        await query.edit_message_text("❌ Нет доступных категорий.")
        return ConversationHandler.END
    
    category_id = int(query.data.split("_")[1])
    
    # Сохраняем категорию
    pending = bot_state.get_pending(update.effective_user.id)
    pending["category_id"] = category_id
    bot_state.set_pending(update.effective_user.id, pending)
    
    await query.edit_message_text(
        "💬 Введи описание (или отправь /skip чтобы пропустить):"
    )
    
    return DESCRIPTION


async def process_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработать описание."""
    description = update.message.text
    
    # Сохраняем описание
    pending = bot_state.get_pending(update.effective_user.id)
    pending["description"] = description
    bot_state.set_pending(update.effective_user.id, pending)
    
    await show_confirmation(update, context)
    return CONFIRM


async def skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить описание."""
    # Описание уже None по умолчанию
    await show_confirmation(update, context)
    return CONFIRM


async def show_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать подтверждение транзакции."""
    db = SessionLocal()
    try:
        pending = bot_state.get_pending(update.effective_user.id)
        
        if not pending:
            await update.message.reply_text("❌ Ошибка. Начни заново.")
            return
        
        category = None
        if pending.get("category_id"):
            from database.crud import get_category_by_id
            category = get_category_by_id(db, pending["category_id"])
        
        trans_type = "Доход" if pending["type"] == TType.INCOME else "Расход"
        category_name = category.name if category else "Без категории"
        
        confirmation_text = f"""
✅ *Подтверждение транзакции*

Тип: {trans_type}
Сумма: {format_amount(pending['amount'])}
Категория: {category_name}
Описание: {pending.get('description', 'Нет')}
        """
        
        await update.message.reply_text(
            confirmation_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_confirmation_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при подтверждении: {e}")
        await update.message.reply_text("❌ Произошла ошибка.")
    finally:
        db.close()


async def confirm_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтвердить транзакцию."""
    query = update.callback_query
    await query.answer()
    
    db = SessionLocal()
    try:
        pending = bot_state.get_pending(update.effective_user.id)
        
        if not pending:
            await query.edit_message_text("❌ Ошибка. Данные не найдены.")
            return
        
        db_user = get_or_create_user(db, update.effective_user.id)
        
        transaction = create_transaction(
            db=db,
            user_id=db_user.id,
            transaction_type=pending["type"],
            amount=pending["amount"],
            category_id=pending.get("category_id"),
            description=pending.get("description")
        )
        
        trans_type = "Доход" if pending["type"] == TType.INCOME else "Расход"
        await query.edit_message_text(
            f"✅ {trans_type} на сумму {format_amount(transaction.amount)} успешно добавлен!",
            reply_markup=None
        )
        
        bot_state.clear_pending(update.effective_user.id)
    except Exception as e:
        logger.error(f"Ошибка при сохранении транзакции: {e}")
        await query.edit_message_text("❌ Произошла ошибка при сохранении.")
    finally:
        db.close()
    
    return ConversationHandler.END


async def cancel_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменить транзакцию."""
    query = update.callback_query
    await query.answer()
    
    bot_state.clear_pending(update.effective_user.id)
    await query.edit_message_text("❌ Транзакция отменена.")
    
    return ConversationHandler.END


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать историю транзакций."""
    db = SessionLocal()
    try:
        user = update.effective_user
        db_user = get_or_create_user(db, user.id)
        
        transactions = get_transactions_by_user(db, db_user.id, limit=10)
        
        if not transactions:
            await update.message.reply_text(
                "📜 История пуста.\n\nДобавь первую транзакцию!",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        history_text = "📜 *История транзакций*\n\n"
        
        for trans in transactions:
            icon = "➕" if trans.type == TType.INCOME else "➖"
            category_name = trans.category.name if trans.category else "Без категории"
            history_text += f"{icon} *{format_amount(trans.amount)}*\n"
            history_text += f"   {category_name}"
            if trans.description:
                history_text += f" - {trans.description}"
            history_text += f"\n   {format_date(trans.date)}\n"
            # Добавляем кнопки редактирования для каждой транзакции
            history_text += f"   [ID: {trans.id}]\n\n"
        
        # Отправляем сообщение с кнопками для каждой транзакции
        for trans in transactions:
            icon = "➕" if trans.type == TType.INCOME else "➖"
            category_name = trans.category.name if trans.category else "Без категории"
            trans_text = f"{icon} {format_amount(trans.amount)} - {category_name}"
            if trans.description:
                trans_text += f"\n{trans.description}"
            trans_text += f"\n{format_date(trans.date)}"
            
            await update.message.reply_text(
                trans_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_transaction_actions_keyboard(trans.id)
            )
        
        await update.message.reply_text(
            "Выбери транзакцию для редактирования или удаления:",
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при показе истории: {e}")
        await update.message.reply_text("❌ Произошла ошибка.")
    finally:
        db.close()


async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать категории."""
    db = SessionLocal()
    try:
        user = update.effective_user
        db_user = get_or_create_user(db, user.id)
        
        categories = get_categories_by_user(db, db_user.id)
        
        if not categories:
            await update.message.reply_text(
                "📊 Нет категорий.\n\nИспользуй /start для создания категорий по умолчанию.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        income_categories = [c for c in categories if c.type == TType.INCOME]
        expense_categories = [c for c in categories if c.type == TType.EXPENSE]
        
        categories_text = "📊 *Твои категории*\n\n"
        
        if income_categories:
            categories_text += "*Доходы:*\n"
            for cat in income_categories:
                categories_text += f"{cat.icon} {cat.name}\n"
            categories_text += "\n"
        
        if expense_categories:
            categories_text += "*Расходы:*\n"
            for cat in expense_categories:
                categories_text += f"{cat.icon} {cat.name}\n"
        
        await update.message.reply_text(
            categories_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при показе категорий: {e}")
        await update.message.reply_text("❌ Произошла ошибка.")
    finally:
        db.close()


async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику."""
    db = SessionLocal()
    try:
        user = update.effective_user
        db_user = get_or_create_user(db, user.id)
        
        # Период - текущий месяц
        today = date.today()
        first_day = date(today.year, today.month, 1)
        
        # Общая статистика за месяц
        month_stats = get_balance(db, db_user.id, start_date=first_day, end_date=today)
        
        # Статистика по категориям расходов
        expense_stats = get_statistics_by_category(
            db, db_user.id, TType.EXPENSE, start_date=first_day, end_date=today
        )
        
        # Статистика по категориям доходов
        income_stats = get_statistics_by_category(
            db, db_user.id, TType.INCOME, start_date=first_day, end_date=today
        )
        
        # Средний дневной расход
        avg_daily = get_average_daily_expense(db, db_user.id, start_date=first_day, end_date=today)
        
        stats_text = f"""
📈 *Статистика за текущий месяц*

*Общие показатели:*
💰 Доходы: {format_amount(month_stats['income'])}
💸 Расходы: {format_amount(month_stats['expense'])}
💵 Баланс: {format_amount(month_stats['balance'])}
📊 Средний расход в день: {format_amount(avg_daily)}
        """
        
        # Топ-5 категорий расходов
        if expense_stats:
            stats_text += "\n*Топ расходов по категориям:*\n"
            for i, stat in enumerate(expense_stats[:5], 1):
                percentage = (stat['total'] / month_stats['expense'] * 100) if month_stats['expense'] > 0 else 0
                stats_text += f"{i}. {stat['icon']} {stat['name']}: {format_amount(stat['total'])} ({percentage:.1f}%)\n"
        
        # Топ-5 категорий доходов
        if income_stats:
            stats_text += "\n*Топ доходов по категориям:*\n"
            for i, stat in enumerate(income_stats[:5], 1):
                percentage = (stat['total'] / month_stats['income'] * 100) if month_stats['income'] > 0 else 0
                stats_text += f"{i}. {stat['icon']} {stat['name']}: {format_amount(stat['total'])} ({percentage:.1f}%)\n"
        
        if not expense_stats and not income_stats:
            stats_text += "\n📭 Нет транзакций за этот период"
        
        await update.message.reply_text(
            stats_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при показе статистики: {e}")
        await update.message.reply_text("❌ Произошла ошибка при загрузке статистики.")
    finally:
        db.close()


async def ai_assistant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """AI ассистент."""
    await update.message.reply_text(
        "🤖 *AI Ассистент*\n\nЗадай мне вопрос о твоих финансах!\n\nПримеры:\n"
        "• Сколько я потратил на еду в этом месяце?\n"
        "• Покажи мои траты за последнюю неделю\n"
        "• На что я больше всего трачу?\n"
        "• Могу ли я позволить себе купить телефон за 50000?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_menu_keyboard()
    )
    
    # Сохраняем состояние для ожидания вопроса
    context.user_data["waiting_for_ai_question"] = True


async def handle_ai_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработать вопрос для AI ассистента."""
    if not context.user_data.get("waiting_for_ai_question"):
        return
    
    db = SessionLocal()
    try:
        user = update.effective_user
        db_user = get_or_create_user(db, user.id)
        
        question = update.message.text
        
        # Получаем данные пользователя для контекста
        today = date.today()
        first_day = date(today.year, today.month, 1)
        
        # Статистика за месяц
        month_stats = get_balance(db, db_user.id, start_date=first_day, end_date=today)
        
        # Последние транзакции
        recent_transactions = get_transactions_by_user(db, db_user.id, limit=10)
        
        # Статистика по категориям
        expense_stats = get_statistics_by_category(
            db, db_user.id, TType.EXPENSE, start_date=first_day, end_date=today
        )
        
        # Формируем контекст для Claude
        context_data = f"""
Данные пользователя за текущий месяц:
- Доходы: {month_stats['income']:.2f} руб
- Расходы: {month_stats['expense']:.2f} руб
- Баланс: {month_stats['balance']:.2f} руб

Топ категорий расходов:
"""
        for stat in expense_stats[:5]:
            context_data += f"- {stat['name']}: {stat['total']:.2f} руб ({stat['count']} операций)\n"
        
        context_data += "\nПоследние транзакции:\n"
        for trans in recent_transactions[:5]:
            trans_type = "Доход" if trans.type == TType.INCOME else "Расход"
            category_name = trans.category.name if trans.category else "Без категории"
            context_data += f"- {trans_type}: {trans.amount:.2f} руб - {category_name}"
            if trans.description:
                context_data += f" ({trans.description})"
            context_data += f" - {format_date(trans.date)}\n"
        
        # Отправляем запрос в Claude
        claude = ClaudeClient()
        
        prompt = f"""Ты финансовый ассистент. Пользователь задал вопрос о своих финансах.

Контекст с данными пользователя:
{context_data}

Вопрос пользователя: {question}

Ответь на вопрос пользователя на русском языке, используя предоставленные данные. Будь дружелюбным и полезным. Если данных недостаточно для ответа, скажи об этом."""
        
        await update.message.reply_text("🤔 Думаю...")
        
        response = claude.get_completion(prompt, max_tokens=512)
        
        await update.message.reply_text(
            f"🤖 *AI Ассистент*\n\n{response}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_keyboard()
        )
        
        # Сбрасываем флаг ожидания вопроса
        context.user_data["waiting_for_ai_question"] = False
        
    except Exception as e:
        logger.error(f"Ошибка в AI ассистенте: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при обработке вопроса. Попробуй позже.",
            reply_markup=get_main_menu_keyboard()
        )
        context.user_data["waiting_for_ai_question"] = False
    finally:
        db.close()


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать настройки."""
    db = SessionLocal()
    try:
        user = update.effective_user
        db_user = get_or_create_user(db, user.id)
        
        # Получаем текущие настройки
        settings = get_user_settings(db, db_user.id)
        currency = settings.get("currency", "RUB")
        month_start = settings.get("month_start", 1)
        
        settings_text = f"""
⚙️ *Настройки*

*Текущие настройки:*
💱 Валюта: {currency}
📅 Начало месяца: {month_start} число

Выбери настройку для изменения:
        """
        
        await update.message.reply_text(
            settings_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_settings_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при показе настроек: {e}")
        await update.message.reply_text("❌ Произошла ошибка.")
    finally:
        db.close()


async def handle_transaction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработать callback для редактирования/удаления транзакции."""
    query = update.callback_query
    await query.answer()
    
    db = SessionLocal()
    try:
        user = update.effective_user
        db_user = get_or_create_user(db, user.id)
        
        callback_data = query.data
        
        if callback_data.startswith("edit_transaction_"):
            transaction_id = int(callback_data.split("_")[2])
            transaction = get_transaction_by_id(db, transaction_id)
            
            if not transaction or transaction.user_id != db_user.id:
                await query.edit_message_text("❌ Транзакция не найдена.")
                return
            
            # Сохраняем ID транзакции для редактирования
            context.user_data["editing_transaction_id"] = transaction_id
            context.user_data["editing_transaction"] = {
                "amount": transaction.amount,
                "category_id": transaction.category_id,
                "date": transaction.date,
                "description": transaction.description
            }
            
            # Показываем меню редактирования
            icon = "➕" if transaction.type == TType.INCOME else "➖"
            category_name = transaction.category.name if transaction.category else "Без категории"
            
            edit_text = f"""
✏️ *Редактирование транзакции*

{icon} Сумма: {format_amount(transaction.amount)}
📊 Категория: {category_name}
📅 Дата: {format_date(transaction.date)}
💬 Описание: {transaction.description or "Нет"}

Выбери поле для редактирования:
            """
            
            await query.edit_message_text(
                edit_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_edit_transaction_keyboard()
            )
            return
        
        elif callback_data.startswith("delete_transaction_"):
            transaction_id = int(callback_data.split("_")[2])
            transaction = get_transaction_by_id(db, transaction_id)
            
            if not transaction or transaction.user_id != db_user.id:
                await query.edit_message_text("❌ Транзакция не найдена.")
                return
            
            # Удаляем транзакцию
            delete_transaction(db, transaction_id)
            
            await query.edit_message_text(
                "✅ Транзакция удалена!",
                reply_markup=None
            )
            await query.message.reply_text(
                "Выбери действие из меню:",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
    except Exception as e:
        logger.error(f"Ошибка при обработке транзакции: {e}")
        await query.edit_message_text("❌ Произошла ошибка.")
    finally:
        db.close()


async def handle_edit_transaction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработать callback для редактирования полей транзакции."""
    query = update.callback_query
    await query.answer()
    
    db = SessionLocal()
    try:
        user = update.effective_user
        db_user = get_or_create_user(db, user.id)
        
        transaction_id = context.user_data.get("editing_transaction_id")
        if not transaction_id:
            await query.edit_message_text("❌ Сессия редактирования истекла.")
            return ConversationHandler.END
        
        transaction = get_transaction_by_id(db, transaction_id)
        if not transaction or transaction.user_id != db_user.id:
            await query.edit_message_text("❌ Транзакция не найдена.")
            return ConversationHandler.END
        
        callback_data = query.data
        
        if callback_data == "edit_field_amount":
            await query.edit_message_text(
                "💰 *Редактирование суммы*\n\nВведи новую сумму:",
                parse_mode=ParseMode.MARKDOWN
            )
            context.user_data["editing_field"] = "amount"
            return EDIT_AMOUNT
        
        elif callback_data == "edit_field_category":
            categories = get_categories_by_user(db, db_user.id, transaction_type=transaction.type)
            if not categories:
                await query.edit_message_text("❌ Нет доступных категорий.")
                return ConversationHandler.END
            
            await query.edit_message_text(
                "📊 *Выбери новую категорию:*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_categories_inline_keyboard(categories, transaction.type)
            )
            context.user_data["editing_field"] = "category"
            return EDIT_CATEGORY
        
        elif callback_data == "edit_field_date":
            await query.edit_message_text(
                "📅 *Редактирование даты*\n\nВведи новую дату в формате ДД.ММ.ГГГГ:",
                parse_mode=ParseMode.MARKDOWN
            )
            context.user_data["editing_field"] = "date"
            return EDIT_DATE
        
        elif callback_data == "edit_field_description":
            await query.edit_message_text(
                "💬 *Редактирование описания*\n\nВведи новое описание (или /skip чтобы удалить):",
                parse_mode=ParseMode.MARKDOWN
            )
            context.user_data["editing_field"] = "description"
            return EDIT_DESCRIPTION
        
        elif callback_data == "edit_save":
            # Сохраняем изменения
            editing_data = context.user_data.get("editing_transaction", {})
            update_transaction(
                db=db,
                transaction_id=transaction_id,
                amount=editing_data.get("amount"),
                category_id=editing_data.get("category_id"),
                date=editing_data.get("date"),
                description=editing_data.get("description")
            )
            
            # Очищаем данные редактирования
            context.user_data.pop("editing_transaction_id", None)
            context.user_data.pop("editing_transaction", None)
            context.user_data.pop("editing_field", None)
            
            await query.edit_message_text(
                "✅ Транзакция успешно обновлена!",
                reply_markup=None
            )
            await query.message.reply_text(
                "Выбери действие из меню:",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
        elif callback_data == "edit_cancel":
            # Отменяем редактирование
            context.user_data.pop("editing_transaction_id", None)
            context.user_data.pop("editing_transaction", None)
            context.user_data.pop("editing_field", None)
            
            await query.edit_message_text(
                "❌ Редактирование отменено.",
                reply_markup=None
            )
            await query.message.reply_text(
                "Выбери действие из меню:",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Ошибка при редактировании транзакции: {e}")
        await query.edit_message_text("❌ Произошла ошибка.")
    finally:
        db.close()
    
    return ConversationHandler.END


async def process_edit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработать ввод новой суммы."""
    amount = parse_amount(update.message.text)
    
    if amount is None or amount <= 0:
        await update.message.reply_text("❌ Неверная сумма. Попробуй еще раз:")
        return EDIT_AMOUNT
    
    editing_data = context.user_data.get("editing_transaction", {})
    editing_data["amount"] = amount
    context.user_data["editing_transaction"] = editing_data
    
    await update.message.reply_text(
        f"✅ Сумма изменена на {format_amount(amount)}\n\nВыбери следующее поле для редактирования:",
        reply_markup=get_edit_transaction_keyboard()
    )
    
    return ConversationHandler.END


async def process_edit_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработать выбор новой категории."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "no_categories":
        await query.edit_message_text("❌ Нет доступных категорий.")
        return ConversationHandler.END
    
    category_id = int(query.data.split("_")[1])
    
    editing_data = context.user_data.get("editing_transaction", {})
    editing_data["category_id"] = category_id
    context.user_data["editing_transaction"] = editing_data
    
    db = SessionLocal()
    try:
        category = get_category_by_id(db, category_id)
        category_name = category.name if category else "Без категории"
        await query.edit_message_text(
            f"✅ Категория изменена на {category_name}\n\nВыбери следующее поле для редактирования:",
            reply_markup=get_edit_transaction_keyboard()
        )
    finally:
        db.close()
    
    return ConversationHandler.END


async def process_edit_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработать ввод новой даты."""
    date_text = update.message.text.strip()
    
    try:
        # Парсим дату в формате ДД.ММ.ГГГГ
        parsed_date = datetime.strptime(date_text, "%d.%m.%Y").date()
        
        editing_data = context.user_data.get("editing_transaction", {})
        editing_data["date"] = parsed_date
        context.user_data["editing_transaction"] = editing_data
        
        await update.message.reply_text(
            f"✅ Дата изменена на {format_date(parsed_date)}\n\nВыбери следующее поле для редактирования:",
            reply_markup=get_edit_transaction_keyboard()
        )
        
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Неверный формат даты. Используй ДД.ММ.ГГГГ (например, 13.11.2024):")
        return EDIT_DATE


async def process_edit_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработать ввод нового описания."""
    description = update.message.text
    
    editing_data = context.user_data.get("editing_transaction", {})
    editing_data["description"] = description
    context.user_data["editing_transaction"] = editing_data
    
    await update.message.reply_text(
        f"✅ Описание изменено\n\nВыбери следующее поле для редактирования:",
        reply_markup=get_edit_transaction_keyboard()
    )
    
    return ConversationHandler.END


async def skip_edit_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропустить описание (удалить)."""
    editing_data = context.user_data.get("editing_transaction", {})
    editing_data["description"] = None
    context.user_data["editing_transaction"] = editing_data
    
    await update.message.reply_text(
        "✅ Описание удалено\n\nВыбери следующее поле для редактирования:",
        reply_markup=get_edit_transaction_keyboard()
    )
    
    return ConversationHandler.END


async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработать callback от настроек."""
    query = update.callback_query
    await query.answer()
    
    db = SessionLocal()
    try:
        user = update.effective_user
        db_user = get_or_create_user(db, user.id)
        
        callback_data = query.data
        
        if callback_data == "settings_back":
            await query.edit_message_text(
                "⚙️ Настройки закрыты.",
                reply_markup=None
            )
            await query.message.reply_text(
                "Выбери действие из меню:",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        elif callback_data == "setting_currency":
            await query.edit_message_text(
                "💱 *Выбери валюту:*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_currency_keyboard()
            )
            return
        
        elif callback_data == "setting_month_start":
            await query.edit_message_text(
                "📅 *Выбери начало месяца (1-31 число):*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_month_start_keyboard()
            )
            return
        
        elif callback_data.startswith("currency_"):
            currency_code = callback_data.split("_")[1]
            currency_symbols = {
                "RUB": "₽",
                "USD": "$",
                "EUR": "€",
                "UAH": "₴",
                "KZT": "₸"
            }
            symbol = currency_symbols.get(currency_code, currency_code)
            
            update_user_settings(db, db_user.id, {"currency": currency_code})
            
            await query.edit_message_text(
                f"✅ Валюта изменена на {symbol} {currency_code}",
                reply_markup=None
            )
            await query.message.reply_text(
                "Выбери действие из меню:",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        elif callback_data.startswith("month_start_"):
            day = int(callback_data.split("_")[2])
            update_user_settings(db, db_user.id, {"month_start": day})
            
            await query.edit_message_text(
                f"✅ Начало месяца установлено на {day} число",
                reply_markup=None
            )
            await query.message.reply_text(
                "Выбери действие из меню:",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
    except Exception as e:
        logger.error(f"Ошибка при обработке настроек: {e}")
        await query.edit_message_text("❌ Произошла ошибка.")
    finally:
        db.close()


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработать загрузку документа (выписки)."""
    document = update.message.document
    
    if not document:
        await update.message.reply_text("❌ Файл не найден.")
        return
    
    # Проверяем размер файла (максимум 20MB)
    if document.file_size and document.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ Файл слишком большой. Максимальный размер: 20MB")
        return
    
    # Определяем тип файла
    file_name = document.file_name.lower() if document.file_name else ""
    file_extension = file_name.split(".")[-1] if "." in file_name else ""
    
    supported_formats = ["pdf", "csv", "xlsx", "xls"]
    if file_extension not in supported_formats:
        await update.message.reply_text(
            f"❌ Неподдерживаемый формат файла.\n\nПоддерживаемые форматы: PDF, CSV, Excel (.xlsx, .xls)"
        )
        return
    
    db = SessionLocal()
    try:
        user = update.effective_user
        db_user = get_or_create_user(db, user.id)
        
        # Получаем категории пользователя для категоризации
        categories = get_categories_by_user(db, db_user.id)
        categories_list = [{"name": cat.name, "icon": cat.icon} for cat in categories]
        
        await update.message.reply_text("📄 Обрабатываю файл выписки...")
        
        # Скачиваем файл
        file = await context.bot.get_file(document.file_id)
        file_bytes = await file.download_as_bytearray()
        
        # Парсим файл в зависимости от формата
        transactions = []
        
        if file_extension == "pdf":
            transactions = parse_pdf_statement(bytes(file_bytes), categories_list)
        elif file_extension == "csv":
            transactions = parse_csv_statement(bytes(file_bytes))
            # Категоризируем через Claude если категории не определены
            if transactions and not transactions[0].get("category_name"):
                transactions = categorize_transactions_batch(transactions, categories_list)
        elif file_extension in ["xlsx", "xls"]:
            transactions = parse_excel_statement(bytes(file_bytes))
            if transactions and not transactions[0].get("category_name"):
                transactions = categorize_transactions_batch(transactions, categories_list)
        
        if not transactions:
            await update.message.reply_text(
                "❌ Не удалось извлечь транзакции из файла. Проверьте формат файла.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Сохраняем транзакции для предпросмотра
        context.user_data["pending_import"] = transactions
        
        # Подсчитываем статистику
        total_income = sum(t["amount"] for t in transactions if t["type"] == "income")
        total_expense = sum(t["amount"] for t in transactions if t["type"] == "expense")
        
        # Получаем настройки пользователя для форматирования
        user_settings = get_user_settings(db, db_user.id)
        
        # Формируем предпросмотр
        preview_text = f"""
📄 *Предпросмотр импорта выписки*

Найдено транзакций: *{len(transactions)}*

*Суммы:*
💰 Доходы: {format_amount(total_income, user_settings=user_settings)}
💸 Расходы: {format_amount(total_expense, user_settings=user_settings)}
💵 Баланс: {format_amount(total_income - total_expense, user_settings=user_settings)}

*Примеры транзакций (первые 5):*
        """
        
        for i, trans in enumerate(transactions[:5], 1):
            icon = "➕" if trans["type"] == "income" else "➖"
            category = trans.get("category_name", "Прочее")
            preview_text += f"\n{i}. {icon} {format_amount(trans['amount'], user_settings=user_settings)} - {category}"
            if trans.get("description"):
                preview_text += f"\n   {trans['description'][:50]}"
            preview_text += f"\n   {format_date(trans['date'])}\n"
        
        if len(transactions) > 5:
            preview_text += f"\n... и еще {len(transactions) - 5} транзакций"
        
        preview_text += "\n\nВыбери действие:"
        
        await update.message.reply_text(
            preview_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_import_confirmation_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Ошибка при обработке выписки: {e}")
        await update.message.reply_text(
            f"❌ Произошла ошибка при обработке файла: {str(e)}",
            reply_markup=get_main_menu_keyboard()
        )
    finally:
        db.close()


async def handle_import_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработать callback для импорта выписки."""
    query = update.callback_query
    await query.answer()
    
    db = SessionLocal()
    try:
        user = update.effective_user
        db_user = get_or_create_user(db, user.id)
        
        callback_data = query.data
        transactions = context.user_data.get("pending_import", [])
        
        if not transactions:
            await query.edit_message_text("❌ Данные для импорта не найдены.")
            return
        
        if callback_data == "import_confirm_all":
            # Массовое добавление всех транзакций
            await query.edit_message_text("⏳ Добавляю транзакции...")
            
            # Преобразуем категории из имен в ID
            categories_dict = {cat.name: cat.id for cat in get_categories_by_user(db, db_user.id)}
            
            transactions_to_import = []
            for trans in transactions:
                trans_data = {
                    "date": trans["date"],
                    "amount": trans["amount"],
                    "type": trans["type"],
                    "description": trans.get("description", ""),
                    "category_name": trans.get("category_name", "Прочее")
                }
                transactions_to_import.append(trans_data)
            
            created_count, skipped_count = bulk_create_transactions(
                db, db_user.id, transactions_to_import
            )
            
            result_text = f"""
✅ *Импорт завершен!*

Добавлено транзакций: *{created_count}*
Пропущено (дубликаты): *{skipped_count}*

Статистика автоматически обновлена!
            """
            
            await query.edit_message_text(
                result_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=None
            )
            await query.message.reply_text(
                "Выбери действие из меню:",
                reply_markup=get_main_menu_keyboard()
            )
            
            # Очищаем данные импорта
            context.user_data.pop("pending_import", None)
            
        elif callback_data == "import_edit":
            # Показываем список для редактирования
            await query.edit_message_text(
                "✏️ Редактирование транзакций перед импортом будет доступно в следующей версии.\n\nИспользуй '✅ Добавить все' для импорта.",
                reply_markup=get_import_confirmation_keyboard()
            )
            
        elif callback_data == "import_cancel":
            context.user_data.pop("pending_import", None)
            await query.edit_message_text(
                "❌ Импорт отменен.",
                reply_markup=None
            )
            await query.message.reply_text(
                "Выбери действие из меню:",
                reply_markup=get_main_menu_keyboard()
            )
            
    except Exception as e:
        logger.error(f"Ошибка при импорте транзакций: {e}")
        await query.edit_message_text("❌ Произошла ошибка при импорте.")
    finally:
        db.close()


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений."""
    text = update.message.text
    
    # Проверяем, ожидается ли вопрос для AI
    if context.user_data.get("waiting_for_ai_question"):
        await handle_ai_question(update, context)
        return
    
    # Проверяем, не является ли это командой из меню
    menu_commands = {
        "➕ Добавить доход": add_income_start,
        "➖ Добавить расход": add_expense_start,
        "💰 Баланс": show_balance,
        "📊 Категории": show_categories,
        "📜 История": show_history,
        "📈 Статистика": show_statistics,
        "🤖 AI Ассистент": ai_assistant,
        "⚙️ Настройки": show_settings
    }
    
    if text in menu_commands:
        await menu_commands[text](update, context)
    else:
        # Обычное текстовое сообщение - можно использовать для AI парсинга
        await update.message.reply_text(
            "💡 Отправь команду из меню или используй кнопки ниже.\n\n💡 Также можно отправить файл выписки (PDF, CSV, Excel) для автоматического импорта транзакций!",
            reply_markup=get_main_menu_keyboard()
        )


def create_income_conversation():
    """Создать ConversationHandler для добавления дохода."""
    return ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Добавить доход$"), add_income_start)],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_amount)],
            CATEGORY: [CallbackQueryHandler(process_category, pattern="^category_")],
            DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_description),
                CommandHandler("skip", skip_description)
            ],
            CONFIRM: [
                CallbackQueryHandler(confirm_transaction, pattern="^confirm$"),
                CallbackQueryHandler(cancel_transaction, pattern="^cancel$")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_transaction)],
        per_message=True
    )


def create_expense_conversation():
    """Создать ConversationHandler для добавления расхода."""
    return ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➖ Добавить расход$"), add_expense_start)],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_amount)],
            CATEGORY: [CallbackQueryHandler(process_category, pattern="^category_")],
            DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_description),
                CommandHandler("skip", skip_description)
            ],
            CONFIRM: [
                CallbackQueryHandler(confirm_transaction, pattern="^confirm$"),
                CallbackQueryHandler(cancel_transaction, pattern="^cancel$")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_transaction)],
        per_message=True
    )


def create_edit_transaction_conversation():
    """Создать ConversationHandler для редактирования транзакции."""
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_edit_transaction_callback, pattern="^edit_field_|^edit_save$|^edit_cancel$")],
        states={
            EDIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_amount)],
            EDIT_CATEGORY: [CallbackQueryHandler(process_edit_category, pattern="^category_")],
            EDIT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_date)],
            EDIT_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_description),
                CommandHandler("skip", skip_edit_description)
            ]
        },
        fallbacks=[CommandHandler("cancel", skip_edit_description)],
        per_message=True
    )


def main():
    """Запустить бота."""
    # Настройка логирования
    logger.add("logs/bot.log", rotation="10 MB", level="INFO")
    
    # Создание приложения
    application = Application.builder().token(settings.telegram_bot_token).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(create_income_conversation())
    application.add_handler(create_expense_conversation())
    application.add_handler(create_edit_transaction_conversation())
    application.add_handler(CallbackQueryHandler(handle_transaction_callback, pattern="^(edit_transaction_|delete_transaction_)"))
    application.add_handler(CallbackQueryHandler(handle_settings_callback, pattern="^(setting_|currency_|month_start_|settings_back)"))
    application.add_handler(CallbackQueryHandler(handle_import_callback, pattern="^import_"))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запуск бота
    logger.info("Бот запущен")
    try:
        # Используем webhook на Railway вместо polling для избежания конфликтов
        # Но если webhook не настроен, используем polling с обработкой конфликтов
        import os
        webhook_url = os.getenv("WEBHOOK_URL")
        
        if webhook_url:
            # Webhook режим для продакшена
            application.run_webhook(
                listen="0.0.0.0",
                port=int(os.getenv("PORT", "8000")),
                webhook_url=webhook_url,
                drop_pending_updates=True
            )
        else:
            # Polling режим для разработки
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,  # Игнорировать старые обновления при перезапуске
                close_loop=False  # Не закрывать event loop при ошибках
            )
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        # Не падаем при конфликте getUpdates - просто логируем и ждем
        if "Conflict" in str(e) or "getUpdates" in str(e):
            logger.warning("Конфликт getUpdates - возможно запущен другой экземпляр бота. Ожидание...")
            import time
            time.sleep(5)
            # Пробуем еще раз
            try:
                if webhook_url:
                    application.run_webhook(
                        listen="0.0.0.0",
                        port=int(os.getenv("PORT", "8000")),
                        webhook_url=webhook_url,
                        drop_pending_updates=True
                    )
                else:
                    application.run_polling(
                        allowed_updates=Update.ALL_TYPES,
                        drop_pending_updates=True,
                        close_loop=False
                    )
            except Exception as retry_error:
                logger.error(f"Ошибка при повторной попытке запуска: {retry_error}")
                raise
        else:
            raise


if __name__ == "__main__":
    main()

