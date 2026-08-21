"""
RAG Engine — Retrieval Augmented Generation for AI Code Mentor.

Keeps things simple and dependency-light for a 4-day MVP:
no vector DB / embeddings service required. Uses a lightweight
keyword-overlap scorer (bag-of-words + simple TF weighting) over
a small curated JSON knowledge base of Python best practices.

This is intentionally NOT a toy — it's a real retrieval step that
Claude/Gemini responses get grounded against, with citations shown
in the UI. It can be swapped for real embeddings (e.g. Chroma +
sentence-transformers) later without changing the public interface
(search() / add_context()).
"""

import json
import os
import re
from collections import Counter
from typing import List, Dict, Optional


class RAGEngine:
    def __init__(self, docs_path: Optional[str] = None):
        self.docs_path = docs_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "python_docs_examples.json"
        )
        self.documents: List[Dict] = []
        self._load_docs()

    # ------------------------------------------------------------------
    # Loading & indexing
    # ------------------------------------------------------------------
    def _load_docs(self):
        """Flatten python_docs_examples.json into a flat list of searchable documents."""
        if not os.path.exists(self.docs_path):
            print(f"[rag_engine] WARNING: docs file not found at {self.docs_path}")
            self.documents = []
            return

        try:
            with open(self.docs_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            print(f"[rag_engine] Failed to load docs: {e}")
            self.documents = []
            return

        docs = []

        def add_doc(category: str, topic: str, text_parts: List[str], source: str):
            text = " ".join(p for p in text_parts if p)
            docs.append({
                "category": category,
                "topic": topic,
                "text": text,
                "tokens": self._tokenize(text + " " + topic),
                "source": source,
            })

        for item in raw.get("python_best_practices", []):
            add_doc(
                "best_practice", item.get("topic", ""),
                [item.get("description", ""), item.get("explanation", "")],
                "Python Best Practices",
            )

        for item in raw.get("performance_tips", []):
            add_doc(
                "performance", item.get("topic", ""),
                [item.get("issue", ""), item.get("why", "")],
                "Python Performance Guide",
            )

        for item in raw.get("security_issues", []):
            add_doc(
                "security", item.get("topic", ""),
                [item.get("danger", ""), item.get("why", "")],
                "Python Security Guidelines",
            )

        for item in raw.get("common_mistakes", []):
            add_doc(
                "mistake", item.get("mistake", ""),
                [item.get("problem", ""), item.get("solution", "")],
                "Common Python Mistakes",
            )

        for item in raw.get("readability_patterns", []):
            add_doc(
                "readability", item.get("pattern", ""),
                [item.get("why", "")],
                "Python Readability Patterns",
            )

        self.documents = docs
        self._build_idf()
        print(f"[rag_engine] Loaded {len(self.documents)} documentation entries")

    def _build_idf(self):
        """Compute inverse-document-frequency weights so rare, specific
        terms (e.g. 'injection', 'parameterized') score higher than
        common ones (e.g. 'using', 'string') that appear in many docs."""
        import math
        n_docs = len(self.documents) or 1
        df = Counter()
        for doc in self.documents:
            for token in doc["tokens"]:
                df[token] += 1
        self.idf = {
            token: math.log((n_docs + 1) / (count + 1)) + 1
            for token, count in df.items()
        }

    @staticmethod
    def _tokenize(text: str) -> Counter:
        words = re.findall(r"[a-zA-Z_][a-zA-Z_0-9]*", text.lower())
        # drop very short/common noise tokens
        stopwords = {"the", "a", "an", "is", "are", "of", "to", "in", "for", "and", "or", "this", "that"}
        return Counter(w for w in words if len(w) > 2 and w not in stopwords)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def search(self, query: str, top_k: int = 1, min_shared_tokens: int = 2) -> List[Dict]:
        """
        Return the top_k documents most relevant to `query`
        (an issue description, topic name, etc.) using TF-IDF weighted
        keyword overlap scoring.

        min_shared_tokens guards against false-positive citations: a
        single coincidental rare-word match (e.g. one shared word like
        "directly") isn't enough evidence of real topical relevance —
        we require at least 2 distinct overlapping terms by default.
        """
        if not self.documents or not query:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scored = []
        for doc in self.documents:
            shared = query_tokens & doc["tokens"]
            if len(shared) < min_shared_tokens:
                continue
            score = sum(count * self.idf.get(token, 1.0) for token, count in shared.items())
            scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]

    def add_context(self, feedback: dict) -> dict:
        """
        Enrich a feedback dict (as returned by CodeAnalyzer.analyze) with
        `source` / `doc_reference` fields pulled from the knowledge base,
        without mutating the structure the frontend already expects.
        """
        if not feedback:
            return feedback

        def enrich_list(items: List[Dict], text_fields: List[str]):
            for item in items or []:
                query = " ".join(str(item.get(f, "")) for f in text_fields)
                hits = self.search(query, top_k=1)
                if hits:
                    item["source"] = hits[0]["source"]
                    item["doc_topic"] = hits[0]["topic"]
            return items

        enrich_list(feedback.get("critical", []), ["issue", "explanation"])
        enrich_list(feedback.get("improvements", []), ["issue", "explanation"])
        enrich_list(feedback.get("learning", []), ["topic", "explanation"])
        # "good" items don't need a source citation — they're praise, not a claim

        return feedback


# Simple manual test when running this file directly:
#   python rag_engine.py
if __name__ == "__main__":
    rag = RAGEngine()
    test_queries = [
        "SQL injection query user id",
        "inefficient loop range len",
        "missing type hints function",
    ]
    for q in test_queries:
        print(f"\nQuery: {q}")
        for doc in rag.search(q, top_k=2):
            print(f"  -> [{doc['source']}] {doc['topic']}")