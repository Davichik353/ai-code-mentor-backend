"""Transactional email via Brevo HTTPS, with SMTP fallback when Brevo is absent."""
import os
import smtplib
from email.message import EmailMessage
import requests


def smtp_configured():
    return all(os.getenv(k, '').strip() for k in ('SMTP_HOST','SMTP_PORT','SMTP_USER','SMTP_PASSWORD','SMTP_FROM'))


def mail_configured():
    if os.getenv('BREVO_API_KEY', '').strip():
        return bool(os.getenv('MAIL_FROM', '').strip())
    return smtp_configured()


def send_mail(recipient, subject, body):
    if not mail_configured():
        raise RuntimeError('Email delivery is not configured')
    if os.getenv('BREVO_API_KEY', '').strip():
        try:
            response = requests.post('https://api.brevo.com/v3/smtp/email',
                headers={'api-key':os.environ['BREVO_API_KEY'], 'accept':'application/json'},
                json={'sender':{'name':'AI Code Mentor','email':os.environ['MAIL_FROM']},
                      'to':[{'email':recipient}], 'subject':subject, 'textContent':body},
                timeout=(5, 20), allow_redirects=False)
            try:
                if response.status_code != 201:
                    raise RuntimeError('Email provider rejected delivery')
            finally:
                response.close()
        except requests.RequestException:
            raise RuntimeError('Email provider unavailable') from None
        return
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = os.environ['SMTP_FROM']
    message['To'] = recipient
    message.set_content(body)
    with smtplib.SMTP(os.environ['SMTP_HOST'], int(os.environ['SMTP_PORT']), timeout=15) as server:
        server.starttls()
        server.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
        server.send_message(message)
