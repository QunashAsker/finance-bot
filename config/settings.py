"""Конфигурация приложения."""
from pydantic_settings import BaseSettings
from typing import Optional
import os


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
        env_file_encoding = "utf-8"
        # Читать переменные окружения (Railway автоматически их предоставляет)
        case_sensitive = False


# Глобальный экземпляр настроек
# Pydantic автоматически читает из переменных окружения, если .env файл не найден
settings = Settings()

