"""Обработка чеков через Claude Vision API."""
import base64
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger
from ai.claude_client import ClaudeClient


def process_receipt_image(image_bytes: bytes, user_categories: list) -> Optional[Dict[str, Any]]:
    """
    Обработать изображение чека через Claude Vision API.
    
    Args:
        image_bytes: Байты изображения чека
        user_categories: Список категорий пользователя
    
    Returns:
        dict: Структурированные данные чека или None при ошибке
        {
            "store_name": str,
            "receipt_date": datetime,
            "total_amount": float,
            "vat_amount": float,
            "receipt_number": str,
            "items": [{"name": str, "price": float, "quantity": float, "total": float}],
            "suggested_category": str,
            "raw_data": dict
        }
    """
    try:
        # Конвертируем изображение в base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Получаем список категорий для промпта
        categories_str = ", ".join([cat["name"] for cat in user_categories])
        
        # Формируем промпт для Claude
        prompt = f"""Проанализируй изображение чека и извлеки следующую информацию:

1. Название магазина/организации
2. Дата и время покупки (в формате YYYY-MM-DD HH:MM)
3. Общая сумма чека
4. Сумма НДС (если указана)
5. Номер чека/кассы (если есть)
6. Список всех товаров/услуг с ценами

Категоризируй покупку в одну из категорий: {categories_str}

Верни результат СТРОГО в формате:

Магазин: [название]
Дата: [YYYY-MM-DD HH:MM]
Сумма: [число]
НДС: [число или 0]
Номер чека: [номер или нет]
Категория: [название категории]

Товары:
1. [название товара] - [количество] x [цена] = [сумма]
2. [название товара] - [количество] x [цена] = [сумма]
...

Если какая-то информация не видна на чеке, укажи "нет" или пропусти."""

        # Запрос к Claude
        claude = ClaudeClient()
        
        try:
            # Используем Vision API через messages.create
            message = claude.client.messages.create(
                model=claude.model,
                max_tokens=2048,
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
            
            # Извлекаем текст из ответа
            response_text = ""
            if message.content and len(message.content) > 0:
                first_content = message.content[0]
                if hasattr(first_content, 'text'):
                    response_text = first_content.text
                elif isinstance(first_content, dict) and 'text' in first_content:
                    response_text = first_content['text']
                else:
                    response_text = str(first_content)
            
            logger.info(f"Ответ Claude для чека (первые 500 символов): {response_text[:500]}")
            
            # Парсим ответ
            parsed_data = parse_receipt_text(response_text, user_categories)
            
            if parsed_data:
                # Сохраняем base64 изображения для БД
                parsed_data["image_base64"] = image_base64
                return parsed_data
            else:
                logger.warning("Не удалось распарсить ответ Claude для чека")
                return None
                
        except Exception as api_error:
            logger.error(f"Ошибка при запросе к Claude API: {api_error}")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при обработке чека: {e}")
        return None


def parse_receipt_text(text: str, user_categories: list) -> Optional[Dict[str, Any]]:
    """
    Парсить текстовый ответ Claude с данными чека.
    
    Args:
        text: Текстовый ответ от Claude
        user_categories: Список категорий пользователя
    
    Returns:
        dict: Распарсенные данные чека
    """
    import re
    
    result = {
        "store_name": None,
        "receipt_date": None,
        "total_amount": 0.0,
        "vat_amount": 0.0,
        "receipt_number": None,
        "suggested_category": "Прочее",
        "items": [],
        "raw_data": {"response_text": text}
    }
    
    try:
        # Извлекаем магазин
        store_match = re.search(r'Магазин:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
        if store_match:
            result["store_name"] = store_match.group(1).strip()
        
        # Извлекаем дату
        date_match = re.search(r'Дата:\s*(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2})?)', text, re.IGNORECASE)
        if date_match:
            date_str = date_match.group(1).strip()
            try:
                # Пробуем с временем
                if ' ' in date_str:
                    result["receipt_date"] = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
                else:
                    result["receipt_date"] = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                logger.warning(f"Не удалось распарсить дату: {date_str}")
                result["receipt_date"] = datetime.now()
        else:
            result["receipt_date"] = datetime.now()
        
        # Извлекаем сумму
        amount_match = re.search(r'Сумма:\s*([\d\s,\.]+)', text, re.IGNORECASE)
        if amount_match:
            amount_str = amount_match.group(1).replace(" ", "").replace(",", ".")
            try:
                result["total_amount"] = float(amount_str)
            except ValueError:
                logger.warning(f"Не удалось распарсить сумму: {amount_str}")
        
        # Извлекаем НДС
        vat_match = re.search(r'НДС:\s*([\d\s,\.]+)', text, re.IGNORECASE)
        if vat_match:
            vat_str = vat_match.group(1).replace(" ", "").replace(",", ".")
            try:
                result["vat_amount"] = float(vat_str)
            except ValueError:
                pass
        
        # Извлекаем номер чека
        number_match = re.search(r'Номер чека:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
        if number_match:
            number = number_match.group(1).strip()
            if number.lower() not in ["нет", "не указан", "отсутствует"]:
                result["receipt_number"] = number
        
        # Извлекаем категорию
        category_match = re.search(r'Категория:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
        if category_match:
            category_name = category_match.group(1).strip()
            # Убираем эмодзи
            category_name = re.sub(r'[^\w\s-]', '', category_name).strip()
            
            # Проверяем, есть ли такая категория у пользователя
            for cat in user_categories:
                cat_name_clean = re.sub(r'[^\w\s-]', '', cat['name']).strip()
                if cat_name_clean.lower() == category_name.lower():
                    result["suggested_category"] = cat['name']
                    break
            else:
                result["suggested_category"] = category_name
        
        # Извлекаем товары
        items_section = re.search(r'Товары:(.+?)(?:\n\n|$)', text, re.IGNORECASE | re.DOTALL)
        if items_section:
            items_text = items_section.group(1)
            # Паттерн: "1. Молоко 3.2% 1л - 1 x 89 = 89"
            item_pattern = r'\d+\.\s*(.+?)\s*-\s*([\d\.]+)\s*x\s*([\d\s,\.]+)\s*=\s*([\d\s,\.]+)'
            
            for item_match in re.finditer(item_pattern, items_text):
                try:
                    item_name = item_match.group(1).strip()
                    quantity = float(item_match.group(2).replace(",", "."))
                    price = float(item_match.group(3).replace(" ", "").replace(",", "."))
                    total = float(item_match.group(4).replace(" ", "").replace(",", "."))
                    
                    result["items"].append({
                        "name": item_name,
                        "quantity": quantity,
                        "price": price,
                        "total": total
                    })
                except Exception as e:
                    logger.warning(f"Ошибка при парсинге товара: {e}")
                    continue
        
        # Если не извлечено ни одного товара, пробуем более простой паттерн
        if not result["items"]:
            simple_pattern = r'\d+\.\s*(.+?)\s*-\s*([\d\s,\.]+)'
            for item_match in re.finditer(simple_pattern, text):
                try:
                    item_name = item_match.group(1).strip()
                    price = float(item_match.group(2).replace(" ", "").replace(",", "."))
                    
                    result["items"].append({
                        "name": item_name,
                        "quantity": 1.0,
                        "price": price,
                        "total": price
                    })
                except Exception as e:
                    continue
        
        # Валидация: должна быть хотя бы сумма
        if result["total_amount"] <= 0:
            logger.warning("Сумма чека не распознана или равна 0")
            return None
        
        logger.info(f"Распознан чек: {result['store_name']}, {result['total_amount']} ₽, товаров: {len(result['items'])}")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при парсинге текста чека: {e}")
        return None

