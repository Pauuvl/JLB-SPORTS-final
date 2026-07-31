"""
Configuración de la aplicación basada en variables de entorno.
Nunca se deben poner secretos directamente en este archivo: todo se
lee de variables de entorno (ver .env.example).
"""
import os


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me-in-production')

    # ── Base de datos ──────────────────────────────────────────────
    # Se admite DATABASE_URL en formato postgres:// o postgresql://
    _database_url = os.environ.get('DATABASE_URL', '')
    if _database_url.startswith('postgres://'):
        # Render/Heroku entregan 'postgres://', SQLAlchemy 1.4+ requiere 'postgresql://'
        _database_url = _database_url.replace('postgres://', 'postgresql://', 1)

    SQLALCHEMY_DATABASE_URI = _database_url or 'sqlite:///' + os.path.join(
        os.path.abspath(os.path.dirname(os.path.dirname(__file__))), 'instance', 'jlb_dev.sqlite3'
    )
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 280,
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Sesión / Auth ───────────────────────────────────────────────
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_DURATION = 60 * 60 * 24 * 14  # 14 días

    # ── Negocio ─────────────────────────────────────────────────────
    LOW_STOCK_DEFAULT = int(os.environ.get('LOW_STOCK_DEFAULT', '5'))
    UNUSUAL_SALE_MULTIPLIER = float(os.environ.get('UNUSUAL_SALE_MULTIPLIER', '3'))

    # ── SocketIO ────────────────────────────────────────────────────
    SOCKETIO_MESSAGE_QUEUE = os.environ.get('SOCKETIO_MESSAGE_QUEUE')  # redis:// opcional multi-worker

    # ── Logging ─────────────────────────────────────────────────────
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_TO_STDOUT = os.environ.get('LOG_TO_STDOUT', '1') == '1'


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = 'https'


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
}


def get_config():
    env = os.environ.get('FLASK_ENV', os.environ.get('APP_ENV', 'production'))
    return config_by_name.get(env, ProductionConfig)
