#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Классификатор обращений и генератор черновиков ответов.
Решение кейса №01 тренировочного дня хакатона.

Роль: Backend & CLI Core Developer (Участник №2)
Особенности:
- Чистая стандартная библиотека Python 3 (zero dependencies, без pip install).
- Поддержка UTF-8 на всех платформах (включая Windows PowerShell / CMD).
- Graceful Fallback: при сбое LLM API или отсутствии ключа — автоматическое переключение на rules.
- Чистый JSON-вывод по флагу --json (предупреждения и логи уходят строго в stderr).
- Умный парсинг входных файлов (очистка нумерации '1)', '1.', '[1]', поддержка BOM).
"""

import os
import re
import sys
import json
import argparse
import urllib.request
import urllib.error
from pathlib import Path

# Обеспечение корректного вывода UTF-8 в консолях (Windows, Linux, macOS)
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# ПРАВИЛА (RULE-BASED КЛАССИФИКАЦИЯ И ШАБЛОНЫ ОТВЕТОВ)
# ---------------------------------------------------------------------------

RULES = [
    {
        "category": "жалоба",
        "patterns": [
            r"очеред[ьи]", r"холодн", r"пропал", r"не работа", r"сломал",
            r"ужасн", r"плох", r"грязн", r"жалоб", r"претензи", r"сбой", r"верните"
        ],
        "draft_template": (
            "Здравствуйте! Благодарим за сигнал и приносим извинения за неудобства. "
            "Информация зафиксирована и передана ответственной службе для оперативного устранения проблемы. "
            "Мы уведомим вас о результатах проверки."
        ),
        "custom_drafts": {
            "столов": (
                "Здравствуйте! Приносим извинения за доставленные неудобства. "
                "Ваша жалоба передана руководству службы питания и администратору столовой. "
                "Будет проведена проверка температурного режима на линии раздачи и организовано перераспределение очередей в пиковые часы."
            ),
            "wi-fi": (
                "Здравствуйте! Информация о сбое сети Wi-Fi в корпусе B зарегистрирована. "
                "Заявка передана инженерам технической поддержки (ИТ-отдел). "
                "Ведутся восстановительные работы, связь появится в ближайшее время."
            )
        }
    },
    {
        "category": "справка",
        "patterns": [
            r"справк", r"как получ", r"где", r"документ", r"расписани",
            r"часы работ", r"график", r"парковк", r"пропуск", r"контакт"
        ],
        "draft_template": (
            "Здравствуйте! По вашему запросу подготовлена справочная информация. "
            "Вы можете ознакомиться с подробностями на официальном портале или обратиться в справочную службу."
        ),
        "custom_drafts": {
            "месте уч": (
                "Здравствуйте! Справку об обучении вы можете заказать онлайн через личный кабинет студента в разделе «Услуги и справки» "
                "либо получить лично в учебной части корпуса А (кабинет 101, пн-пт с 9:00 до 18:00). Срок готовности — до 3 рабочих дней."
            ),
            "парковк": (
                "Здравствуйте! Гостевая парковка расположена справа от центрального въезда со стороны Северного проезда. "
                "Для заезда обратитесь на пост охраны (КПП №1) для оформления временного пропуска при предъявлении паспорта/ВУ."
            )
        }
    },
    {
        "category": "другое",
        "patterns": [
            r"записат", r"консультац", r"встреч", r"прием", r"хочу", r"предложен"
        ],
        "draft_template": (
            "Здравствуйте! Ваше обращение принято в обработку. Наш специалист свяжется с вами "
            "в течение рабочего дня для уточнения деталей."
        ),
        "custom_drafts": {
            "консультац": (
                "Здравствуйте! Вы можете записаться на консультацию через личный кабинет в модуле «Электронная запись» "
                "или напрямую у куратора курса. Уточните, пожалуйста, преподавателя или тематику интересующего вопроса."
            )
        }
    }
]


def classify_by_rules(text: str) -> tuple[str, str]:
    """Классификация текста обращения и подбор ответа на основе регулярных выражений."""
    # Попытка подключить внешний модуль rules_data, если он предоставлен Участником №1
    try:
        from rules_data import classify_text_by_rules  # type: ignore
        return classify_text_by_rules(text)
    except (ImportError, AttributeError):
        pass

    lower_text = text.lower()

    # Проверяем категории по шаблонам
    for rule in RULES:
        for pattern in rule["patterns"]:
            if re.search(pattern, lower_text):
                category = rule["category"]

                # Ищем наиболее релевантный контекстный ответ
                for sub_key, custom_reply in rule.get("custom_drafts", {}).items():
                    if sub_key in lower_text:
                        return category, custom_reply

                return category, rule["draft_template"]

    # Категория по умолчанию
    default_draft = (
        "Здравствуйте! Ваше обращение получено и передано дежурному координатору. "
        "Мы свяжемся с вами в ближайшее время."
    )
    return "другое", default_draft


# Алиас для совместимости с интерфейсом Участника №1
classify_text_by_rules = classify_by_rules


# ---------------------------------------------------------------------------
# LLM КЛАССИФИКАЦИЯ (ОПЦИОНАЛЬНО: OpenAI / Любой OpenAI-совместимый API)
# ---------------------------------------------------------------------------

def classify_by_llm(
    text: str,
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o-mini",
    timeout: int = 15,
) -> tuple[str, str]:
    """Классификация текста обращения и генерация черновика ответа через LLM API.
    
    При любой ошибке сети, превышении квоты или сбое API автоматически переключается
    на rule-based классификацию (Graceful Fallback).
    """
    if not api_key:
        print("[Предупреждение] Ключ API не передан. Выполняется fallback на rules.", file=sys.stderr)
        return classify_by_rules(text)

    prompt = f"""Ты — интеллектуальный ассистент службы поддержки.
Твоя задача — классифицировать обращение пользователя и сформировать вежливый черновик ответа на русском языке.

Правила классификации:
- Категория строго одна из трех: "справка", "жалоба", "другое".
- "справка" — запросы информации, справок, документов, локаций, расписания, парковки.
- "жалоба" — недовольство, претензии, поломки, сбои, качество сервиса/еды/связи.
- "другое" — запись на встречи, консультации, прочие запросы.

Обращение:
"{text}"

Ответь СТРОГО в формате валидного JSON:
{{
  "category": "справка" | "жалоба" | "другое",
  "draft": "Текст черновика ответа на русском языке"
}}
"""

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that outputs only valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }

    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"].strip()

            # Извлекаем JSON даже если LLM обернула его в markdown или добавила текст
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                parsed = json.loads(json_match.group(0))
            else:
                parsed = json.loads(content)

            category = str(parsed.get("category", "другое")).strip().lower()
            if category not in ["справка", "жалоба", "другое"]:
                category = "другое"

            draft = (
                parsed.get("draft")
                or parsed.get("draft_reply")
                or parsed.get("reply")
                or parsed.get("answer")
                or "Здравствуйте! Ваше обращение принято в обработку."
            )
            return category, str(draft).strip()
    except Exception as e:
        print(f"[Внимание] Ошибка при вызове LLM ({e}). Выполняется fallback на rules.", file=sys.stderr)
        return classify_by_rules(text)


# ---------------------------------------------------------------------------
# ПАРСИНГ ФАЙЛА И CLI
# ---------------------------------------------------------------------------

def load_messages(filepath: Path) -> list[str]:
    """Считывание строк обращений из файла с очисткой от ведущей нумерации."""
    if not filepath.exists():
        raise FileNotFoundError(f"Файл '{filepath}' не найден!")

    messages = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Убираем ведущую нумерацию вида "1) ", "1. ", "[1] ", "(1) ", "1 - ", "1: "
            cleaned = re.sub(r"^\s*(?:\[\d+\]|\(\d+\)|\d+[\)\.\:\-–—])\s*", "", line)
            cleaned = cleaned.strip()
            if cleaned:
                messages.append(cleaned)
    return messages


def main():
    parser = argparse.ArgumentParser(
        description="Классификатор обращений для тренировочного дня хакатона (Кейс №01)"
    )
    parser.add_argument(
        "-f", "--file",
        type=str,
        default="messages.txt",
        help="Путь к файлу с обращениями (по умолчанию: messages.txt)"
    )
    parser.add_argument(
        "--mode",
        choices=["rules", "llm"],
        default="rules",
        help="Режим классификации: rules (эвристики, оффлайн) или llm (через API)"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.environ.get("OPENAI_API_KEY"),
        help="API-ключ для LLM (или переменная окружения OPENAI_API_KEY)"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        help="Базовый URL для OpenAI-совместимого API (по умолчанию: https://api.openai.com/v1)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        help="Модель LLM (по умолчанию: gpt-4o-mini)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Вывод результатов в формате чистого JSON вместо форматированного текста"
    )

    args = parser.parse_args()

    # Разрешение пути: абсолютный, относительно текущей директории или относительно скрипта
    script_dir = Path(__file__).resolve().parent
    raw_path = Path(args.file)
    if raw_path.is_absolute():
        input_path = raw_path
    elif raw_path.exists():
        input_path = raw_path.resolve()
    elif (script_dir / raw_path).exists():
        input_path = (script_dir / raw_path).resolve()
    else:
        input_path = raw_path.resolve()

    try:
        messages = load_messages(input_path)
    except Exception as err:
        print(f"Ошибка загрузки сообщений: {err}", file=sys.stderr)
        sys.exit(1)

    if not messages:
        if args.json:
            print(json.dumps([], ensure_ascii=False))
        else:
            print("[Предупреждение] Файл обращений пуст.", file=sys.stderr)
        return

    results = []

    use_llm = (args.mode == "llm" and bool(args.api_key))
    if args.mode == "llm" and not args.api_key:
        print(
            "[Предупреждение] Флаг --mode llm задан, но API-ключ не передан. Запуск в режиме 'rules'.",
            file=sys.stderr
        )
        use_llm = False

    if not args.json:
        print("\n=======================================================")
        print(f" ОБРАБОТКА ОБРАЩЕНИЙ ({len(messages)} шт.) | РЕЖИМ: {'LLM' if use_llm else 'RULES'}")
        print("=======================================================\n")

    for idx, msg in enumerate(messages, 1):
        if use_llm:
            category, draft = classify_by_llm(
                msg,
                api_key=args.api_key,
                base_url=args.base_url,
                model=args.model
            )
        else:
            category, draft = classify_by_rules(msg)

        results.append({
            "id": idx,
            "message": msg,
            "category": category,
            "draft_reply": draft
        })

        if not args.json:
            print(f"[{idx}] Обращение: \"{msg}\"")
            print(f"    • Категория: {category.upper()}")
            print(f"    • Черновик ответа: {draft}\n" + "-" * 55)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
