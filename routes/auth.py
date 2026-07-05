from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from authlib.integrations.flask_client import OAuth
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from config import Config
from extensions import db
from models import User, AdminEmail

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

oauth = OAuth()


def _email_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def _build_verify_url(user):
    token = _email_serializer().dumps({'user_id': user.id}, salt=current_app.config['EMAIL_VERIFY_SALT'])
    return url_for('auth.verify_email', token=token, _external=True)


def _send_verify_email(user):
    verify_url = _build_verify_url(user)
    body = (
        f"Hola {user.nombre},\n\n"
        "Gracias por registrarte en Morena Sin Gluten.\n"
        "Para verificar tu email, hacé click en este enlace:\n\n"
        f"{verify_url}\n\n"
        "Si no creaste esta cuenta, podés ignorar este mensaje.\n"
    )
    Config.send_email(
        to_email=user.email,
        subject='Verificá tu email - Morena Sin Gluten',
        body=body
    )


def init_oauth(app):
    oauth.init_app(app)
    oauth.register(
        name='google',
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )


@auth_bp.route('/registro', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('shop.index'))

    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        email = request.form.get('email', '').strip().lower()
        whatsapp = request.form.get('whatsapp', '').strip()
        direccion = request.form.get('direccion', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        errors = []
        if not nombre:
            errors.append('El nombre es obligatorio.')
        if not email:
            errors.append('El email es obligatorio.')
        if not password or len(password) < 6:
            errors.append('La contraseña debe tener al menos 6 caracteres.')
        if password != password2:
            errors.append('Las contraseñas no coinciden.')
        if User.query.filter_by(email=email).first():
            errors.append('Ya existe una cuenta con ese email.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('auth/registro.html', nombre=nombre, email=email, whatsapp=whatsapp, direccion=direccion)

        user = User(
            email=email,
            username=email,
            nombre=nombre,
            whatsapp=whatsapp,
            direccion=direccion,
            email_verificado=False
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        try:
            _send_verify_email(user)
            flash('Cuenta creada. Te enviamos un link para verificar tu email.', 'success')
        except Exception:
            flash('Cuenta creada. No se pudo enviar el email de verificación, podés reenviarlo desde tu perfil.', 'warning')

        login_user(user)
        return redirect(url_for('shop.index'))

    return render_template('auth/registro.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('shop.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            next_page = request.form.get('next') or request.args.get('next')
            if user.email_verificado or user.google_id or user.is_admin:
                flash('¡Bienvenido/a de vuelta!', 'success')
            else:
                flash('Tu email todavía no está verificado. Revisá tu bandeja o reenviá el link desde tu perfil.', 'warning')
            return redirect(next_page or url_for('shop.index'))
        else:
            flash('Email o contraseña incorrectos.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/google')
def google_login():
    redirect_uri = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route('/google/callback')
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
        user_info = token.get('userinfo')
        if not user_info:
            user_info = oauth.google.userinfo()
    except Exception:
        flash('Error al iniciar sesión con Google. Intentá de nuevo.', 'danger')
        return redirect(url_for('auth.login'))

    google_id = user_info.get('sub')
    email = user_info.get('email', '').lower()
    nombre = user_info.get('name', '')
    avatar = user_info.get('picture', '')

    user = User.query.filter_by(google_id=google_id).first()

    if not user:
        user = User.query.filter_by(email=email).first()
        if user:
            user.google_id = google_id
            user.avatar_url = avatar
            user.email_verificado = True
        else:
            user = User(
                email=email,
                username=email,
                nombre=nombre,
                google_id=google_id,
                avatar_url=avatar,
                email_verificado=True
            )
            db.session.add(user)

    user.email_verificado = True

    # Promover a admin si el email está en la lista de admin emails
    if not user.is_admin:
        admin_email = AdminEmail.query.filter_by(email=user.email).first()
        if admin_email:
            user.is_admin = True

    db.session.commit()
    login_user(user)

    if not user.whatsapp:
        flash('Completá tu número de WhatsApp para finalizar tu registro.', 'info')
        return redirect(url_for('auth.complete_profile'))

    flash('¡Bienvenido/a de vuelta!', 'success')
    return redirect(url_for('shop.index'))


@auth_bp.route('/verificar-email')
def verify_email():
    token = request.args.get('token', '')
    if not token:
        flash('Link de verificación inválido.', 'danger')
        return redirect(url_for('auth.login'))

    try:
        data = _email_serializer().loads(
            token,
            salt=current_app.config['EMAIL_VERIFY_SALT'],
            max_age=current_app.config['EMAIL_VERIFY_MAX_AGE']
        )
    except SignatureExpired:
        flash('El link de verificación expiró. Solicitá uno nuevo.', 'warning')
        return redirect(url_for('auth.login'))
    except BadSignature:
        flash('Link de verificación inválido.', 'danger')
        return redirect(url_for('auth.login'))

    user = db.session.get(User, data.get('user_id'))
    if not user:
        flash('No encontramos la cuenta asociada al link.', 'danger')
        return redirect(url_for('auth.login'))

    if not user.email_verificado:
        user.email_verificado = True
        db.session.commit()

    login_user(user)
    flash('Email verificado correctamente.', 'success')
    return redirect(url_for('shop.index'))


@auth_bp.route('/reenviar-verificacion', methods=['POST'])
@login_required
def resend_verification_email():
    if current_user.is_admin:
        flash('La cuenta administradora no requiere verificación por email.', 'info')
        return redirect(url_for('auth.complete_profile'))

    if current_user.google_id:
        flash('Tu cuenta inició con Google y no requiere verificación por email.', 'info')
        return redirect(url_for('auth.complete_profile'))

    if current_user.email_verificado:
        flash('Tu email ya está verificado.', 'info')
        return redirect(url_for('auth.complete_profile'))

    try:
        _send_verify_email(current_user)
        flash('Te enviamos un nuevo link de verificación.', 'success')
    except Exception:
        flash('No se pudo enviar el email de verificación. Revisá la configuración SMTP.', 'danger')

    return redirect(url_for('auth.complete_profile'))


@auth_bp.route('/completar-perfil', methods=['GET', 'POST'])
@login_required
def complete_profile():
    if request.method == 'POST':
        whatsapp = request.form.get('whatsapp', '').strip()
        direccion = request.form.get('direccion', '').strip()
        if not whatsapp:
            flash('El número de WhatsApp es obligatorio.', 'danger')
        else:
            current_user.whatsapp = whatsapp
            current_user.direccion = direccion or None
            db.session.commit()
            flash('¡Perfil completado!', 'success')
            return redirect(url_for('shop.index'))

    return render_template('auth/completar_perfil.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Cerraste sesión correctamente.', 'info')
    return redirect(url_for('shop.index'))
