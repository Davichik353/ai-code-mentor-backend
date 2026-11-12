import os
import secrets
import tempfile
import unittest
from unittest.mock import patch, Mock
import requests
os.environ.setdefault('JWT_SECRET', secrets.token_urlsafe(48))
from fastapi.testclient import TestClient
import main
from database import Database
from mail_delivery import send_mail

BREVO = {'BREVO_API_KEY':'test-key','MAIL_FROM':'sender@example.com','REQUIRE_EMAIL_VERIFICATION':'true'}

class MailDeliveryTests(unittest.TestCase):
    def test_brevo_https_request_and_redacted_failure(self):
        response=Mock(status_code=201)
        with patch.dict(os.environ,BREVO), patch('mail_delivery.requests.post',return_value=response) as post:
            send_mail('recipient@example.com','Subject','Body')
            args, kwargs=post.call_args
            self.assertEqual(args[0],'https://api.brevo.com/v3/smtp/email')
            self.assertEqual(kwargs['json']['to'],[{'email':'recipient@example.com'}])
            self.assertFalse(kwargs['allow_redirects'])
            response.status_code=401
            with self.assertRaisesRegex(RuntimeError,'rejected'): send_mail('a@example.com','Subject','Body')
            post.side_effect=requests.Timeout('secret provider error')
            with self.assertRaisesRegex(RuntimeError,'^Email provider unavailable$'): send_mail('a@example.com','Subject','Body')

    def test_verification_required_and_bound_to_email(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,BREVO), patch.object(main,'db',Database(tmp+'/test.sqlite')), patch('main.send_verification_email') as send:
            for limiter in (main.registration_ip_limiter,main.registration_email_limiter,main.api_limiter,main.auth_ip_limiter,main.login_limiter,main.verification_limiter,main.resend_email_limiter,main.resend_ip_limiter): limiter.clear()
            with TestClient(main.app) as client:
                credentials={'email':'new@example.com','password':'Strong-Test-Password1!'}
                response=client.post('/auth/register',json=credentials)
                self.assertEqual(response.status_code,201,response.text)
                self.assertTrue(response.json()['verification_required'])
                self.assertFalse(response.json().get('access_token'))
                self.assertEqual(client.post('/auth/login',json=credentials).status_code,403)
                token=send.call_args.args[1]
                self.assertRegex(token, r"^[0-9]{8}$")
                self.assertEqual(client.post('/auth/verify-email',params={'email':'wrong@example.com','code':token}).status_code,400)
                self.assertEqual(main.db.get_user_by_email('new@example.com')['email_verified'],0)
                old_token=token
                with patch('main.secrets.randbelow',return_value=(int(token)+1)%100_000_000):
                    self.assertEqual(client.post('/auth/resend-verification',json=credentials).status_code,200)
                token=send.call_args.args[1]
                self.assertNotEqual(token,old_token)
                self.assertEqual(client.post('/auth/resend-verification',json=credentials).status_code,429)
                self.assertEqual(client.post('/auth/verify-email',params={'email':credentials['email'],'code':old_token}).status_code,400)
                self.assertEqual(client.post('/auth/verify-email',params={'email':credentials['email'],'code':token}).status_code,200)
                self.assertEqual(client.post('/auth/verify-email',params={'email':credentials['email'],'code':token}).status_code,400)
                self.assertEqual(client.post('/auth/login',json=credentials).status_code,200)
                send.side_effect=RuntimeError('Provider unavailable')
                response=client.post('/auth/register',json={**credentials,'email':'failure@example.com'})
                self.assertEqual(response.status_code,503)
                self.assertIsNone(main.db.get_user_by_email('failure@example.com'))
