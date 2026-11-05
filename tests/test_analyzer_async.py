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

    async def test_requested_explanation_language_is_included_in_provider_prompt(self):
        for locale, instruction in [('ru', 'Russian'), ('uz', 'Uzbek (Latin alphabet)')]:
            analyzer = CodeAnalyzer()
            generate = AsyncMock(return_value=SimpleNamespace(text='{"summary":"Reviewed","critical":[],"improvements":[],"learning":[],"good":[]}'))
            analyzer.client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
            await analyzer.analyze('print(42)', 'example.py', 'Python', response_language=locale)
            self.assertIn('in ' + instruction, generate.await_args.kwargs['contents'])

    async def test_invalid_first_model_does_not_hide_valid_fallback(self):
        analyzer = CodeAnalyzer()
        valid = '{"summary":"Reviewed","critical":[],"improvements":[],"learning":[],"good":[]}'
        generate = AsyncMock(side_effect=[SimpleNamespace(text='incomplete response'), SimpleNamespace(text=valid)])
        analyzer.client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
        result = await analyzer.analyze('print(42)', 'example.py', 'Python')
        self.assertEqual(result['summary'], 'Reviewed')
        self.assertEqual(generate.await_count, 2)
        self.assertEqual(analyzer.model_name, analyzer.model_candidates[1])

    async def test_invalid_json_shape_is_rejected_without_fake_success(self):
        analyzer = CodeAnalyzer()
        generate = AsyncMock(return_value=SimpleNamespace(text='{"summary":"Not a complete review","critical":"invalid"}'))
        analyzer.client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
        result = await analyzer.analyze('print(42)', 'example.py', 'Python')
        self.assertFalse(result['analysis_available'])
        self.assertIsNone(analyzer.model_name)
