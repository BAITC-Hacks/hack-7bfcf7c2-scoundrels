# -*- coding: utf-8 -*-
"""
Юнит-тесты правил классификации и генерации ответов.

Разработано: Участник №1 (Data & AI / Rules Engineer)
Ветка: feature/member-1-data-ai
"""

import unittest
from rules import classify_text_by_rules, Category


class TestRulesClassifier(unittest.TestCase):

    def test_required_five_messages(self):
        """Проверка 5 обязательных кейсов из условия хакатона."""
        cases = [
            ("Как получить справку о месте учёбы?", Category.REFERENCE.value),
            ("В столовой очередь, еда холодная.", Category.COMPLAINT.value),
            ("Хочу записаться на консультацию завтра.", Category.OTHER.value),
            ("Пропал Wi-Fi в корпусе B.", Category.COMPLAINT.value),
            ("Где парковка для гостей?", Category.REFERENCE.value),
        ]
        for message, expected_cat in cases:
            with self.subTest(msg=message):
                res = classify_text_by_rules(message)
                self.assertEqual(res.category, expected_cat, f"Ошибка классификации для: {message}")
                self.assertTrue(len(res.draft_reply) > 20, "Черновик ответа слишком короткий!")
                self.assertTrue("Здравствуйте" in res.draft_reply, "Черновик должен начинаться с вежливого приветствия")

    def test_extended_edge_cases(self):
        """Проверка устойчивости к опечаткам, регистру и вариациям формулировок."""
        edge_cases = [
            ("где деканат?", Category.REFERENCE.value),
            ("Вай-фай не работает уже 2 часа!", Category.COMPLAINT.value),
            ("еда в кафе совсем холодная", Category.COMPLAINT.value),
            ("подскажите расписание экзаменов", Category.REFERENCE.value),
            ("как записаться на повторный прием", Category.OTHER.value),
            ("ужасный сервис и грязь в коридоре", Category.COMPLAINT.value),
        ]
        for message, expected_cat in edge_cases:
            with self.subTest(msg=message):
                res = classify_text_by_rules(message)
                self.assertEqual(res.category, expected_cat)


if __name__ == "__main__":
    unittest.main()
