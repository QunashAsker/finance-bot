"""Конфигурация приложения."""
from pydantic_settings import BaseSettings
from typing import Optional
import os
import sys


class Settings(BaseSettings):
    """Настройки приложения."""
    
    # Telegram Bot
    telegram_bot_token: str
    
    # Claude API
    claude_api_key: str
    
    # Database
    database_url: str
    
    # Application
    environment: str = "development"
    log_level: str = "INFO"
    
    class Config:
        # Сначала пытаемся прочитать из .env файла (для локальной разработки)
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Переменные окружения имеют приоритет над .env файлом
        case_sensitive = False


# Глобальный экземпляр настроек
# Пытаемся создать с fallback на os.getenv для Railway
try:
    settings = Settings()
except Exception as e:
    # Если не удалось загрузить через pydantic, используем os.getenv
    print(f"Warning: Could not load settings via pydantic: {e}", file=sys.stderr)
    print("Falling back to os.getenv...", file=sys.stderr)
    
    # Проверяем переменные окружения напрямую
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    claude_api_key = os.getenv("CLAUDE_API_KEY")
    database_url = os.getenv("DATABASE_URL")
    
    if not telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
    if not claude_api_key:
        raise ValueError("CLAUDE_API_KEY environment variable is required")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is required")
    
    # Создаем объект настроек вручную
    class SettingsFromEnv:
        def __init__(self):
            self.telegram_bot_token = telegram_bot_token
            self.claude_api_key = claude_api_key
            self.database_url = database_url
            self.environment = os.getenv("ENVIRONMENT", "production")
            self.log_level = os.getenv("LOG_LEVEL", "INFO")
    
    settings = SettingsFromEnv()
    print("Settings loaded successfully from environment variables", file=sys.stderr)

