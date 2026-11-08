"""Profile settings are persistent, user-scoped and cannot change account privileges."""
import os
import secrets
import tempfile
import unittest
from unittest.mock import patch
os.environ.setdefault('JWT_SECRET', secrets.token_urlsafe(48))
os.environ['REQUIRE_EMAIL_VERIFICATION']='false'
from fastapi.testclient import TestClient
import main
from database import Database


class AccountSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Database(self.tmp.name+'/settings.sqlite')
        self.patcher=patch.object(main,'db',self.db);self.patcher.start()
        for limiter in [main.registration_ip_limiter,main.registration_email_limiter,main.auth_ip_limiter,main.api_limiter]:limiter.clear()
        self.client=TestClient(main.app);self.client.__enter__()
        self.users=[]
        for name in ['first','second']:
            response=self.client.post('/auth/register',json={'email':name+'@example.com','password':'Settings-Test-Password1!','display_name':name})
            self.assertEqual(response.status_code,201,response.text)
            self.users.append({'Authorization':'Bearer '+response.json()['access_token']})

    def tearDown(self):
        self.client.__exit__(None,None,None);self.patcher.stop();self.tmp.cleanup()

    def test_profile_name_persists_only_for_current_user_and_is_validated(self):
        self.assertEqual(self.client.patch('/auth/profile',json={'display_name':'No auth'}).status_code,401)
        response=self.client.patch('/auth/profile',headers=self.users[0],json={'display_name':'  Давлатбек  '})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['display_name'],'Давлатбек')
        self.assertEqual(self.client.get('/auth/me',headers=self.users[0]).json()['display_name'],'Давлатбек')
        self.assertEqual(self.client.get('/auth/me',headers=self.users[1]).json()['display_name'],'second')
        for body in [{'display_name':'x'*121},{'display_name':'Name','email':'other@example.com'},{'role':'teacher'}]:
            self.assertEqual(self.client.patch('/auth/profile',headers=self.users[0],json=body).status_code,422)
        self.assertEqual(self.client.patch('/auth/profile',headers=self.users[0],json={'display_name':'bad\nname'}).status_code,400)
        self.assertEqual(self.client.patch('/auth/profile',headers=self.users[0],json={'display_name':None}).json()['display_name'],None)
