"""Автокатегоризация транзакций через Claude AI."""
from typing import Dict, List, Optional, Any
from loguru import logger
from services.claude import ClaudeClient


def auto_categorize_transaction(
    merchant: str,
    description: str,
    user_categories: List[Dict[str, Any]],
    transaction_type: str = "expense"
) -> Dict[str, Any]:
    """
    Автоматически категоризировать транзакцию через Claude AI.
    
    Args:
        merchant: Название мерчанта (например "Перекрёсток")
        description: Описание транзакции
        user_categories: Список категорий пользователя
        transaction_type: Тип транзакции ("income" или "expense")
    
    Returns:
        dict: {
            "category_name": "Продукты",
            "category_id": 5,
            "suggested_description": "Покупка в Перекрёсток",
            "confidence": "high"  # high, medium, low
        }
    """
    try:
        # Фильтруем категории по типу транзакции
        filtered_categories = [
            cat for cat in user_categories 
            if cat.get("type") == transaction_type
        ]
        
        if not filtered_categories:
            logger.warning(f"Нет категорий для типа {transaction_type}")
            return {
                "category_name": "Прочее",
                "category_id": None,
                "suggested_description": f"{'Покупка' if transaction_type == 'expense' else 'Поступление'} {merchant}",
                "confidence": "low"
            }
        
        # Формируем список категорий для промпта
        categories_str = "\n".join([
            f"- {cat['icon']} {cat['name']}"
            for cat in filtered_categories
        ])
        
        # Промпт для Claude
        prompt = f"""Ты помощник для категоризации финансовых транзакций.

Мерчант: {merchant}
Описание: {description}
Тип транзакции: {"Расход" if transaction_type == "expense" else "Доход"}

Доступные категории:
{categories_str}

Задача:
1. Определи наиболее подходящую категорию из списка выше
2. Предложи краткое и понятное описание транзакции (до 50 символов)
3. Оцени уверенность в выборе категории (high/medium/low)

Верни результат СТРОГО в формате:
Категория: [название категории]
Описание: [предложенное описание]
Уверенность: [high/medium/low]

Примеры:
- Для "Перекрёсток" → Категория: Продукты, Описание: Покупка в Перекрёсток, Уверенность: high
- Для "Яндекс Такси" → Категория: Транспорт, Описание: Поездка на такси, Уверенность: high
- Для "Неизвестная покупка" → Категория: Прочее, Описание: Покупка, Уверенность: low"""

        # Запрос к Claude
        claude = ClaudeClient()
        response = claude.send_message(prompt)
        
        # Парсим ответ
        result = parse_categorization_response(response, filtered_categories)
        
        logger.info(f"Автокатегоризация '{merchant}': {result['category_name']} ({result['confidence']})")
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при автокатегоризации: {e}")
        # Возвращаем дефолтные значения
        return {
            "category_name": "Прочее",
            "category_id": None,
            "suggested_description": f"{'Покупка' if transaction_type == 'expense' else 'Поступление'} {merchant}",
            "confidence": "low"
        }


def parse_categorization_response(response: str, categories: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Парсить ответ Claude с результатом категоризации.
    
    Ожидаемый формат:
    Категория: Продукты
    Описание: Покупка в Перекрёсток
    Уверенность: high
    """
    import re
    
    result = {
        "category_name": "Прочее",
        "category_id": None,
        "suggested_description": "",
        "confidence": "low"
    }
    
    try:
        # Извлекаем категорию
        category_match = re.search(r'Категория:\s*(.+?)(?:\n|$)', response, re.IGNORECASE)
        if category_match:
            category_name = category_match.group(1).strip()
            # Убираем эмодзи если есть
            category_name = re.sub(r'[^\w\s-]', '', category_name).strip()
            result["category_name"] = category_name
            
            # Находим ID категории
            for cat in categories:
                cat_name_clean = re.sub(r'[^\w\s-]', '', cat['name']).strip()
                if cat_name_clean.lower() == category_name.lower():
                    result["category_id"] = cat['id']
                    result["category_name"] = cat['name']  # Используем оригинальное название
                    break
        
        # Извлекаем описание
        description_match = re.search(r'Описание:\s*(.+?)(?:\n|$)', response, re.IGNORECASE)
        if description_match:
            result["suggested_description"] = description_match.group(1).strip()
        
        # Извлекаем уверенность
        confidence_match = re.search(r'Уверенность:\s*(high|medium|low)', response, re.IGNORECASE)
        if confidence_match:
            result["confidence"] = confidence_match.group(1).lower()
        
    except Exception as e:
        logger.warning(f"Ошибка при парсинге ответа категоризации: {e}")
    
    return result


def suggest_merchant_description(merchant: str, transaction_type: str = "expense") -> str:
    """
    Предложить описание для мерчанта без использования AI.
    Быстрый fallback метод.
    
    Args:
        merchant: Название мерчанта
        transaction_type: Тип транзакции
    
    Returns:
        str: Предложенное описание
    """
    # Словарь популярных мерчантов с шаблонами описаний
    merchant_templates = {
        "перекрёсток": "Покупка в Перекрёсток",
        "пятёрочка": "Покупка в Пятёрочка",
        "магнит": "Покупка в Магнит",
        "лента": "Покупка в Лента",
        "ашан": "Покупка в Ашан",
        "дикси": "Покупка в Дикси",
        "вкусвилл": "Покупка в ВкусВилл",
        "яндекс такси": "Поездка на такси",
        "такси": "Поездка на такси",
        "макдональдс": "Еда в McDonald's",
        "kfc": "Еда в KFC",
        "бургер кинг": "Еда в Burger King",
        "subway": "Еда в Subway",
        "додо пицца": "Заказ пиццы",
        "аптека": "Покупка в аптеке",
        "аптечка": "Покупка в аптеке",
    }
    
    merchant_lower = merchant.lower().strip()
    
    # Проверяем точное совпадение
    if merchant_lower in merchant_templates:
        return merchant_templates[merchant_lower]
    
    # Проверяем частичное совпадение
    for key, template in merchant_templates.items():
        if key in merchant_lower or merchant_lower in key:
            return template
    
    # Дефолтные шаблоны
    if transaction_type == "expense":
        return f"Покупка {merchant}"
    else:
        return f"Поступление {merchant}"

