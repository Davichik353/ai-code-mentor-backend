from google import genai
from google.genai import types as genai_types
import json
import os
import re
from typing import Optional

from rag_engine import RAGEngine
from mentor_hints import MentorMode

class CodeAnalyzer:
    """
    Code analyzer powered by Google Gemini (free tier), using the
    current `google-genai` SDK (the older `google-generativeai`
    package is deprecated and can silently misroute model names).
    Same public interface as before (analyze / generate_hints / calculate_score),
    so main.py doesn't need to change at all.

    Day 2 addition: feedback items are enriched with RAG-sourced
    documentation citations, and generate_hints() now returns
    progressive Mentor Mode hints instead of flat one-liners.
    """
    def __init__(self):
        self.client = None
        # IMPORTANT: gemini-2.5-* models are NOT available to new API keys
        # (confirmed via live 404 errors: "no longer available to new users,
        # use models/gemini-3.6-flash instead" etc). Using the 3.x family
        # that Google's own error messages pointed us to, confirmed present
        # in ListModels output for this key.
        self.model_candidates = [
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-flash-latest",
            "gemini-pro-latest",
        ]
        self.model_name = None
        self._init_error = None

        self.rag = RAGEngine()
        self.mentor = MentorMode(rag_engine=self.rag)

    def _get_client(self):
        """Lazily create the Gemini client on first use, not at server startup."""
        if self.client is not None:
            return self.client

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            self._init_error = "GOOGLE_API_KEY is not set in .env"
            return None

        try:
            self.client = genai.Client(api_key=api_key)
            return self.client
        except Exception as e:
            self._init_error = f"Failed to initialize Gemini client: {e}"
            print(f"[claude_analyzer] {self._init_error}")
            return None

    async def analyze(self, code: str, filename: str = "code.py") -> dict:
        """
        Analyze code with 4-level feedback system.
        Returns: dict with critical, improvements, learning, and good feedback
        """
        client = self._get_client()
        if client is None:
            print(f"[claude_analyzer] Using fallback feedback: {self._init_error}")
            return self._create_default_feedback(code)

        system_prompt = """You are an expert Python code mentor for students. Analyze code and provide structured feedback.

Return ONLY valid JSON (no markdown, no code blocks, no backticks) with this exact structure:
{
  "summary": "1-2 sentence summary",
  "critical": [
    {"issue": "...", "explanation": "...", "why": "...", "fix": "..."}
  ],
  "improvements": [
    {"issue": "...", "explanation": "...", "why": "...", "suggestion": "..."}
  ],
  "learning": [
    {"topic": "...", "explanation": "...", "resource": "Python Documentation"}
  ],
  "good": [
    {"practice": "...", "explanation": "..."}
  ]
}

Guidelines:
- Critical: Security issues, runtime errors, logic bugs
- Improvements: Bad practices, performance, readability
- Learning: Concepts to study, patterns to learn
- Good: Praise correct implementations

Be encouraging but honest. Explain WHY, not just WHAT."""

        user_prompt = f"""Analyze this Python code ({filename}):

```python
{code}
```

Provide detailed, structured feedback. Remember: respond with ONLY the JSON object, nothing else."""

        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        response_text = None
        last_error = None

        # Try the already-selected model first, then fall back through the
        # remaining candidates if it 404s (Google renames/retires model IDs).
        names_to_try = [self.model_name] + [n for n in self.model_candidates if n != self.model_name] \
            if self.model_name else self.model_candidates

        for name in names_to_try:
            if not name:
                continue
            print(f"[claude_analyzer] Trying model: {name} ...")
            try:
                response = client.models.generate_content(
                    model=name,
                    contents=full_prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=2000,
                        http_options=genai_types.HttpOptions(timeout=20000),  # 20s, in ms
                    )
                )
                response_text = (response.text or "").strip()
                if response_text:
                    self.model_name = name
                    print(f"[claude_analyzer] ✅ {name} responded in time")
                    break
                else:
                    print(f"[claude_analyzer] {name} returned empty response, trying next...")
            except Exception as e:
                print(f"[claude_analyzer] ❌ {name} failed: {e}")
                last_error = e
                continue

        if not response_text:
            print(f"Error calling Gemini API: {last_error}")
            return self._create_default_feedback(code)

        try:
            # Gemini sometimes wraps JSON in ```json ... ``` even when told not to
            response_text = re.sub(r'^```json\s*', '', response_text)
            response_text = re.sub(r'^```\s*', '', response_text)
            response_text = re.sub(r'```\s*$', '', response_text)
            response_text = response_text.strip()

            try:
                feedback = json.loads(response_text)
            except json.JSONDecodeError:
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    feedback = json.loads(json_match.group())
                else:
                    print(f"[claude_analyzer] Could not parse Gemini response as JSON")
                    feedback = self._create_default_feedback(code)

            # Day 2: attach documentation sources/citations via RAG
            feedback = self.rag.add_context(feedback)
            return feedback

        except Exception as e:
            print(f"Error parsing Gemini response: {e}")
            return self._create_default_feedback(code)

    def generate_hints(self, feedback: dict) -> list:
        """
        Generate progressive mentor hints from feedback (Day 2: Mentor Mode).
        Hints guide students toward the answer instead of giving it away,
        and are enriched with RAG-sourced learning resources where available.
        """
        return self.mentor.generate_hints(feedback)

    def calculate_score(self, feedback: dict) -> int:
        """Calculate overall code quality score (0-100)"""
        score = 100

        critical_count = len(feedback.get("critical", []))
        score -= critical_count * 15

        improvements_count = len(feedback.get("improvements", []))
        score -= improvements_count * 5

        good_count = len(feedback.get("good", []))
        score += good_count * 3

        return max(0, min(100, score))

    def _create_hint_guide(self, explanation: str) -> str:
        """Create a guiding question from explanation"""
        hints_map = {
            "undefined": "Have you defined this variable?",
            "indent": "Check your indentation carefully",
            "type": "What type should this be?",
            "function": "Is this function defined?",
            "import": "Did you import this module?",
            "syntax": "Check the Python syntax rules",
            "logic": "Does this logic produce the expected result?",
            "performance": "Is this the most efficient way?",
        }

        for key, hint in hints_map.items():
            if key.lower() in explanation.lower():
                return hint

        return "Take another look at this part of your code"

    def _create_default_feedback(self, code: str) -> dict:
        """Fallback feedback if the API is unavailable (no key, quota, etc.)"""
        return {
            "summary": "Unable to analyze code at the moment (AI service unavailable)",
            "critical": [],
            "improvements": [
                {
                    "issue": "AI analysis unavailable",
                    "explanation": "Could not reach the analysis service",
                    "why": "Check GOOGLE_API_KEY in .env and your API quota",
                    "suggestion": "Verify your API key is set and valid"
                }
            ],
            "learning": [],
            "good": [
                {
                    "practice": "Code submission",
                    "explanation": "Successfully submitted code for analysis"
                }
            ]
        }