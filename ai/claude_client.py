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
            self.model = "claude-3-5-sonnet-20241022"
        except Exception as e:
            logger.error(f"Ошибка при инициализации Claude клиента: {e}")
            raise
    
    def get_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024
    ) -> str:
        """Получить ответ от Claude."""
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return message.content[0].text
        except Exception as e:
            logger.error(f"Ошибка при запросе к Claude API: {e}")
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

