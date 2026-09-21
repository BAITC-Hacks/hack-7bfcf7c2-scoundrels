#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматизированный QA тест-сьют для классификатора обращений (Кейс №01).
Разработано QA Lead (Участник №3) в рамках хакатона.

Запуск тестов:
    python test_classifier.py
или:
    python -m unittest test_classifier.py
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

# Импорт тестируемых функций
from classifier import classify_by_rules, load_messages


class TestClassifierCore(unittest.TestCase):
    """Модульные тесты базовой логики классификатора."""

    def test_control_case_1_certificate(self):
        msg = "Как получить справку о месте учёбы?"
        category, draft = classify_by_rules(msg)
        self.assertEqual(category, "справка")
        self.assertIn("Справку об обучении", draft)

    def test_control_case_2_canteen(self):
        msg = "В столовой очередь, еда холодная."
        category, draft = classify_by_rules(msg)
        self.assertEqual(category, "жалоба")
        self.assertTrue("питания" in draft.lower() or "столов" in draft.lower())

    def test_control_case_3_consultation(self):
        msg = "Хочу записаться на консультацию завтра."
        category, draft = classify_by_rules(msg)
        self.assertEqual(category, "другое")
        self.assertIn("консультацию", draft)

    def test_control_case_4_wifi(self):
        msg = "Пропал Wi-Fi в корпусе B."
        category, draft = classify_by_rules(msg)
        self.assertEqual(category, "жалоба")
        self.assertIn("Wi-Fi", draft)

    def test_control_case_5_parking(self):
        msg = "Где парковка для гостей?"
        category, draft = classify_by_rules(msg)
        self.assertEqual(category, "справка")
        self.assertTrue("парковк" in draft.lower() or "стоянк" in draft.lower())

    def test_unknown_text_fallback(self):
        msg = "Случайный текст без ключевых паттернов"
        category, draft = classify_by_rules(msg)
        self.assertEqual(category, "другое")
        self.assertTrue(len(draft) > 0)


class TestMessageParser(unittest.TestCase):
    """Тестирование парсинга сообщений и очистки нумерации."""

    def setUp(self):
        self.test_file = Path("test_sample_messages.tmp")

    def tearDown(self):
        if self.test_file.exists():
            self.test_file.unlink()

    def test_clean_prefixes_and_empty_lines(self):
        content = (
            "1) Первая строка\n"
            "2. Вторая строка\n"
            "[3] Третья строка\n"
            "(4) Четвертая строка\n"
            "5 - Пятая строка\n"
            "\n"
            "# Комментарий\n"
            "   Просто текст без номера   \n"
        )
        self.test_file.write_text(content, encoding="utf-8")
        parsed = load_messages(self.test_file)

        expected = [
            "Первая строка",
            "Вторая строка",
            "Третья строка",
            "Четвертая строка",
            "Пятая строка",
            "Просто текст без номера"
        ]
        self.assertEqual(parsed, expected)

    def test_nonexistent_file_raises_error(self):
        with self.assertRaises(FileNotFoundError):
            load_messages(Path("file_that_does_not_exist_xyz.txt"))


class TestCLIIntegration(unittest.TestCase):
    """Сквозные интеграционные тесты CLI."""

    def run_cli(self, args: list[str]) -> subprocess.CompletedProcess:
        cmd = [sys.executable, "classifier.py"] + args
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

    def test_cli_default_run(self):
        res = self.run_cli([])
        self.assertEqual(res.returncode, 0)
        self.assertIn("ОБРАБОТКА ОБРАЩЕНИЙ (5 шт.)", res.stdout)
        self.assertIn("Категория: СПРАВКА", res.stdout)
        self.assertIn("Категория: ЖАЛОБА", res.stdout)
        self.assertIn("Категория: ДРУГОЕ", res.stdout)

    def test_cli_json_mode(self):
        res = self.run_cli(["--json"])
        self.assertEqual(res.returncode, 0)
        # Проверяем чистоту stdout (валидный JSON без лишних логов)
        data = json.loads(res.stdout)
        self.assertEqual(len(data), 5)
        for item in data:
            self.assertIn("id", item)
            self.assertIn("message", item)
            self.assertIn("category", item)
            self.assertIn("draft_reply", item)

    def test_cli_llm_mode_fallback_without_key(self):
        res = self.run_cli(["--mode", "llm", "--json"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("Предупреждение", res.stderr)
        data = json.loads(res.stdout)
        self.assertEqual(len(data), 5)

    def test_cli_llm_mode_fallback_with_bad_key(self):
        res = self.run_cli(["--mode", "llm", "--api-key", "sk-invalid-fake-key", "--json"])
        self.assertEqual(res.returncode, 0)
        self.assertTrue(len(res.stderr) > 0)
        data = json.loads(res.stdout)
        self.assertEqual(len(data), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
