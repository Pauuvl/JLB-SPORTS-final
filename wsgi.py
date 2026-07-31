"""
Punto de entrada WSGI para producción (gunicorn).

Ejemplo (ver Procfile):
    gunicorn -k eventlet -w 1 wsgi:app

Nota importante sobre Socket.IO + gunicorn:
  - Con websockets se recomienda 1 solo worker por proceso con el
    worker class 'eventlet' o 'gevent', usando Redis como
    SOCKETIO_MESSAGE_QUEUE si se necesita escalar a más de un proceso/dyno.
  - Si no se requiere WebSocket real (solo long-polling), se puede usar
    el worker 'sync' estándar de gunicorn sin -k eventlet.
"""
from app import create_app
from app.extensions import socketio

app = create_app()

# gunicorn -k eventlet apunta a `wsgi:app`. Cuando se ejecuta bajo
# eventlet, Flask-SocketIO parchea el socket real automáticamente.
