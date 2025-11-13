# Инструкция по установке и запуску

## Предварительные требования

- Python 3.9 или выше
- PostgreSQL 12 или выше
- Telegram Bot Token (получить у @BotFather)
- Claude API Key (получить на https://console.anthropic.com/)

## Установка

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd finance-bot
```

### 2. Создание виртуального окружения

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка переменных окружения

Создайте файл `.env` в корне проекта:

```bash
cp .env.example .env
```

Отредактируйте `.env` и заполните следующие переменные:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
CLAUDE_API_KEY=your_claude_api_key_here
DATABASE_URL=postgresql://user:password@localhost:5432/finance_bot
ENVIRONMENT=development
LOG_LEVEL=INFO
```

### 5. Настройка базы данных

1. Создайте базу данных PostgreSQL:

```sql
CREATE DATABASE finance_bot;
```

2. Примените миграции:

```bash
alembic upgrade head
```

### 6. Запуск бота

```bash
python run.py
```

или

```bash
python bot/main.py
```

## Структура проекта

```
finance-bot/
├── bot/                 # Логика Telegram бота
│   ├── main.py         # Основной файл бота
│   └── keyboards.py    # Клавиатуры
├── database/            # Модели и CRUD операции
│   ├── models.py       # SQLAlchemy модели
│   ├── crud.py         # CRUD операции
│   └── connection.py   # Подключение к БД
├── ai/                  # Claude API интеграции
│   └── claude_client.py
├── utils/               # Вспомогательные функции
│   ├── helpers.py
│   └── default_categories.py
├── config/              # Конфигурация
│   └── settings.py
├── alembic/             # Миграции БД
│   └── versions/
└── requirements.txt
```

## Использование

После запуска бота:

1. Найдите вашего бота в Telegram
2. Отправьте команду `/start`
3. Используйте кнопки меню для управления финансами

## Разработка

### Создание новой миграции

```bash
alembic revision --autogenerate -m "Описание изменений"
alembic upgrade head
```

### Логи

Логи сохраняются в директории `logs/bot.log`

## Деплой на Railway

1. Создайте аккаунт на [Railway](https://railway.app/)
2. Подключите GitHub репозиторий
3. Добавьте PostgreSQL addon
4. Настройте переменные окружения в Railway
5. Railway автоматически задеплоит приложение

## Поддержка

При возникновении проблем проверьте:
- Правильность переменных окружения в `.env`
- Подключение к базе данных
- Логи в `logs/bot.log`

