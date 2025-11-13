"""Клиент для работы с Claude API."""
from anthropic import Anthropic
from config.settings import settings
from typing import Optional, Dict, Any
import json
from loguru import logger


class ClaudeClient:
    """Клиент для взаимодействия с Claude API."""
    
    def __init__(self):
        """Инициализировать клиент Claude."""
        try:
            self.client = Anthropic(api_key=settings.claude_api_key)
            # Используем актуальное имя модели Claude 4 Sonnet согласно документации
            self.model = "claude-sonnet-4-20250514"  # Claude 4 Sonnet
        except Exception as e:
            logger.error(f"Ошибка при инициализации Claude клиента: {e}")
            raise
    
    def _try_models(self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 1024) -> str:
        """Попробовать разные модели если основная не работает."""
        # Список моделей согласно официальной документации Claude API
        models_to_try = [
            "claude-sonnet-4-20250514",  # Claude 4 Sonnet (рекомендуется)
            "claude-opus-4-1-20250805",  # Claude 4 Opus
            "claude-3-7-sonnet-20250219",  # Claude 3.7 Sonnet
            "claude-3-opus-20240229",  # Claude 3 Opus
            "claude-3-sonnet-20240229",  # Claude 3 Sonnet
            "claude-3-haiku-20240307"  # Claude 3 Haiku (быстрая и дешевая)
        ]
        
        for model_name in models_to_try:
            try:
                logger.info(f"Пробую модель: {model_name}")
                request_params = {
                    "model": model_name,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}]
                }
                
                if system_prompt:
                    request_params["system"] = system_prompt
                
                message = self.client.messages.create(**request_params)
                
                if message.content and len(message.content) > 0:
                    first_content = message.content[0]
                    if hasattr(first_content, 'text'):
                        logger.info(f"Успешно использована модель: {model_name}")
                        self.model = model_name  # Сохраняем рабочую модель
                        return first_content.text
                    elif isinstance(first_content, dict) and 'text' in first_content:
                        logger.info(f"Успешно использована модель: {model_name}")
                        self.model = model_name
                        return first_content['text']
            except Exception as e:
                logger.warning(f"Модель {model_name} не работает: {e}")
                continue
        
        raise ValueError("Ни одна из моделей Claude не доступна")
    
    def get_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024
    ) -> str:
        """Получить ответ от Claude."""
        try:
            # Формируем messages согласно документации Claude API
            # content может быть строкой или массивом объектов с type и text
            messages = [
                {
                    "role": "user",
                    "content": prompt  # Простая строка работает в новом API
                }
            ]
            
            # Формируем параметры запроса
            request_params = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": messages
            }
            
            # Если есть system prompt, добавляем его как строку (согласно документации)
            if system_prompt:
                request_params["system"] = system_prompt
            
            message = self.client.messages.create(**request_params)
            
            # Извлекаем текст из ответа
            # response.content - это массив объектов с type и text
            if message.content and len(message.content) > 0:
                # Проверяем тип первого элемента
                first_content = message.content[0]
                if hasattr(first_content, 'text'):
                    return first_content.text
                elif isinstance(first_content, dict) and 'text' in first_content:
                    return first_content['text']
                else:
                    # Если это объект TextBlock
                    return str(first_content)
            else:
                raise ValueError("Пустой ответ от Claude API")
        except Exception as e:
            logger.error(f"Ошибка при запросе к Claude API: {e}")
            logger.error(f"Тип ошибки: {type(e)}")
            raise
    
    def analyze_receipt(
        self,
        image_base64: str,
        user_categories: list
    ) -> Dict[str, Any]:
        """Проанализировать чек и извлечь данные."""
        categories_str = ", ".join([cat["name"] for cat in user_categories])
        
        prompt = f"""Проанализируй изображение чека и извлеки следующую информацию в формате JSON:
{{
    "total_amount": сумма покупки (число),
    "date": дата покупки в формате YYYY-MM-DD (если видна),
    "store_name": название магазина (если видно),
    "items": список товаров (массив строк, опционально),
    "suggested_category": наиболее подходящая категория из списка: {categories_str}
}}

Если какая-то информация не видна, укажи null. Отвечай только JSON без дополнительного текста."""
        
        try:
            # Формируем content как массив для мультимодального запроса
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )
            
            response_text = message.content[0].text
            # Извлекаем JSON из ответа
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
            else:
                raise ValueError("Не удалось найти JSON в ответе")
        except Exception as e:
            logger.error(f"Ошибка при анализе чека: {e}")
            raise
    
    def parse_transaction_text(
        self,
        text: str,
        user_categories: list
    ) -> Dict[str, Any]:
        """Распарсить текстовое описание транзакции."""
        categories_str = ", ".join([cat["name"] for cat in user_categories])
        
        prompt = f"""Проанализируй следующее текстовое сообщение о финансовой транзакции и извлеки данные в формате JSON:
{{
    "type": "income" или "expense",
    "amount": сумма (число),
    "category": название категории из списка: {categories_str},
    "description": описание транзакции (если есть)
}}

Примеры:
- "потратил 500 на такси" -> {{"type": "expense", "amount": 500, "category": "Транспорт", "description": "такси"}}
- "получил 3000 зарплата" -> {{"type": "income", "amount": 3000, "category": "Зарплата", "description": "зарплата"}}

Отвечай только JSON без дополнительного текста.

Текст пользователя: {text}"""
        
        try:
            response = self.get_completion(prompt, max_tokens=512)
            # Извлекаем JSON из ответа
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            else:
                raise ValueError("Не удалось найти JSON в ответе")
        except Exception as e:
            logger.error(f"Ошибка при парсинге текста транзакции: {e}")
            raise
    
    def suggest_category(
        self,
        description: str,
        user_categories: list,
        recent_transactions: list
    ) -> str:
        """Предложить категорию на основе описания."""
        categories_str = ", ".join([cat["name"] for cat in user_categories])
        recent_str = "\n".join([f"- {t.description}" for t in recent_transactions[:5]])
        
        prompt = f"""На основе описания транзакции "{description}" и последних транзакций пользователя, предложи наиболее подходящую категорию из списка: {categories_str}

Последние транзакции:
{recent_str}

Отвечай только названием категории без дополнительного текста."""
        
        try:
            response = self.get_completion(prompt, max_tokens=64)
            return response.strip()
        except Exception as e:
            logger.error(f"Ошибка при предложении категории: {e}")
            return None

