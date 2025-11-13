"""Точка входа для запуска бота."""
import sys
import subprocess
from bot.main import main
from loguru import logger

def run_migrations():
    """Применить миграции базы данных."""
    try:
        logger.info("Applying database migrations...")
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            check=True
        )
        logger.info("Migrations applied successfully")
        logger.debug(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to apply migrations: {e}")
        logger.error(f"Error output: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during migrations: {e}")
        return False

if __name__ == "__main__":
    # Пытаемся применить миграции перед запуском
    # Если не получится, продолжаем запуск (миграции можно применить вручную)
    migration_success = run_migrations()
    if not migration_success:
        logger.warning("Migrations failed, but continuing with bot startup...")
        logger.warning("You may need to run migrations manually: alembic upgrade head")
    
    # Запускаем бота
    main()

