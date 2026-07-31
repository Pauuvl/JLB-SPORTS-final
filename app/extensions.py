"""
Instancias únicas de extensiones Flask, creadas aquí para evitar
importaciones circulares entre app/__init__.py y los blueprints.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_socketio import SocketIO

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

# async_mode='threading' funciona sin dependencias extra en cualquier
# entorno WSGI estándar (gunicorn con worker sync o gthread).
# Para alta concurrencia en producción se recomienda gunicorn -k eventlet.
socketio = SocketIO(cors_allowed_origins='*', async_mode='threading')

login_manager.login_view = 'auth.login'
login_manager.login_message = 'Por favor inicia sesión para continuar.'
login_manager.login_message_category = 'info'
