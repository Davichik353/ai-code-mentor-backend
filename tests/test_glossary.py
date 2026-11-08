"""Glossary metadata and real execution of every curated Python/JS example."""
import json
import shutil
import subprocess
import sys
import unittest

from learning_glossary import CATEGORIES, GLOSSARY


class GlossaryTests(unittest.TestCase):
    def test_terms_are_unique_and_cover_requested_basics(self):
        self.assertGreaterEqual(len(GLOSSARY), 40)
        terms = [item['term'] for item in GLOSSARY]
        self.assertEqual(len(terms), len(set(terms)))
        expected = {'variable', 'loop', 'edge case', 'test', 'type', 'input', 'print',
                    'int', 'float', 'str', 'bool', 'if', 'else', 'elif', 'for', 'while',
                    'range', 'break', 'continue', 'list', 'index', 'len', 'append',
                    'dict', 'set', 'function', 'parameter', 'return', 'comparison',
                    'logical operators', 'modulo', 'integer division', 'try/except',
                    'syntax error', 'runtime error', 'algorithm'}
        self.assertTrue(expected.issubset(terms))
        self.assertEqual({item['category'] for item in GLOSSARY}, set(CATEGORIES))

    def test_entries_explain_purpose_and_examples_in_both_locales(self):
        for item in GLOSSARY:
            with self.subTest(term=item['term']):
                self.assertIn(item['category'], CATEGORIES)
                for locale in ('ru', 'uz'):
                    self.assertGreater(len(item[locale]), 20)
                    for field in ('title', 'purpose', 'category_title'):
                        self.assertTrue(item[field][locale].strip())
                self.assertEqual(set(item['examples']), {'Python', 'JavaScript'})
                for example in item['examples'].values():
                    self.assertTrue(example['code'].strip())
                    self.assertTrue(example['expected_stdout'])
                    for locale in ('ru', 'uz'):
                        self.assertGreater(len(example['explanation'][locale]), 15)

    def test_every_python_example_runs_and_matches_its_result(self):
        for item in GLOSSARY:
            example = item['examples']['Python']
            with self.subTest(term=item['term']):
                result = subprocess.run([sys.executable, '-I', '-c', example['code']],
                                        input=example['stdin'], text=True, capture_output=True,
                                        timeout=3)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), example['expected_stdout'])

    @unittest.skipUnless(shutil.which('node'), 'Node.js is needed for curated JavaScript examples')
    def test_every_javascript_example_runs_and_matches_its_result(self):
        for item in GLOSSARY:
            example = item['examples']['JavaScript']
            # The product's browser executor offers prompt(); provide the same line-based
            # input contract here without evaluating any user-supplied code.
            prefix = ('const lines = ' + json.dumps(example['stdin'].splitlines()) +
                      '; globalThis.prompt = () => lines.shift() ?? "";\n')
            with self.subTest(term=item['term']):
                result = subprocess.run(['node', '-e', prefix + example['code']],
                                        text=True, capture_output=True, timeout=3)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), example['expected_stdout'])


if __name__ == '__main__':
    unittest.main()
