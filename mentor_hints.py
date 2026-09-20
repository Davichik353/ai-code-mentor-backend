"""
Mentor Mode — генерирует прогрессивные подсказки (не готовые ответы) из фидбека.

Философия (из продуктового плана): не давать студенту готовое решение,
а направлять его к самостоятельному поиску через 3 нарастающие подсказки:
  Уровень 1: «Ты заметил...?»           (осознание)
  Уровень 2: «Что случится, если...?»   (исследование)
  Уровень 3: «Какой паттерн/концепт...?» (называние решения)

Каждая группа подсказок может нести `learning_resource` из RAG-движка,
чтобы UI мог показать «почему» со ссылкой на источник.
"""

from typing import List, Dict, Optional


class MentorMode:
    def __init__(self, rag_engine=None):
        self.rag = rag_engine

    def generate_hints(self, feedback: dict) -> List[Dict]:
        """
        Строит плоский упорядоченный список подсказок по критическим проблемам
        и улучшениям. Каждый dict содержит: level ('critical'|'hint'|'learn'),
        hint (текст шага 1), guide (текст шага 2) и опционально
        'learning_resource' если RAG нашёл что-то релевантное.

        Возвращает не более 4 групп подсказок для сохранения фокуса.
        """
        groups: List[Dict] = []

        for item in (feedback.get("critical") or [])[:2]:
            groups.append(self._build_group(item, level="critical",
                                             title_field="issue",
                                             detail_field="explanation"))

        for item in (feedback.get("improvements") or [])[:2]:
            groups.append(self._build_group(item, level="hint",
                                             title_field="issue",
                                             detail_field="explanation"))

        if not groups and feedback.get("learning"):
            item = feedback["learning"][0]
            groups.append(self._build_group(item, level="learn",
                                             title_field="topic",
                                             detail_field="explanation"))

        # Разворачиваем каждую группу из 3 шагов в отдельные записи,
        # чтобы кнопки «Назад»/«Вперёд» в Mentor Mode шли по одной подсказке.
        flat: List[Dict] = []
        for g in groups[:4]:
            for step_text in g["progression"]:
                flat.append({
                    "level": g["level"],
                    "hint": step_text,
                    "guide": g.get("learning_resource", {}).get("summary", ""),
                })

        return flat if flat else self._fallback_hint()

    def _build_group(self, item: dict, level: str, title_field: str, detail_field: str) -> Dict:
        title = item.get(title_field, "эту часть кода")
        detail = item.get(detail_field, "")

        # Переводим технические заголовки проблем на русский
        ru_title = self._translate_issue(title)

        progression = [
            f"💡 Ты заметил: {ru_title}?".encode('utf-8').decode('utf-8'),
            f"🤔 Что произойдёт, если передать сюда неожиданные данные или кто-то попытается это использовать?".encode('utf-8').decode('utf-8'),
            f"📚 Подумай об основной концепции — {self._name_pattern(title, detail)}".encode('utf-8').decode('utf-8'),
        ]

        resource = None
        if self.rag:
            hits = self.rag.search(f"{title} {detail}", top_k=1)
            if hits:
                resource = {
                    "topic": hits[0]["topic"],
                    "source": hits[0]["source"],
                    "summary": hits[0]["text"][:160],
                }

        return {
            "level": level,
            "title": ru_title,
            "progression": progression,
            "learning_resource": resource or {},
        }

    @staticmethod
    def _translate_issue(title: str) -> str:
        """Переводит типовые заголовки проблем с английского на русский."""
        translations = {
            "sql injection":             "SQL-инъекция",
            "sql":                       "SQL-инъекция",
            "injection":                 "инъекция данных",
            "resource leak":             "утечка ресурсов",
            "missing type hint":         "отсутствуют аннотации типов",
            "type hint":                 "отсутствуют аннотации типов",
            "missing docstring":         "отсутствует документация (docstring)",
            "docstring":                 "отсутствует документация (docstring)",
            "exception handling":        "обработка исключений",
            "missing exception":         "отсутствует обработка исключений",
            "lack of exception":         "отсутствует обработка исключений",
            "race condition":            "состояние гонки (race condition)",
            "toctou":                    "состояние гонки (TOCTOU)",
            "syntax error":              "синтаксическая ошибка",
            "nameerror":                 "обращение к неопределённой переменной",
            "undefined variable":        "неопределённая переменная",
            "hardcoded":                 "захардкоженные данные",
            "password":                  "небезопасное хранение пароля",
            "eafp":                      "принцип EAFP не соблюдён",
            "context manager":           "отсутствует менеджер контекста",
            "missing connection":        "соединение не закрывается явно",
            "connection context":        "соединение не закрывается явно",
            "loop":                      "неэффективный цикл",
            "list comprehension":        "не использован list comprehension",
            "performance":               "проблема производительности",
            "readability":               "недостаточная читаемость",
            "naming":                    "именование переменных",
            "global variable":           "использование глобальных переменных",
        }
        lower = title.lower()
        for key, ru in translations.items():
            if key in lower:
                return ru
        # Если перевод не найден — возвращаем оригинал без изменений
        return title

    @staticmethod
    def _name_pattern(title: str, detail: str) -> str:
        """Определяет ключевой концепт для шага 3 подсказки."""
        combined = f"{title} {detail}".lower()
        patterns = {
            "sql":          "параметризованные запросы / prepared statements",
            "inject":       "санитизация пользовательского ввода",
            "loop":         "итерация напрямую по коллекции (for item in list)",
            "range(len":    "паттерн «for item in list»",
            "type hint":    "статическая типизация с аннотациями типов",
            "docstring":    "документирование функций через docstring",
            "except":       "обработка конкретных исключений",
            "password":     "управление секретами / переменные окружения",
            "hardcode":     "переменные окружения для конфигурации",
            "context":      "менеджер контекста (with statement)",
            "resource":     "менеджер контекста (with statement)",
            "toctou":       "атомарные операции и EAFP-подход",
            "race":         "атомарные операции и EAFP-подход",
            "eafp":         "принцип EAFP вместо LBYL",
            "global":       "избегание глобального состояния",
            "comprehension":"list / dict comprehension",
        }
        for key, name in patterns.items():
            if key in combined:
                return name
        return "более питонический и надёжный подход"

    @staticmethod
    def _fallback_hint() -> List[Dict]:
        return [{
            "level": "hint",
            "hint": "✅ Серьёзных проблем не найдено — отличная работа! Загрузи другой файл, чтобы продолжить практику.",
            "guide": "",
        }]
