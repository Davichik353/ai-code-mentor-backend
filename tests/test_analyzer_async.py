import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from claude_analyzer import CodeAnalyzer

class AsyncAnalyzerTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_is_awaited_and_response_is_parsed(self):
        analyzer = CodeAnalyzer()
        generate = AsyncMock(return_value=SimpleNamespace(text='{"summary":"Reviewed","critical":[],"improvements":[],"learning":[],"good":[]}'))
        analyzer.client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
        result = await analyzer.analyze('print(42)', 'example.py', 'Python')
        self.assertEqual(result['summary'], 'Reviewed')
        generate.assert_awaited_once()
