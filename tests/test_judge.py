import base64
import unittest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from judge import run_cases, configured

class JudgeTests(unittest.TestCase):
    def test_disabled_fails_closed(self):
        with patch.dict('os.environ',{'JUDGE0_ENABLED':'false'}):
            self.assertFalse(configured())
            with self.assertRaises(HTTPException): run_cases('print(1)','Python',[])

    def test_limits_network_and_results(self):
        fake=MagicMock();fake.__enter__.return_value=fake
        fake.post.return_value.json.return_value=[{'token':'token'}]
        fake.get.return_value.json.return_value={'submissions':[{'status':{'id':3},'stdout':base64.b64encode(b'5\n').decode()}]}
        with patch.dict('os.environ',{'JUDGE0_URL':'https://judge.example.test','JUDGE0_ENABLED':'true'}),patch('judge.requests.Session',return_value=fake):
            result=run_cases('console.log(Number(prompt())+Number(prompt()))','JavaScript',[{'stdin':'2\n3','expected_stdout':'5'}])
        self.assertTrue(result[0]['passed'])
        sent=fake.post.call_args.kwargs['json']['submissions'][0]
        self.assertFalse(sent['enable_network']);self.assertEqual(sent['cpu_time_limit'],2)
        self.assertIn('globalThis.prompt',base64.b64decode(sent['source_code']).decode())

    def test_provider_failure_is_not_a_grade(self):
        fake=MagicMock();fake.__enter__.return_value=fake
        fake.post.return_value.json.return_value=[{'token':'token'}]
        fake.get.return_value.json.return_value={'submissions':[{'status':{'id':13,'description':'Internal error'}}]}
        with patch.dict('os.environ',{'JUDGE0_URL':'https://judge.example.test','JUDGE0_ENABLED':'true'}),patch('judge.requests.Session',return_value=fake):
            with self.assertRaises(HTTPException) as error: run_cases('print(1)','Python',[{'stdin':'','expected_stdout':'1'}])
        self.assertEqual(error.exception.status_code,503)
