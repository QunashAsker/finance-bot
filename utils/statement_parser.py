"""Парсер выписок из различных форматов."""
import base64
import io
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger
import pandas as pd
from ai.claude_client import ClaudeClient


def parse_pdf_statement(pdf_bytes: bytes, user_categories: List[Dict]) -> List[Dict[str, Any]]:
    """Парсить банковскую выписку из PDF через Claude API."""
    try:
        # Конвертируем PDF в base64
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        
        # Получаем список категорий для промпта
        categories_str = ", ".join([f"{cat['icon']} {cat['name']}" for cat in user_categories])
        
        # Формируем промпт для Claude
        prompt = f"""Проанализируй банковскую выписку в PDF и извлеки все транзакции в формате JSON массива.

Для каждой транзакции определи:
- date: дата в формате YYYY-MM-DD
- amount: сумма (положительное число, без знака)
- type: "income" если это зачисление/доход, "expense" если списание/расход
- description: описание операции
- category: наиболее подходящая категория из списка: {categories_str}

Верни только JSON массив в следующем формате:
[
  {{
    "date": "2024-11-13",
    "amount": 1000.00,
    "type": "income",
    "description": "Зарплата",
    "category": "Зарплата"
  }},
  {{
    "date": "2024-11-13",
    "amount": 500.00,
    "type": "expense",
    "description": "Оплата в кафе",
    "category": "Кафе"
  }}
]

Если категория не подходит ни к одной из списка, используй "Прочее".
Отвечай только JSON массивом без дополнительного текста."""
        
        claude = ClaudeClient()
        
        # Отправляем PDF в Claude через document API
        # Согласно документации Claude API, для PDF используется формат document с base64
        try:
            request_params = {
                "model": claude.model,
                "max_tokens": 4096,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": pdf_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            }
            
            message = claude.client.messages.create(**request_params)
        except Exception as api_error:
            logger.error(f"Ошибка при запросе к Claude API: {api_error}")
            # Пробуем альтернативный формат или другую модель
            try:
                # Пробуем использовать другую модель через fallback
                logger.info("Пробую альтернативный метод...")
                # Используем текстовый промпт с просьбой вернуть JSON
                alternative_prompt = f"""{prompt}

ВАЖНО: Верни ТОЛЬКО валидный JSON массив без дополнительного текста, комментариев или объяснений. Начни ответ сразу с символа '[' и закончи символом ']'."""
                
                request_params = {
                    "model": claude.model,
                    "max_tokens": 4096,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "document",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "application/pdf",
                                        "data": pdf_base64
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": alternative_prompt
                                }
                            ]
                        }
                    ]
                }
                
                message = claude.client.messages.create(**request_params)
            except Exception as retry_error:
                logger.error(f"Ошибка при повторной попытке: {retry_error}")
                raise ValueError(f"Не удалось обработать PDF через Claude API: {api_error}")
        
        # Извлекаем JSON из ответа
        if message.content and len(message.content) > 0:
            # Получаем текст из ответа
            first_content = message.content[0]
            if hasattr(first_content, 'text'):
                response_text = first_content.text
            elif isinstance(first_content, dict) and 'text' in first_content:
                response_text = first_content['text']
            else:
                response_text = str(first_content)
            
            logger.debug(f"Ответ Claude (первые 500 символов): {response_text[:500]}")
            
            # Пробуем найти JSON массив в ответе
            import json
            import re
            
            # Сначала пробуем найти JSON массив через регулярное выражение
            json_pattern = r'\[[\s\S]*?\]'
            json_matches = re.findall(json_pattern, response_text)
            
            transactions = None
            
            # Пробуем каждый найденный JSON массив
            for json_str in json_matches:
                try:
                    transactions = json.loads(json_str)
                    if isinstance(transactions, list) and len(transactions) > 0:
                        break
                except json.JSONDecodeError:
                    continue
            
            # Если не нашли через regex, пробуем стандартный способ
            if not transactions:
                json_start = response_text.find("[")
                json_end = response_text.rfind("]") + 1
                
                if json_start != -1 and json_end > json_start:
                    try:
                        json_str = response_text[json_start:json_end]
                        transactions = json.loads(json_str)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Ошибка парсинга JSON: {e}")
                        logger.warning(f"Проблемный JSON: {json_str[:200]}")
            
            if not transactions or not isinstance(transactions, list):
                # Если все еще не получилось, пробуем извлечь транзакции из текста через Claude
                logger.warning("Не удалось извлечь JSON массив. Пробую альтернативный метод...")
                # Пробуем найти транзакции в тексте вручную
                raise ValueError(f"Не удалось найти JSON массив в ответе Claude. Ответ: {response_text[:500]}")
            
            # Валидируем и нормализуем транзакции
            normalized_transactions = []
            for trans in transactions:
                try:
                    # Парсим дату
                    if isinstance(trans.get("date"), str):
                        # Пробуем разные форматы даты
                        date_formats = ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"]
                        parsed_date = None
                        for fmt in date_formats:
                            try:
                                parsed_date = datetime.strptime(trans["date"], fmt).date()
                                break
                            except ValueError:
                                continue
                        if not parsed_date:
                            parsed_date = datetime.now().date()
                    else:
                        parsed_date = datetime.now().date()
                    
                    amount = float(trans.get("amount", 0))
                    if amount <= 0:
                        continue  # Пропускаем нулевые или отрицательные суммы
                    
                    normalized_transactions.append({
                        "date": parsed_date,
                        "amount": amount,
                        "type": trans.get("type", "expense"),
                        "description": trans.get("description", ""),
                        "category_name": trans.get("category", "Прочее")
                    })
                except Exception as e:
                    logger.warning(f"Ошибка при нормализации транзакции: {e}, данные: {trans}")
                    continue
            
            if not normalized_transactions:
                raise ValueError("Не удалось извлечь ни одной транзакции из ответа Claude")
            
            return normalized_transactions
        else:
            raise ValueError("Пустой ответ от Claude API")
            
    except Exception as e:
        logger.error(f"Ошибка при парсинге PDF выписки: {e}")
        raise


def parse_csv_statement(csv_bytes: bytes, encoding: str = "utf-8") -> List[Dict[str, Any]]:
    """Парсить банковскую выписку из CSV."""
    try:
        # Пробуем разные разделители
        for delimiter in [",", ";", "\t"]:
            try:
                df = pd.read_csv(io.BytesIO(csv_bytes), encoding=encoding, delimiter=delimiter)
                if len(df.columns) >= 2:  # Минимум 2 колонки (дата и сумма)
                    break
            except:
                continue
        else:
            raise ValueError("Не удалось определить формат CSV")
        
        transactions = []
        
        # Пытаемся найти колонки автоматически
        date_col = None
        amount_col = None
        desc_col = None
        
        for col in df.columns:
            col_lower = str(col).lower()
            if any(word in col_lower for word in ["дата", "date", "день"]):
                date_col = col
            elif any(word in col_lower for word in ["сумма", "amount", "сум"]):
                amount_col = col
            elif any(word in col_lower for word in ["описание", "description", "опис", "назначение"]):
                desc_col = col
        
        # Если не нашли автоматически, используем первые колонки
        if not date_col:
            date_col = df.columns[0]
        if not amount_col:
            amount_col = df.columns[1] if len(df.columns) > 1 else None
        if not desc_col and len(df.columns) > 2:
            desc_col = df.columns[2]
        
        for _, row in df.iterrows():
            try:
                # Парсим дату
                date_str = str(row[date_col])
                try:
                    parsed_date = pd.to_datetime(date_str).date()
                except:
                    parsed_date = datetime.now().date()
                
                # Парсим сумму
                amount_str = str(row[amount_col]) if amount_col else "0"
                amount = float(amount_str.replace(",", ".").replace(" ", ""))
                
                # Определяем тип по знаку суммы
                transaction_type = "income" if amount >= 0 else "expense"
                amount = abs(amount)
                
                # Описание
                description = str(row[desc_col]) if desc_col else ""
                
                if amount > 0:  # Пропускаем нулевые суммы
                    transactions.append({
                        "date": parsed_date,
                        "amount": amount,
                        "type": transaction_type,
                        "description": description,
                        "category_name": None  # Будет определена через Claude
                    })
            except Exception as e:
                logger.warning(f"Ошибка при парсинге строки CSV: {e}")
                continue
        
        return transactions
        
    except Exception as e:
        logger.error(f"Ошибка при парсинге CSV выписки: {e}")
        raise


def parse_excel_statement(excel_bytes: bytes) -> List[Dict[str, Any]]:
    """Парсить банковскую выписку из Excel."""
    try:
        df = pd.read_excel(io.BytesIO(excel_bytes), engine='openpyxl')
        
        transactions = []
        
        # Аналогично CSV - находим колонки
        date_col = None
        amount_col = None
        desc_col = None
        
        for col in df.columns:
            col_lower = str(col).lower()
            if any(word in col_lower for word in ["дата", "date", "день"]):
                date_col = col
            elif any(word in col_lower for word in ["сумма", "amount", "сум"]):
                amount_col = col
            elif any(word in col_lower for word in ["описание", "description", "опис", "назначение"]):
                desc_col = col
        
        if not date_col:
            date_col = df.columns[0]
        if not amount_col:
            amount_col = df.columns[1] if len(df.columns) > 1 else None
        if not desc_col and len(df.columns) > 2:
            desc_col = df.columns[2]
        
        for _, row in df.iterrows():
            try:
                date_str = str(row[date_col])
                try:
                    parsed_date = pd.to_datetime(date_str).date()
                except:
                    parsed_date = datetime.now().date()
                
                amount_str = str(row[amount_col]) if amount_col else "0"
                amount = float(amount_str.replace(",", ".").replace(" ", ""))
                
                transaction_type = "income" if amount >= 0 else "expense"
                amount = abs(amount)
                
                description = str(row[desc_col]) if desc_col else ""
                
                if amount > 0:
                    transactions.append({
                        "date": parsed_date,
                        "amount": amount,
                        "type": transaction_type,
                        "description": description,
                        "category_name": None
                    })
            except Exception as e:
                logger.warning(f"Ошибка при парсинге строки Excel: {e}")
                continue
        
        return transactions
        
    except Exception as e:
        logger.error(f"Ошибка при парсинге Excel выписки: {e}")
        raise


def categorize_transactions_batch(
    transactions: List[Dict[str, Any]],
    user_categories: List[Dict]
) -> List[Dict[str, Any]]:
    """Категоризировать транзакции через Claude API (пакетная обработка)."""
    if not transactions:
        return []
    
    try:
        categories_str = ", ".join([f"{cat['icon']} {cat['name']}" for cat in user_categories])
        
        # Формируем список транзакций для Claude
        transactions_text = "\n".join([
            f"- {trans['date']} | {trans['amount']:.2f} | {trans['type']} | {trans['description']}"
            for trans in transactions[:50]  # Ограничиваем до 50 за раз
        ])
        
        prompt = f"""Для каждой транзакции определи наиболее подходящую категорию из списка: {categories_str}

Транзакции:
{transactions_text}

Верни JSON массив с категориями в том же порядке:
[
  {{"category": "Название категории"}},
  {{"category": "Название категории"}},
  ...
]

Если категория не подходит, используй "Прочее".
Отвечай только JSON массивом."""
        
        claude = ClaudeClient()
        response = claude.get_completion(prompt, max_tokens=2048)
        
        # Извлекаем JSON
        import json
        json_start = response.find("[")
        json_end = response.rfind("]") + 1
        
        if json_start != -1 and json_end > json_start:
            categories_list = json.loads(response[json_start:json_end])
            
            # Присваиваем категории транзакциям
            for i, trans in enumerate(transactions[:len(categories_list)]):
                if i < len(categories_list):
                    trans["category_name"] = categories_list[i].get("category", "Прочее")
                else:
                    trans["category_name"] = "Прочее"
        
        return transactions
        
    except Exception as e:
        logger.error(f"Ошибка при категоризации транзакций: {e}")
        # Если ошибка, используем "Прочее" для всех
        for trans in transactions:
            if not trans.get("category_name"):
                trans["category_name"] = "Прочее"
        return transactions

