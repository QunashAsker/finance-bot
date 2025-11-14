"""Утилита для парсинга текста транзакций."""
import re
from typing import Optional, Dict, Any
from loguru import logger


def parse_transaction_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Парсить текст транзакции в формате: "− 379 Перекрёсток" или "+1500 зарплата".
    
    Поддерживаемые форматы:
    - "− 379 Перекрёсток"
    - "-379 Перекрёсток"
    - "379 Перекрёсток" (по умолчанию расход)
    - "+1500 зарплата"
    - "1500+ зарплата"
    
    Returns:
        dict или None, если не удалось распарсить
        {
            "amount": 379.0,
            "type": "expense",  # или "income"
            "merchant": "Перекрёсток",
            "raw_text": "− 379 Перекрёсток"
        }
    """
    if not text or not text.strip():
        return None
    
    text = text.strip()
    
    # Паттерны для распознавания
    # Формат: [знак] [сумма] [описание/мерчант]
    patterns = [
        # "− 379 Перекрёсток" или "-379 Перекрёсток"
        r'^([−\-+])\s*([0-9]+(?:[.,][0-9]{1,2})?)\s+(.+)$',
        # "379 Перекрёсток" (без знака, по умолчанию расход)
        r'^([0-9]+(?:[.,][0-9]{1,2})?)\s+(.+)$',
        # "+1500 зарплата" или "1500+ зарплата"
        r'^([0-9]+(?:[.,][0-9]{1,2})?)\s*([+])\s*(.*)$',
        # "1500 + зарплата"
        r'^([0-9]+(?:[.,][0-9]{1,2})?)\s+([+])\s+(.+)$',
    ]
    
    for pattern in patterns:
        match = re.match(pattern, text, re.UNICODE)
        if match:
            groups = match.groups()
            
            # Определяем тип, сумму и описание в зависимости от паттерна
            if len(groups) == 3:
                # Паттерн с явным знаком в начале
                sign = groups[0]
                amount_str = groups[1]
                merchant = groups[2].strip()
                
                # Определяем тип транзакции
                transaction_type = "income" if sign == "+" else "expense"
            elif len(groups) == 2:
                # Паттерн без знака или со знаком после суммы
                if groups[1].isdigit() or '.' in groups[1] or ',' in groups[1]:
                    # Это "379 Перекрёсток" (без знака)
                    amount_str = groups[0]
                    merchant = groups[1].strip()
                    transaction_type = "expense"  # По умолчанию расход
                else:
                    # Это паттерн типа "1500+ зарплата"
                    amount_str = groups[0]
                    sign = groups[1] if len(groups) > 1 else ""
                    merchant = groups[2].strip() if len(groups) > 2 else ""
                    transaction_type = "income" if sign == "+" else "expense"
            else:
                continue
            
            # Парсим сумму
            try:
                amount = float(amount_str.replace(',', '.').replace(' ', ''))
            except ValueError:
                logger.warning(f"Не удалось распарсить сумму: {amount_str}")
                continue
            
            # Валидация
            if amount <= 0:
                logger.warning(f"Сумма должна быть положительной: {amount}")
                continue
            
            if not merchant:
                logger.warning(f"Не указан мерчант или описание")
                continue
            
            return {
                "amount": amount,
                "type": transaction_type,
                "merchant": merchant,
                "raw_text": text
            }
    
    logger.debug(f"Не удалось распарсить текст транзакции: {text}")
    return None


def normalize_merchant_name(merchant: str) -> str:
    """
    Нормализовать название мерчанта для поиска правил.
    
    Примеры:
    - "Перекрёсток" -> "перекрёсток"
    - "ПЕРЕКРЁСТОК!!!" -> "перекрёсток"
    - "  Пятёрочка  " -> "пятёрочка"
    """
    if not merchant:
        return ""
    
    # Убираем лишние пробелы и приводим к lowercase
    normalized = merchant.strip().lower()
    
    # Убираем знаки препинания в конце
    normalized = re.sub(r'[!?,.\s]+$', '', normalized)
    
    return normalized


def extract_merchant_from_description(description: str) -> Optional[str]:
    """
    Извлечь название мерчанта из описания транзакции.
    
    Примеры:
    - "Покупка в Перекрёсток" -> "Перекрёсток"
    - "Оплата СБП QR Пятёрочка" -> "Пятёрочка"
    - "Списание 379.00р Магнит" -> "Магнит"
    """
    if not description:
        return None
    
    # Паттерны для извлечения мерчанта
    patterns = [
        r'(?:в|В)\s+([А-ЯЁа-яё\w\s]+)',  # "в Перекрёсток"
        r'(?:QR|qr)\s+([А-ЯЁа-яё\w\s]+)',  # "QR Пятёрочка"
        r'(?:Списание|списание).*?([А-ЯЁа-яё\w]+)$',  # "Списание ... Магнит"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, description)
        if match:
            merchant = match.group(1).strip()
            if len(merchant) >= 3:  # Минимальная длина названия
                return merchant
    
    # Если не нашли по паттернам, берём последнее слово (если оно достаточно длинное)
    words = description.split()
    if words:
        last_word = words[-1].strip()
        # Убираем числа и спец символы
        last_word = re.sub(r'[0-9₽$€£.,-]', '', last_word)
        if len(last_word) >= 3:
            return last_word
    
    return None

