"""Explainable provenance signals, never a forensic AI authorship verdict."""
import io
import re
import tokenize

DISCLOSURE = re.compile(
    r'(?:generated|written|created|produced|assisted)\s+(?:by|with|using)\s+(?:an?\s+)?'
    r'(?:ai\b|chatgpt\b|gpt[-\s]?\d|github\s+copilot\b|claude\b|gemini\b)'
    r'|(?:ai[- ]generated|сгенерирован\w*\s+(?:ии|нейросет\w*|chatgpt))', re.I)
DISCLAIMER = ('По одному фрагменту нельзя надёжно определить автора. Это поиск явных '
              'пометок, а не обученный AI-детектор. Пометки могут быть ошибочными или скопированными; '
              'их отсутствие не доказывает, что код написан человеком. Не используйте результат как доказательство нарушения.')


def inspect_authorship(code: str, filename: str = 'code.py', language: str = '') -> dict:
    python = filename.lower().endswith('.py') or language.lower() == 'python'
    signals = []
    if python:
        try:
            comments = [(t.start[0], t.string) for t in tokenize.generate_tokens(io.StringIO(code).readline)
                        if t.type == tokenize.COMMENT]
        except (tokenize.TokenError, IndentationError, SyntaxError):
            comments = []
    else:
        # Other languages need a language-specific parser before making claims about comments.
        comments = []
    for line, comment in comments:
        if DISCLOSURE.search(comment) and not re.search(r'\b(?:not|never)\b|не\s+сгенерирован', comment, re.I):
            signals.append({'line': line, 'kind': 'declared_ai_use', 'excerpt': comment[:240],
                            'explanation': 'В комментарии явно упомянуто создание кода с помощью AI. Это заявление в тексте, а не подтверждение авторства.'})
    return {
        'status': 'ai_use_declared' if signals else 'inconclusive',
        'label': 'В комментариях заявлено использование AI' if signals else 'Авторство не определено',
        'method': 'python_comment_disclosures_v1',
        'supported': python,
        'signals': signals,
        'limitations': DISCLAIMER,
        'next_step': 'Попросите автора объяснить решение и изменить его на практике; обсудите, какие инструменты использовались.',
    }
