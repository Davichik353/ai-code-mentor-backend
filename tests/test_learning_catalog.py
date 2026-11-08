"""Validate teaching metadata and run every Python reference solution against its examples."""
from collections import Counter
import subprocess
import sys
import unittest

from learning_content import CATEGORIES, DIFFICULTIES, TEMPLATES


class LearningCatalogTests(unittest.TestCase):
    def test_bilingual_catalog_categories_and_legacy_ids(self):
        self.assertGreaterEqual(len(TEMPLATES), 36)
        self.assertTrue({'sum-py', 'sum-js', 'maximum-py', 'maximum-js', 'vowels-py', 'vowels-js'} <= TEMPLATES.keys())
        categories = {item['id']: item['title'] for item in CATEGORIES}
        difficulties = {item['id']: item['title'] for item in DIFFICULTIES}
        self.assertEqual(set(categories), {'basics', 'conditions', 'loops', 'strings', 'lists', 'logic'})
        self.assertEqual(set(difficulties), {'beginner', 'intermediate'})
        counts = Counter()
        languages = {}
        for key, item in TEMPLATES.items():
            with self.subTest(exercise=key):
                self.assertEqual(key, item['id'])
                self.assertIn(item['language'], ('Python', 'JavaScript'))
                self.assertIn(item['category'], categories)
                self.assertIn(item['difficulty'], difficulties)
                self.assertEqual(item['category_title'], categories[item['category']])
                self.assertEqual(item['difficulty_title'], difficulties[item['difficulty']])
                counts[item['category']] += 1
                languages.setdefault(key.rsplit('-', 1)[0], set()).add(item['language'])
                for field in ('title', 'prompt', 'change', 'category_title', 'difficulty_title'):
                    self.assertEqual(set(item[field]), {'ru', 'uz'})
                    self.assertTrue(all(isinstance(value, str) and value.strip() for value in item[field].values()))
                self.assertEqual(len(item['hints']), 3)
                for hint in item['hints'] + item['defense_questions']:
                    self.assertEqual(set(hint), {'ru', 'uz'})
                    self.assertTrue(all(value.strip() for value in hint.values()))
                self.assertTrue(item['starter_code'].strip())
                self.assertGreaterEqual(len(item['tests']), 3)
                self.assertLessEqual(len(item['tests']), 5)
                self.assertEqual(len({case['stdin'] for case in item['tests']}), len(item['tests']))
                for case in item['tests']:
                    self.assertEqual(set(case), {'stdin', 'expected_stdout'})
                    self.assertTrue(all(isinstance(value, str) for value in case.values()))
        self.assertTrue(all(count >= 6 for count in counts.values()))
        self.assertTrue(all(pair == {'Python', 'JavaScript'} for pair in languages.values()))

    def test_all_python_reference_solutions_match_public_cases(self):
        count = 0
        for item in TEMPLATES.values():
            if item['language'] != 'Python':
                continue
            for index, case in enumerate(item['tests']):
                with self.subTest(exercise=item['id'], case=index + 1):
                    result = subprocess.run(
                        [sys.executable, '-I', '-c', item['solution']],
                        input=case['stdin'] + '\n', text=True, capture_output=True, timeout=3,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), case['expected_stdout'])
                    count += 1
        self.assertGreaterEqual(count, 54)


if __name__ == '__main__':
    unittest.main()
