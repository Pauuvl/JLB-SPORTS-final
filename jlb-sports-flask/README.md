# JLB Sports — Sistema de Gestión Comercial (Flask + PostgreSQL)

Reescritura completa de JLB-SPORTS (originalmente Django) a **Flask +
SQLAlchemy + PostgreSQL + Socket.IO**, lista para producción 24/7 y
multi-dispositivo, sin perder ninguna funcionalidad del sistema original.

## Índice
- [Qué incluye esta versión](#qué-incluye-esta-versión)
- [Arquitectura](#arquitectura)
- [Instalación local](#instalación-local)
- [Variables de entorno](#variables-de-entorno)
- [Migraciones de base de datos](#migraciones-de-base-de-datos)
- [Migrar tus datos existentes de SQLite](#migrar-tus-datos-existentes-de-sqlite)
- [Ejecutar en desarrollo](#ejecutar-en-desarrollo)
- [Despliegue en producción (Render)](#despliegue-en-producción-render)
- [Tiempo real (Socket.IO)](#tiempo-real-socketio)
- [Seguridad](#seguridad)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Limitaciones conocidas / próximos pasos](#limitaciones-conocidas--próximos-pasos)

## Qué incluye esta versión

- ✅ Inventario, clientes, ventas (con stock por color), pedidos,
  cotizaciones, listas de precios — toda la lógica de negocio portada
  1:1 desde las vistas Django originales.
- ✅ PostgreSQL vía SQLAlchemy + Flask-Migrate (Alembic).
- ✅ Tiempo real con Flask-SocketIO: productos, ventas, pedidos y
  alertas de stock se reflejan al instante en todos los dispositivos
  conectados, sin recargar la página.
- ✅ Dashboard con KPIs (productos, stock, ventas del día/mes, ingresos,
  clientes, pedidos pendientes, última venta), sección "Productos más
  vendidos" con filtros por periodo + gráfico de barras y circular, y
  una sección de Estadísticas con 5 gráficas Chart.js.
- ✅ Alertas automáticas (stock bajo, agotado, venta inusual) que
  aparecen en vivo vía Socket.IO.
- ✅ Generación de PDF (facturas y cotizaciones) con ReportLab, mismo
  diseño que el original.
- ✅ CSRF (Flask-WTF), autenticación (Flask-Login), logging, manejo de
  errores 404/403/500, cabeceras de seguridad básicas.
- ✅ Script de migración de datos desde el `db.sqlite3` original de
  Django, con compatibilidad automática de contraseñas.

## Arquitectura

```
app/
  __init__.py          # App factory: registra extensiones, blueprints, logging
  config.py             # Configuración por variables de entorno
  extensions.py          # db, migrate, login_manager, csrf, socketio
  models.py              # Modelos SQLAlchemy (equivalentes a los de Django)
  utils.py                # Filtros Jinja2 (pesos, fechas, etc.)
  pdf.py                   # Generación de PDF (facturas / cotizaciones)
  sockets.py                # Eventos y alertas de Socket.IO
  blueprints/
    auth/       → /login/, /logout/
    dashboard/  → /, /dashboard/, /dashboard/api/*
    inventory/  → /inventory/products/, /inventory/categories/
    sales/      → /sales/
    clients/    → /clients/
    orders/     → /orders/
    pricing/    → /pricing/
    quotes/     → /quotes/
  templates/    # Jinja2 (convertidas desde las plantillas Django originales)
  static/       # CSS, JS (incluye realtime.js para Socket.IO), imágenes
migrations/     # Alembic (Flask-Migrate)
scripts/
  migrate_sqlite_to_postgres.py   # Migración de datos
run.py           # Entrypoint de desarrollo
wsgi.py          # Entrypoint de producción (gunicorn)
```

## Instalación local

Requisitos: Python 3.12+, PostgreSQL 14+ (o SQLite para probar rápido
sin instalar nada).

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edita .env con tus valores (SECRET_KEY, DATABASE_URL, etc.)
```

Si no tienes PostgreSQL a mano todavía, puedes dejar `DATABASE_URL`
vacío en `.env`: la app usará automáticamente un archivo SQLite en
`instance/jlb_dev.sqlite3` para que puedas probarla de inmediato.

## Variables de entorno

Ver `.env.example` para la lista completa. Las más importantes:

| Variable | Descripción |
|---|---|
| `SECRET_KEY` | Clave para sesiones y CSRF. Genera una con `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | Cadena de conexión PostgreSQL (`postgresql://usuario:pass@host:puerto/bd`) |
| `FLASK_ENV` | `development` o `production` |
| `LOW_STOCK_DEFAULT` | Umbral de stock bajo por defecto |
| `UNUSUAL_SALE_MULTIPLIER` | Cuántas veces el promedio activa la alerta de "venta inusual" |
| `SOCKETIO_MESSAGE_QUEUE` | (Opcional) URL de Redis si despliegas con más de 1 worker |

## Migraciones de base de datos

Las migraciones (Alembic, vía Flask-Migrate) ya están incluidas en
`migrations/`, con la migración inicial que crea todas las tablas.

```bash
export FLASK_APP=run.py

# Crear/actualizar las tablas en la base de datos configurada en DATABASE_URL
flask db upgrade

# Si en el futuro cambias un modelo en app/models.py:
flask db migrate -m "Descripción del cambio"
flask db upgrade
```

## Migrar tus datos existentes de SQLite

Si ya tenías datos en el `db.sqlite3` del proyecto Django original, no
se pierden. El script `scripts/migrate_sqlite_to_postgres.py` copia
todas las filas (usuarios, productos, clientes, ventas, pedidos,
cotizaciones, listas de precios) preservando los IDs originales.

```bash
# 1. Asegúrate de tener las tablas creadas en PostgreSQL
flask db upgrade

# 2. Copia tu db.sqlite3 original a la raíz de este proyecto (o indica la ruta)
python scripts/migrate_sqlite_to_postgres.py --sqlite ruta/a/tu/db.sqlite3
```

El script es idempotente: se puede ejecutar más de una vez sin generar
duplicados (usa upsert por ID). Las contraseñas de usuarios migrados
desde Django siguen funcionando: el sistema detecta automáticamente el
formato `pbkdf2_sha256$...` de Django y lo verifica de forma
compatible, sin necesidad de resetear contraseñas.

Para crear un usuario nuevo directamente en Flask:

```bash
flask create-admin
```

## Ejecutar en desarrollo

```bash
export FLASK_APP=run.py
export FLASK_ENV=development
flask db upgrade
flask create-admin        # si no migraste usuarios existentes
python run.py              # sirve en http://localhost:5000 con soporte WebSocket
```

## Despliegue en producción (Render)

Este proyecto incluye `render.yaml`, por lo que puedes desplegarlo
como **Blueprint** directamente desde el dashboard de Render
("New +" → "Blueprint", apuntando a este repositorio). Eso crea
automáticamente:

- Una base de datos PostgreSQL gestionada.
- El servicio web, con `SECRET_KEY` autogenerado y `DATABASE_URL`
  conectado a la base de datos anterior.

Si prefieres configurarlo manualmente:

1. Crea una base de datos PostgreSQL en Render y copia su
   "Internal Database URL".
2. Crea un Web Service apuntando a este repositorio.
   - **Build command:** `./build.sh`
   - **Start command:** `gunicorn -k eventlet -w 1 wsgi:app --bind 0.0.0.0:$PORT --log-file -`
3. Configura las variables de entorno (`SECRET_KEY`, `DATABASE_URL`,
   `FLASK_ENV=production`) en la sección "Environment".
4. Despliega. `build.sh` instala dependencias y corre `flask db
   upgrade` automáticamente en cada deploy.

El mismo `Procfile` funciona también en Railway y Heroku-style
platforms sin cambios.

**Nota sobre Socket.IO en producción:** se usa 1 solo worker de
gunicorn con el modo `eventlet` para soportar WebSockets de forma
nativa. Si necesitas escalar a más de un worker/dyno, configura
`SOCKETIO_MESSAGE_QUEUE` con una URL de Redis para que los eventos se
sincronicen entre procesos.

## Tiempo real (Socket.IO)

Cada creación/edición/eliminación de producto, cada venta, cada
cambio de stock y cada pedido emite un evento por WebSocket
(`app/sockets.py`) que todos los navegadores conectados reciben al
instante (`app/static/js/realtime.js`), sin recargar la página:

- `product_created` / `product_updated` / `product_deleted`
- `stock_changed`
- `sale_created` / `sale_cancelled`
- `order_created` / `order_confirmed` / `order_cancelled`
- `low_stock_alert` / `out_of_stock_alert` / `unusual_sale_alert`
- `dashboard_refresh` — dispara el refresco automático de las gráficas
  y KPIs del panel principal.

## Seguridad

- CSRF habilitado globalmente vía Flask-WTF.
- Contraseñas con hash seguro (`werkzeug.security`), con capa de
  compatibilidad para hashes migrados desde Django.
- Cabeceras de seguridad básicas (`X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Strict-Transport-Security` en
  producción).
- Cookies de sesión `HttpOnly` + `Secure` en producción.
- Todas las consultas usan el ORM de SQLAlchemy (sin SQL crudo con
  datos del usuario) — sin superficie de SQL Injection.
- Todas las rutas de negocio requieren `@login_required`.

## Estructura del proyecto

Ver el árbol en [Arquitectura](#arquitectura). Los nombres de URL
(`inventory.product_list`, `sales.sale_create`, etc.) siguen el mismo
esquema de rutas que tenía el proyecto Django, solo que organizados
en blueprints de Flask.

## Limitaciones conocidas / próximos pasos

Esta migración fue construida y probada con pruebas automatizadas de
extremo a extremo (creación de productos/clientes, ventas con
descuento de stock por color, pedidos → confirmación → conversión a
venta, cotizaciones y PDFs), pero **no ha sido probada manualmente en
un navegador real** ni contra una base de datos PostgreSQL real (se
probó localmente sobre SQLite; la sintaxis SQL usada es estándar y
portable, pero vale la pena hacer una pasada de QA visual antes de
usarla con clientes reales). Puntos a revisar antes de un lanzamiento:

- Verificar visualmente el dashboard, los formularios y los PDFs en un
  navegador (Chrome/Firefox/Safari, escritorio y móvil).
- Probar el flujo completo contra un PostgreSQL real (Render/local)
  antes de migrar datos de producción.
- Revisar el límite de tasa/anti-abuso en `/login/` si el sistema
  quedará expuesto públicamente (actualmente no hay límite de
  intentos).
- Si se necesita más de 1 worker en producción, configurar
  `SOCKETIO_MESSAGE_QUEUE` con Redis.
