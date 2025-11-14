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
        
        # Извлекаем JSON из ответа
        if message.content and len(message.content) > 0:
            response_text = message.content[0].text
            
            # Находим JSON массив в ответе
            json_start = response_text.find("[")
            json_end = response_text.rfind("]") + 1
            
            if json_start != -1 and json_end > json_start:
                import json
                json_str = response_text[json_start:json_end]
                transactions = json.loads(json_str)
                
                # Валидируем и нормализуем транзакции
                normalized_transactions = []
                for trans in transactions:
                    try:
                        # Парсим дату
                        if isinstance(trans.get("date"), str):
                            parsed_date = datetime.strptime(trans["date"], "%Y-%m-%d").date()
                        else:
                            parsed_date = datetime.now().date()
                        
                        normalized_transactions.append({
                            "date": parsed_date,
                            "amount": float(trans.get("amount", 0)),
                            "type": trans.get("type", "expense"),
                            "description": trans.get("description", ""),
                            "category_name": trans.get("category", "Прочее")
                        })
                    except Exception as e:
                        logger.warning(f"Ошибка при нормализации транзакции: {e}")
                        continue
                
                return normalized_transactions
            else:
                raise ValueError("Не удалось найти JSON массив в ответе Claude")
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

