"""
Mentor Mode — generates progressive hints (not answers) from analysis feedback.

Philosophy (from the product plan): don't hand the student a fix,
guide them toward finding it themselves through 3 escalating hints:
  Level 1: "Have you noticed...?"      (awareness)
  Level 2: "What happens if...?"       (investigation)
  Level 3: "Which pattern/concept...?" (naming the solution)

Each hint group can carry a `learning_resource` pulled from the
RAG engine so the UI can show "why" with a citation.
"""

from typing import List, Dict, Optional


class MentorMode:
    def __init__(self, rag_engine=None):
        self.rag = rag_engine

    def generate_hints(self, feedback: dict) -> List[Dict]:
        """
        Build a flat, ordered list of hints across critical + improvement
        items. Each hint dict has: level ('critical'|'hint'|'learn'),
        hint (progression step 1 text), guide (step 2 text), and
        optionally a nested 'progression' list of 3 steps plus a
        'learning_resource' if RAG found something relevant.

        Returns at most 4 hint groups to keep Mentor Mode focused.
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

        # Flatten each group's 3-step progression into individual hint
        # entries so the frontend's Next/Previous stepping (Mentor Mode
        # widget) can walk through them one at a time, in order.
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
        title = item.get(title_field, "this part of your code")
        detail = item.get(detail_field, "")

        progression = [
            f"💡 Have you noticed: {title}?",
            f"🤔 What would happen if you ran this with unexpected input, or someone tried to exploit it?",
            f"📚 Think about the underlying concept here — {self._name_pattern(title, detail)}",
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
            "title": title,
            "progression": progression,
            "learning_resource": resource or {},
        }

    @staticmethod
    def _name_pattern(title: str, detail: str) -> str:
        """Best-effort guess at what concept to name in the final hint step."""
        combined = f"{title} {detail}".lower()
        patterns = {
            "sql": "parameterized queries / prepared statements",
            "inject": "input sanitization",
            "loop": "iterating directly over a collection instead of by index",
            "range(len": "the 'for item in list' pattern",
            "type hint": "static typing with type hints",
            "docstring": "documenting functions with docstrings",
            "except": "specific exception handling",
            "password": "secrets management / environment variables",
            "hardcode": "environment variables for configuration",
        }
        for key, name in patterns.items():
            if key in combined:
                return name
        return "a more Pythonic / robust approach"

    @staticmethod
    def _fallback_hint() -> List[Dict]:
        return [{
            "level": "hint",
            "hint": "✅ No major issues found — nice work! Try uploading another file to keep practicing.",
            "guide": "",
        }]