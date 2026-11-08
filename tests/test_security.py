"""Authentication, request limits, durable quotas and encrypted recovery regressions."""
import hashlib
import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from cryptography.fernet import Fernet, InvalidToken
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from fastapi.testclient import TestClient
from performance import RateLimiter
from request_security import RequestSecurity
from test_release import ReleaseTests
from scripts.backup_database import backup, restore
from scripts.cost_report import report


class SecurityTests(ReleaseTests):
    def test_password_recovery_single_use_expiry_and_session_revocation(self):
        import main
        smtp = dict(SMTP_HOST='smtp.example.com', SMTP_PORT='587', SMTP_USER='user', SMTP_PASSWORD='test', SMTP_FROM='test@example.com')
        with patch.dict(os.environ, smtp), patch.object(main, 'send_password_reset_email') as send:
            absent = self.client.post('/auth/forgot-password', json={'email':'missing@example.com'})
            present = self.client.post('/auth/forgot-password', json={'email':'alice@example.com'})
            self.assertEqual(absent.status_code, 200)
            self.assertEqual(absent.json(), present.json())
            token = send.call_args.args[1]
        with sqlite3.connect(self.db.db_path) as c:
            stored = c.execute('SELECT reset_token_hash FROM users WHERE email=?',('alice@example.com',)).fetchone()[0]
        self.assertEqual(stored, hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token, present.text)
        payload = {'token':token,'password':'New-Secure-Password1!'}
        self.assertEqual(self.client.post('/auth/reset-password',json=payload).status_code,200)
        self.assertEqual(self.client.get('/auth/me', headers=self.a).status_code,401)
        self.assertEqual(self.client.post('/auth/reset-password',json=payload).status_code,400)
        main.auth_ip_limiter.clear()
        login = self.client.post('/auth/login',json={'email':'alice@example.com','password':payload['password']})
        self.assertEqual(login.status_code,200,login.text)
        self.assertEqual(self.client.get('/auth/me',headers={'Authorization':'Bearer '+login.json()['access_token']}).status_code,200)
        self.assertEqual(self.client.post('/auth/login',json={'email':'alice@example.com','password':'Release-test-Password1!'}).status_code,401)
        record=self.db.get_user_by_email('bob@example.com')
        self.db.issue_password_reset(record['id'], hashlib.sha256(token.encode()).hexdigest(), '2000-01-01T00:00:00')
        self.assertEqual(self.client.post('/auth/reset-password',json=payload).status_code,400)

    def test_public_launch_requires_smtp_and_verification(self):
        import main
        with patch.dict(os.environ, {'PUBLIC_LAUNCH':'true','SMTP_HOST':''}):
            with self.assertRaisesRegex(RuntimeError,'email delivery'):
                with TestClient(main.app):
                    pass

    def test_single_frontend_api_root_and_redirect(self):
        self.assertEqual(self.client.get('/').json()['ui'],'https://ai-code-mentor-frontend-iota.vercel.app')
        r=self.client.get('/app',follow_redirects=False)
        self.assertEqual(r.status_code,307)
        self.assertEqual(r.headers['location'],'https://ai-code-mentor-frontend-iota.vercel.app')

    def test_login_bruteforce_limit_is_by_normalized_account(self):
        import main
        main.auth_ip_limiter.clear()
        for _ in range(10):
            self.assertEqual(self.client.post('/auth/login',json={'email':' ALICE@example.com ','password':'wrong'}).status_code,401)
        self.assertEqual(self.client.post('/auth/login',json={'email':'alice@example.com','password':'wrong'}).status_code,429)

    def test_recovery_requires_mail_config_and_hides_delivery_failure(self):
        import main
        with patch.dict(os.environ, {'SMTP_HOST':''}):
            self.assertEqual(self.client.post('/auth/forgot-password',json={'email':'alice@example.com'}).status_code,503)
        smtp=dict(SMTP_HOST='host', SMTP_PORT='587', SMTP_USER='u', SMTP_PASSWORD='p', SMTP_FROM='f')
        with patch.dict(os.environ,smtp), patch.object(main,'send_password_reset_email',side_effect=RuntimeError('test')):
            self.assertEqual(self.client.post('/auth/forgot-password',json={'email':'alice@example.com'}).status_code,200)
        self.assertIsNone(self.db.get_user_by_email('alice@example.com')['reset_token_hash'])

    def test_quotas_persist_and_global_failure_rolls_back(self):
        from database import Database
        self.assertTrue(self.db.reserve_analysis_quota('a',2,3))
        self.assertTrue(Database(self.db.db_path).reserve_analysis_quota('a',2,3))
        self.assertFalse(self.db.reserve_analysis_quota('a',2,3))
        self.assertTrue(self.db.reserve_analysis_quota('b',2,3))
        self.assertFalse(self.db.reserve_analysis_quota('c',2,3))

    def test_backup_roundtrip_preserves_rows_and_rejects_tampering(self):
        from snapshot_migration import row_digests
        encrypted=Path(self.tmp.name)/'backup.fernet'; restored=Path(self.tmp.name)/'restored.sqlite3'
        key=Fernet.generate_key()
        self.assertGreater(backup(encrypted,key,self.db.db_path),4)
        self.assertNotIn(b'alice@example.com',encrypted.read_bytes())
        restore(encrypted,restored,key)
        with sqlite3.connect(self.db.db_path) as a, sqlite3.connect(restored) as b:
            names=[r[1] for r in a.execute('pragma table_info(users)')]
            self.assertEqual(row_digests(a,'users',names),row_digests(b,'users',names))
        with self.assertRaises(ValueError):restore(encrypted,restored,key)
        encrypted.write_bytes(encrypted.read_bytes()[:-5]+b'xxxxx')
        with self.assertRaises(InvalidToken):restore(encrypted,Path(self.tmp.name)/'bad.sqlite3',key)


class MiddlewareTests(unittest.TestCase):
    def test_migration_maintenance_blocks_api_but_preserves_health(self):
        async def endpoint(request): return JSONResponse({'ok':True})
        app=Starlette(routes=[Route('/health',endpoint), Route('/anything',endpoint,methods=['GET','POST'])])
        app.add_middleware(RequestSecurity)
        with TestClient(app) as c, patch.dict(os.environ, {'DATABASE_MAINTENANCE':'true'}):
            self.assertEqual(c.get('/health').status_code,200)
            self.assertEqual(c.get('/anything').status_code,503)
            self.assertEqual(c.post('/anything').status_code,503)
        with TestClient(app) as c, patch.dict(os.environ, {'DATABASE_MAINTENANCE':'false'}):
            self.assertEqual(c.post('/anything').status_code,200)

    def test_all_routes_limited_and_forwarded_header_cannot_bypass(self):
        async def endpoint(request):return JSONResponse({'ok':True})
        app=Starlette(routes=[Route('/anything',endpoint,methods=['GET','POST'])])
        app.add_middleware(RequestSecurity,general=RateLimiter(2,2))
        with TestClient(app) as c:
            self.assertEqual(c.get('/anything').status_code,200)
            self.assertEqual(c.get('/anything',headers={'X-Forwarded-For':'1.2.3.4'}).status_code,200)
            r=c.get('/anything',headers={'X-Forwarded-For':'5.6.7.8'})
            self.assertEqual(r.status_code,429)
            self.assertGreater(int(r.headers['Retry-After']),0)

    def test_oversized_stream_is_rejected(self):
        async def endpoint(request):return JSONResponse({'ok':True})
        app=Starlette(routes=[Route('/anything',endpoint,methods=['POST'])]);app.add_middleware(RequestSecurity)
        with TestClient(app) as c:
            self.assertEqual(c.post('/anything',content=(b'a'*40000 for _ in range(2))).status_code,413)

    def test_limiter_has_bounded_memory(self):
        limiter=RateLimiter(1,1,max_keys=2)
        self.assertTrue(limiter.is_allowed('a')[0]);self.assertTrue(limiter.is_allowed('b')[0])
        self.assertFalse(limiter.is_allowed('c')[0]);self.assertFalse(limiter.is_allowed('a')[0])

    def test_cost_unknown_usage_or_rates_never_become_zero(self):
        prices={'model':{'input_per_million_usd':1,'output_per_million_usd':2}}
        known=report([('model',1000000,500000,1)],prices,2,Decimal(12000),Decimal(8000),Decimal('.5'))
        self.assertEqual(Decimal(known['known_api_usd']),2)
        self.assertEqual(Decimal(known['cost_per_learner_uzs']),16000)
        for rows,rates in [([('model',None,None,1)],prices),([('model',1,1,1)],{})]:
            self.assertIsNone(report(rows,rates,2,Decimal(1),Decimal(0),Decimal('.5'))['cost_per_learner_uzs'])
