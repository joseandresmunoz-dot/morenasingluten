import base64
import json
import os
import smtplib
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


def _platform_db_url():
    relationships = os.environ.get('PLATFORM_RELATIONSHIPS')
    if not relationships:
        return None
    try:
        data = json.loads(base64.b64decode(relationships).decode())
    except Exception:
        return None
    pg = data.get('database', [{}])[0]
    dbname = pg.get('path', 'main')
    return (
        f"postgresql://{pg['username']}:{pg['password']}"
        f"@{pg['host']}:{pg['port']}/{dbname}"
    )


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-cambiar-en-produccion')
    SQLALCHEMY_DATABASE_URI = _platform_db_url() or os.environ.get('DATABASE_URL', 'postgresql://usuario:password@localhost:5432/morena_sin_gluten')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    WTF_CSRF_TIME_LIMIT = int(os.environ.get('WTF_CSRF_TIME_LIMIT', '3600'))

    # Google OAuth
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')

    # WhatsApp
    WHATSAPP_NUMBER = os.environ.get('WHATSAPP_NUMBER', '5492966355530')

    # Mercado Pago
    MERCADOPAGO_ALIAS = os.environ.get('MERCADOPAGO_ALIAS', 'lacocinaceliaco')
    MERCADOPAGO_TITULAR = os.environ.get('MERCADOPAGO_TITULAR', 'Ana Carolina Iannovelli')

    # Verificación de email
    EMAIL_VERIFY_SALT = os.environ.get('EMAIL_VERIFY_SALT', 'email-verify-salt')
    EMAIL_VERIFY_MAX_AGE = int(os.environ.get('EMAIL_VERIFY_MAX_AGE', '86400'))
    MAIL_FROM = os.environ.get('MAIL_FROM', 'no-reply@morenasingluten.com')
    MAIL_SERVER = os.environ.get('MAIL_SERVER', '')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', '587'))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')

    @classmethod
    def has_mail_config(cls):
        return bool(cls.MAIL_SERVER and cls.MAIL_USERNAME and cls.MAIL_PASSWORD)

    @classmethod
    def send_email(cls, to_email, subject, body):
        if not cls.has_mail_config():
            raise RuntimeError('Falta configuración SMTP para enviar emails.')

        message = (
            f"From: {cls.MAIL_FROM}\r\n"
            f"To: {to_email}\r\n"
            f"Subject: {subject}\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            f"{body}"
        )

        with smtplib.SMTP(cls.MAIL_SERVER, cls.MAIL_PORT) as server:
            if cls.MAIL_USE_TLS:
                server.starttls()
            server.login(cls.MAIL_USERNAME, cls.MAIL_PASSWORD)
            server.sendmail(cls.MAIL_FROM, [to_email], message.encode('utf-8'))
