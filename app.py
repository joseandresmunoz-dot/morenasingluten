import os
from flask import Flask, send_from_directory, redirect, url_for, flash, request
from flask_wtf.csrf import CSRFError
from sqlalchemy import text
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from extensions import db, login_manager, migrate, csrf


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    # Inicializar extensiones
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # Google OAuth
    from routes.auth import init_oauth
    init_oauth(app)

    # Registrar blueprints
    from routes.auth import auth_bp
    from routes.shop import shop_bp
    from routes.admin import admin_bp
    from routes.wheel_api import wheel_api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(shop_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(wheel_api_bp, url_prefix='/api/wheel')

    # Servir uploads
    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    @app.route('/images/<filename>')
    def brand_image(filename):
        images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images')
        return send_from_directory(images_dir, filename)

    @app.route('/manifest.json')
    def manifest():
        return {
            "name": "Morena Sin Gluten",
            "short_name": "Morena SG",
            "description": "Sabores artesanales sin gluten",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#ffffff",
            "theme_color": "#f17528",
            "icons": [
                {
                    "src": "/images/logo_frente.png",
                    "sizes": "192x192",
                    "type": "image/png"
                },
                {
                    "src": "/images/logo_frente.png",
                    "sizes": "512x512",
                    "type": "image/png"
                }
            ]
        }

    @app.after_request
    def add_no_cache_headers(response):
        if request.endpoint == 'auth.login':
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if request.endpoint == 'auth.login' and request.method == 'POST':
            flash('Tu sesión expiró. Volvé a intentar iniciar sesión.', 'warning')
            return redirect(url_for('auth.login', next=request.form.get('next') or request.args.get('next')))
        return e.description, 400

    # Crear tablas si no existen
    with app.app_context():
        import models  # noqa: F401
        try:
            db.create_all()
        except Exception:
            pass
        inspector = db.inspect(db.engine)
        user_columns = [c['name'] for c in inspector.get_columns('users')]
        if 'email_verificado' not in user_columns:
            db.session.execute(text("ALTER TABLE users ADD COLUMN email_verificado BOOLEAN DEFAULT FALSE"))
            db.session.commit()
        if 'notas' not in user_columns:
            db.session.execute(text("ALTER TABLE users ADD COLUMN notas TEXT"))
            db.session.commit()
        product_columns = [c['name'] for c in inspector.get_columns('products')]
        if 'destacado' not in product_columns:
            db.session.execute(text("ALTER TABLE products ADD COLUMN destacado BOOLEAN DEFAULT FALSE"))
            db.session.commit()
        if 'direccion' not in user_columns:
            db.session.execute(text("ALTER TABLE users ADD COLUMN direccion VARCHAR(300)"))
            db.session.commit()
        user_coupon_columns = [c['name'] for c in inspector.get_columns('user_coupons')]
        if 'disponible' not in user_coupon_columns:
            db.session.execute(text("ALTER TABLE user_coupons ADD COLUMN disponible BOOLEAN DEFAULT FALSE"))
            db.session.commit()
            db.session.execute(text("UPDATE user_coupons SET disponible = TRUE"))
            db.session.commit()
        order_columns = [c['name'] for c in inspector.get_columns('orders')]
        if 'tipo_entrega' not in order_columns:
            db.session.execute(text("ALTER TABLE orders ADD COLUMN tipo_entrega VARCHAR(20) DEFAULT 'retiro'"))
            db.session.commit()
        if 'costo_envio' not in order_columns:
            db.session.execute(text("ALTER TABLE orders ADD COLUMN costo_envio NUMERIC(10, 2) DEFAULT 0"))
            db.session.commit()
        if 'direccion_entrega' not in order_columns:
            db.session.execute(text("ALTER TABLE orders ADD COLUMN direccion_entrega VARCHAR(300)"))
            db.session.commit()

        # Prize wheel migrations
        wheel_token_columns = [c['name'] for c in inspector.get_columns('prize_wheel_tokens')] if inspector.has_table('prize_wheel_tokens') else []
        if 'token' not in wheel_token_columns:
            if not inspector.has_table('prize_wheel_tokens'):
                from models import PrizeWheelToken
                db.create_all()
            else:
                db.session.execute(text("ALTER TABLE prize_wheel_tokens ADD COLUMN token VARCHAR(64)"))
                db.session.commit()
                db.session.execute(text("ALTER TABLE prize_wheel_tokens ADD COLUMN order_id INTEGER REFERENCES orders(id)"))
                db.session.commit()
                db.session.execute(text("ALTER TABLE prize_wheel_tokens ADD COLUMN ip_address VARCHAR(45)"))
                db.session.commit()
                db.session.execute(text("ALTER TABLE prize_wheel_tokens ADD COLUMN user_agent VARCHAR(255)"))
                db.session.commit()

        wheel_segment_columns = [c['name'] for c in inspector.get_columns('prize_wheel_segments')] if inspector.has_table('prize_wheel_segments') else []
        if 'cantidad_disponible' not in wheel_segment_columns:
            db.session.execute(text("ALTER TABLE prize_wheel_segments ADD COLUMN cantidad_disponible INTEGER"))
            db.session.commit()
        if 'orden' not in wheel_segment_columns:
            db.session.execute(text("ALTER TABLE prize_wheel_segments ADD COLUMN orden INTEGER DEFAULT 0"))
            db.session.commit()

        spin_columns = [c['name'] for c in inspector.get_columns('prize_spins')] if inspector.has_table('prize_spins') else []
        if 'token_id' not in spin_columns:
            db.session.execute(text("ALTER TABLE prize_spins ADD COLUMN token_id INTEGER REFERENCES prize_wheel_tokens(id)"))
            db.session.commit()

    # Context processor para templates
    @app.context_processor
    def inject_cart_count():
        from flask import session
        cart = session.get('cart', [])
        return {'cart_count': len(cart)}

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
