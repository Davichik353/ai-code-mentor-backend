import json
from unittest.mock import patch
from test_learning import LearningWorkflowTests
from learning import Learning
from fastapi import FastAPI
from fastapi.testclient import TestClient
from reliability import ErrorMonitoring

class ReliabilityTests(LearningWorkflowTests):
    def test_support_privacy_retries_staff_and_deletion(self):
        payload={'category':'code','message':'My editor does not save the input code.','request_key':'test-request-key-123'}
        response=self.client.post('/support/tickets',json=payload,headers=self.student)
        self.assertEqual(response.status_code,201);ticket=response.json()['id']
        self.assertEqual(self.client.post('/support/tickets',json=payload,headers=self.student).json()['id'],ticket)
        self.assertEqual(self.client.get('/support/tickets',headers=self.student).json()['tickets'][0]['id'],ticket)
        self.assertEqual(self.client.get('/support/tickets',headers=self.outsider).json()['tickets'],[])
        reply={'reply':'Please reload the editor and restore your saved draft.','status':'resolved'}
        self.assertEqual(self.client.post('/support/tickets/'+ticket+'/reply',json=reply,headers=self.student).status_code,404)
        with patch.dict('os.environ',{'SUPPORT_ADMIN_EMAILS':'teacher@example.com'}):
            # Verified email is required even if a deployment explicitly allows the address.
            with Learning(self.db.db_path).connect() as c:
                c.execute("UPDATE users SET email_verified=1 WHERE email='teacher@example.com'")
            self.assertTrue(self.client.get('/support/tickets',headers=self.teacher).json()['is_staff'])
            self.assertEqual(self.client.post('/support/tickets/'+ticket+'/reply',json=reply,headers=self.teacher).status_code,200)
        self.assertEqual(self.client.get('/support/tickets',headers=self.student).json()['tickets'][0]['reply'],reply['reply'])
        self.assertEqual(self.client.delete('/auth/account',headers=self.student).status_code,200)
        with Learning(self.db.db_path).connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM support_tickets').fetchone()[0],0)

    def test_error_logs_do_not_contain_user_data(self):
        app=FastAPI();app.add_middleware(ErrorMonitoring)
        @app.get('/example/{item_id}')
        def fail(item_id:str):raise ValueError('SECRET CODE PASSWORD')
        with patch('reliability.logger.error') as logger:
            response=TestClient(app).get('/example/private-id?token=private-token')
            self.assertEqual(response.status_code,500)
            self.assertEqual(response.json()['request_id'],response.headers['x-request-id'])
            record=logger.call_args.args[0]
            self.assertNotIn('SECRET',record);self.assertNotIn('private',record)
            self.assertEqual(json.loads(record)['route'],'/example/{item_id}')
