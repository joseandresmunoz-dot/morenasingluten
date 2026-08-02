import json
from flask import current_app
from pywebpush import webpush, WebPushException
from extensions import db
from models import PushSubscription, User


def send_push_to_admins(title, body, data=None):
    """Envía una notificación push a todos los admins suscriptos.

    Nunca lanza excepciones: si algo falla se registra y continúa.
    Devuelve la cantidad de suscripciones encontradas (para diagnóstico).
    """
    if not current_app.config.get('VAPID_PRIVATE_KEY'):
        return 0

    subs = PushSubscription.query.join(User).filter(User.is_admin == True).all()  # noqa: E712
    if not subs:
        return 0

    payload = json.dumps({'title': title, 'body': body, 'data': data or {}})
    sent = 0

    for sub in subs:
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {'p256dh': sub.p256dh, 'auth': sub.auth}
                },
                data=payload,
                vapid_private_key=current_app.config['VAPID_PRIVATE_KEY'],
                vapid_claims={'sub': current_app.config['VAPID_SUBJECT']}
            )
            sent += 1
        except WebPushException as e:
            if e.response and e.response.status_code in (404, 410):
                db.session.delete(sub)
                db.session.commit()
        except Exception:
            pass

    return sent
