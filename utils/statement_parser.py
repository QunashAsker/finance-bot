"""Парсер выписок из различных форматов."""
import base64
import io
import re
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger
import pandas as pd
from ai.claude_client import ClaudeClient


def parse_text_transactions(text: str, user_categories: List[Dict]) -> List[Dict[str, Any]]:
    """Парсить транзакции из текстового ответа Claude.
    
    Ожидаемый формат:
    Доход/Расход: Доход
    Сумма: 150000.00
    Описание: Входящий перевод СБП...
    Категория: Прочее
    
    Доход/Расход: Расход
    ...
    """
    transactions = []
    
    # Разбиваем текст на блоки транзакций
    # Ищем паттерн "Доход/Расход:" как начало транзакции
    transaction_pattern = r'Доход/Расход:\s*(Доход|Расход)\s*\n\s*Сумма:\s*([\d\s,\.]+)\s*\n\s*Описание:\s*(.*?)\s*\n\s*Категория:\s*(.+?)(?=\n\s*Доход/Расход:|$)'
    
    matches = re.finditer(transaction_pattern, text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    
    for match in matches:
        try:
            trans_type_text = match.group(1).strip()
            amount_str = match.group(2).strip()
            description = match.group(3).strip()
            category = match.group(4).strip()
            
            # Определяем тип транзакции
            if "доход" in trans_type_text.lower() or "income" in trans_type_text.lower():
                transaction_type = "income"
            else:
                transaction_type = "expense"
            
            # Парсим сумму (убираем пробелы и запятые, заменяем запятую на точку)
            amount_str = amount_str.replace(" ", "").replace(",", ".")
            try:
                amount = float(amount_str)
            except ValueError:
                logger.warning(f"Не удалось распарсить сумму: {amount_str}")
                continue
            
            # Убираем эмодзи из категории если есть
            category_clean = re.sub(r'[^\w\s-]', '', category).strip()
            
            # Пробуем найти дату в описании или используем текущую дату
            date = datetime.now().date()
            date_patterns = [
                r'(\d{2})\.(\d{2})\.(\d{4})',  # ДД.ММ.ГГГГ
                r'(\d{4})-(\d{2})-(\d{2})',    # ГГГГ-ММ-ДД
            ]
            
            for pattern in date_patterns:
                date_match = re.search(pattern, description)
                if date_match:
                    try:
                        if '.' in date_match.group(0):
                            # ДД.ММ.ГГГГ
                            day, month, year = date_match.groups()
                            date = datetime(int(year), int(month), int(day)).date()
                        else:
                            # ГГГГ-ММ-ДД
                            year, month, day = date_match.groups()
                            date = datetime(int(year), int(month), int(day)).date()
                        break
                    except ValueError:
                        continue
            
            transactions.append({
                "date": date,
                "amount": amount,
                "type": transaction_type,
                "description": description,
                "category_name": category_clean if category_clean else "Прочее"
            })
            
        except Exception as e:
            logger.warning(f"Ошибка при парсинге транзакции: {e}")
            continue
    
    # Если не нашли через паттерн, пробуем альтернативный метод
    if not transactions:
        # Пробуем найти транзакции через более гибкий паттерн
        lines = text.split('\n')
        current_trans = {}
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_trans:
                    # Сохраняем транзакцию если есть все необходимые поля
                    if all(k in current_trans for k in ['type', 'amount']):
                        transactions.append({
                            "date": current_trans.get("date", datetime.now().date()),
                            "amount": current_trans["amount"],
                            "type": current_trans["type"],
                            "description": current_trans.get("description", ""),
                            "category_name": current_trans.get("category", "Прочее")
                        })
                    current_trans = {}
                continue
            
            # Ищем поля транзакции
            if re.match(r'Доход/Расход:', line, re.IGNORECASE):
                trans_type = re.search(r'(Доход|Расход)', line, re.IGNORECASE)
                if trans_type:
                    current_trans["type"] = "income" if "доход" in trans_type.group(0).lower() else "expense"
            
            elif re.match(r'Сумма:', line, re.IGNORECASE):
                amount_match = re.search(r'([\d\s,\.]+)', line)
                if amount_match:
                    amount_str = amount_match.group(1).replace(" ", "").replace(",", ".")
                    try:
                        current_trans["amount"] = float(amount_str)
                    except ValueError:
                        pass
            
            elif re.match(r'Описание:', line, re.IGNORECASE):
                desc = line.split(':', 1)[1].strip() if ':' in line else line
                current_trans["description"] = desc
            
            elif re.match(r'Категория:', line, re.IGNORECASE):
                cat = line.split(':', 1)[1].strip() if ':' in line else line
                current_trans["category"] = re.sub(r'[^\w\s-]', '', cat).strip()
        
        # Сохраняем последнюю транзакцию если есть
        if current_trans and all(k in current_trans for k in ['type', 'amount']):
            transactions.append({
                "date": current_trans.get("date", datetime.now().date()),
                "amount": current_trans["amount"],
                "type": current_trans["type"],
                "description": current_trans.get("description", ""),
                "category_name": current_trans.get("category", "Прочее")
            })
    
    logger.info(f"Извлечено транзакций из текста: {len(transactions)}")
    return transactions


def parse_pdf_statement(pdf_bytes: bytes, user_categories: List[Dict]) -> List[Dict[str, Any]]:
    """Парсить банковскую выписку из PDF через Claude API."""
    try:
        # Конвертируем PDF в base64
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        
        # Получаем список категорий для промпта
        categories_str = ", ".join([f"{cat['icon']} {cat['name']}" for cat in user_categories])
        
        # Формируем промпт для Claude - просим текстовый список
        prompt = f"""Проанализируй банковскую выписку в PDF и выпиши списком все транзакции с указанием:

Доход/Расход
Сумма
Описание транзакции
Категория транзакции

Для каждой транзакции определи:
- Тип: "Доход" если это зачисление/доход, "Расход" если списание/расход
- Сумма: положительное число (без знака)
- Описание: полное описание операции из выписки
- Категория: наиболее подходящая категория из списка: {categories_str}

Формат вывода для каждой транзакции:
Доход/Расход: [Доход или Расход]
Сумма: [число]
Описание: [текст]
Категория: [название категории]

Если категория не подходит ни к одной из списка, используй "Прочее".
Выведи все транзакции из выписки по порядку."""
        
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
        
        # Извлекаем транзакции из текстового ответа
        if message.content and len(message.content) > 0:
            # Получаем текст из ответа
            first_content = message.content[0]
            if hasattr(first_content, 'text'):
                response_text = first_content.text
            elif isinstance(first_content, dict) and 'text' in first_content:
                response_text = first_content['text']
            else:
                response_text = str(first_content)
            
            logger.debug(f"Ответ Claude (первые 1000 символов): {response_text[:1000]}")
            
            # Парсим текстовый формат транзакций
            transactions = parse_text_transactions(response_text, categories_list)
            
            if not transactions:
                raise ValueError(f"Не удалось извлечь транзакции из ответа Claude. Ответ (первые 500 символов): {response_text[:500]}")
            
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

