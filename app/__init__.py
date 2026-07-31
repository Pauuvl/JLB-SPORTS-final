import logging
import os
import sys

from flask import Flask, render_template

from app.config import get_config
from app.extensions import db, migrate, login_manager, csrf, socketio
from app.utils import register_filters


def create_app(config_object=None):
    app = Flask(__name__)
    app.config.from_object(config_object or get_config())

    _configure_logging(app)

    # ── Extensiones ──────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    socketio.init_app(app, message_queue=app.config.get('SOCKETIO_MESSAGE_QUEUE'))

    register_filters(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ── Blueprints ───────────────────────────────────────────────
    from app.blueprints.auth.routes import bp as auth_bp
    from app.blueprints.dashboard.routes import bp as dashboard_bp
    from app.blueprints.inventory.routes import bp as inventory_bp
    from app.blueprints.sales.routes import bp as sales_bp
    from app.blueprints.clients.routes import bp as clients_bp
    from app.blueprints.orders.routes import bp as orders_bp
    from app.blueprints.pricing.routes import bp as pricing_bp
    from app.blueprints.quotes.routes import bp as quotes_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(sales_bp, url_prefix='/sales')
    app.register_blueprint(clients_bp, url_prefix='/clients')
    app.register_blueprint(orders_bp, url_prefix='/orders')
    app.register_blueprint(pricing_bp, url_prefix='/pricing')
    app.register_blueprint(quotes_bp, url_prefix='/quotes')

    from app import sockets as _sockets  # noqa: F401

    _register_error_handlers(app)
    _register_security_headers(app)
    _register_cli(app)

    # ------------------------------------------------------------
    # Crear administrador automáticamente si no existe
    # ------------------------------------------------------------
    with app.app_context():
        from app.models import User

        username = os.environ.get("ADMIN_USERNAME")
        email = os.environ.get("ADMIN_EMAIL", "")
        password = os.environ.get("ADMIN_PASSWORD")

        if username and password:
            admin = User.query.filter_by(username=username).first()

            if admin is None:
                admin = User(
                    username=username,
                    email=email,
                    is_superuser=True,
                    is_staff=True
                )

                admin.set_password(password)

                db.session.add(admin)
                db.session.commit()

                app.logger.info(
                    f'Administrador "{username}" creado automáticamente.'
                )

    return app


def _configure_logging(app):
    level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO'), logging.INFO)
    handler = (
        logging.StreamHandler(sys.stdout)
        if app.config.get('LOG_TO_STDOUT', True)
        else logging.NullHandler()
    )

    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )

    handler.setFormatter(formatter)

    app.logger.handlers = [handler]
    app.logger.setLevel(level)

    logging.getLogger('werkzeug').setLevel(level)


def _register_error_handlers(app):

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception('Error interno del servidor: %s', e)
        db.session.rollback()
        return render_template('errors/500.html'), 500


def _register_security_headers(app):
    """Cabeceras básicas de seguridad."""

    @app.after_request
    def set_secure_headers(response):
        response.headers.setdefault(
            'X-Content-Type-Options',
            'nosniff'
        )
        response.headers.setdefault(
            'X-Frame-Options',
            'DENY'
        )
        response.headers.setdefault(
            'Referrer-Policy',
            'same-origin'
        )

        if app.config.get('PREFERRED_URL_SCHEME') == 'https':
            response.headers.setdefault(
                'Strict-Transport-Security',
                'max-age=31536000; includeSubDomains'
            )

        return response


def _register_cli(app):

    @app.cli.command('create-admin')
    def create_admin():
        """Crea un superusuario interactivo."""
        import getpass
        from app.models import User

        username = input('Usuario: ').strip()
        email = input('Email (opcional): ').strip()
        password = getpass.getpass('Contraseña: ')

        if User.query.filter_by(username=username).first():
            print(f'El usuario "{username}" ya existe.')
            return

        user = User(
            username=username,
            email=email,
            is_superuser=True,
            is_staff=True
        )

        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        print(f'Superusuario "{username}" creado correctamente.')

    @app.cli.command('seed-demo')
    def seed_demo():
        """Crea datos mínimos de ejemplo."""
        from app.models import Category, Product

        if Category.query.count() == 0:

            cat = Category(
                name='General',
                description='Categoría de ejemplo'
            )

            db.session.add(cat)
            db.session.commit()

            db.session.add(
                Product(
                    name='Producto de ejemplo',
                    category_id=cat.id,
                    cost_price=10000,
                    sale_price=15000,
                    stock_quantity=20,
                    min_stock=5
                )
            )

            db.session.commit()
            print('Datos de ejemplo creados.')

        else:
            print('Ya existen datos; no se hizo nada.')
