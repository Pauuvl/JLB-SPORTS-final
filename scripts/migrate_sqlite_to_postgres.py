"""
Migración de datos: SQLite (proyecto Django original) -> PostgreSQL
(nuevo esquema Flask/SQLAlchemy).

Este script NO migra el esquema (eso lo hace `flask db upgrade` con las
migraciones de Alembic) — solo copia los datos existentes, tabla por
tabla, preservando IDs originales para no romper las relaciones (FKs).

Uso:
    1. Asegúrate de tener la base de datos PostgreSQL ya creada y con
       las tablas migradas:
           flask db upgrade
    2. Copia tu archivo db.sqlite3 original (el de Django) a la raíz
       de este proyecto, o pasa la ruta con --sqlite.
    3. Ejecuta:
           python scripts/migrate_sqlite_to_postgres.py --sqlite ruta/a/db.sqlite3

El script es idempotente para PostgreSQL: si una fila con el mismo id
ya existe, la actualiza en vez de duplicarla (upsert), por lo que se
puede correr más de una vez sin generar duplicados.
"""
import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.extensions import db
from app.models import (User, Category, Product, ProductStock, Client,
                         Sale, SaleItem, Order, OrderItem, PriceList,
                         PriceListItem, Quote, QuoteItem)


# Orden de migración: primero las tablas sin dependencias, luego las
# que referencian a otras (respeta las foreign keys).
TABLE_PLAN = [
    # (tabla sqlite, modelo, mapeo de columnas sqlite -> campo del modelo)
    ('auth_user', User, {
        'id': 'id', 'username': 'username', 'email': 'email',
        'first_name': 'first_name', 'last_name': 'last_name',
        'password': 'password_hash', 'is_active': 'is_active',
        'is_superuser': 'is_superuser', 'is_staff': 'is_staff',
        'date_joined': 'date_joined', 'last_login': 'last_login',
    }),
    ('inventory_category', Category, {
        'id': 'id', 'name': 'name', 'description': 'description',
    }),
    ('clients_client', Client, {
        'id': 'id', 'name': 'name', 'cedula': 'cedula', 'client_type': 'client_type',
        'email': 'email', 'phone': 'phone', 'municipio': 'municipio', 'address': 'address',
        'discount_percent': 'discount_percent', 'notes': 'notes', 'created_at': 'created_at',
    }),
    ('inventory_product', Product, {
        # 'talla'/'color' del Django original ya no se cargan al producto:
        # se usan solo para decidir la talla por defecto en ProductStock (ver abajo).
        'id': 'id', 'codigo': 'codigo', 'name': 'name', 'category_id': 'category_id',
        'marca': 'marca', 'description': 'description',
        'cost_price': 'cost_price', 'sale_price': 'sale_price', 'stock_quantity': 'stock_quantity',
        'min_stock': 'min_stock', 'created_at': 'created_at',
    }),
    # inventory_productcolorstock se migra aparte (ver migrate_product_stock),
    # porque el esquema nuevo agrega una dimensión (talla) que no existía en Django.
    ('sales_sale', Sale, {
        'id': 'id', 'client_id': 'client_id', 'status': 'status', 'notes': 'notes',
        'total_amount': 'total_amount', 'discount_applied': 'discount_applied', 'created_at': 'created_at',
    }),
    ('sales_saleitem', SaleItem, {
        'id': 'id', 'sale_id': 'sale_id', 'product_id': 'product_id', 'quantity': 'quantity',
        'unit_price': 'unit_price', 'color_vendido': 'color_vendido',
    }),
    ('orders_order', Order, {
        'id': 'id', 'client_id': 'client_id', 'status': 'status', 'notes': 'notes',
        'total_amount': 'total_amount', 'created_at': 'created_at', 'confirmed_at': 'confirmed_at',
    }),
    ('orders_orderitem', OrderItem, {
        'id': 'id', 'order_id': 'order_id', 'product_id': 'product_id',
        'quantity': 'quantity', 'unit_price': 'unit_price',
    }),
    ('pricing_pricelist', PriceList, {
        'id': 'id', 'name': 'name', 'client_type': 'client_type', 'description': 'description',
        'is_active': 'is_active', 'created_at': 'created_at',
    }),
    ('pricing_pricelistitem', PriceListItem, {
        'id': 'id', 'price_list_id': 'price_list_id', 'product_id': 'product_id',
        'custom_price': 'custom_price',
    }),
    ('quotes_quote', Quote, {
        'id': 'id', 'client_id': 'client_id', 'client_name': 'client_name', 'status': 'status',
        'notes': 'notes', 'valid_days': 'valid_days', 'discount_applied': 'discount_applied',
        'total_amount': 'total_amount', 'created_at': 'created_at',
    }),
    ('quotes_quoteitem', QuoteItem, {
        'id': 'id', 'quote_id': 'quote_id', 'product_id': 'product_id', 'description': 'description',
        'quantity': 'quantity', 'unit_price': 'unit_price',
    }),
]


def _parse_datetime(value):
    """SQLite (Django) guarda las fechas como texto; PostgreSQL/SQLAlchemy
    necesitan objetos datetime reales."""
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    return None


def migrate_product_stock(sqlite_con):
    """Migra inventory_productcolorstock (esquema Django, sin talla) hacia
    ProductStock (esquema nuevo, con talla). Usa la talla que tenía cada
    producto en Django (o 'Única' si no tenía) como talla por defecto.
    Los productos que no tenían desglose por color en absoluto se migran
    como una sola fila con su stock_quantity total, para no perder unidades.
    """
    cur = sqlite_con.cursor()

    try:
        cur.execute('SELECT id, talla, stock_quantity FROM inventory_product')
        productos = {row[0]: {'talla': row[1] or '', 'stock_quantity': row[2] or 0} for row in cur.fetchall()}
    except sqlite3.OperationalError as e:
        print(f'  ⚠️  Saltando migración de stock por talla/color: {e}')
        return 0

    count = 0
    productos_con_color = set()

    try:
        cur.execute('SELECT id, product_id, color, stock FROM inventory_productcolorstock')
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        rows = []

    for old_id, product_id, color, stock in rows:
        info = productos.get(product_id, {})
        talla = info.get('talla') or 'Única'
        productos_con_color.add(product_id)

        existing = ProductStock.query.filter_by(product_id=product_id, talla=talla, color=color).first()
        if existing is None:
            existing = ProductStock(product_id=product_id, talla=talla, color=color)
            db.session.add(existing)
        existing.stock = stock
        count += 1

    # Productos sin ninguna fila de color: se crea una fila con su stock total.
    for product_id, info in productos.items():
        if product_id in productos_con_color or info['stock_quantity'] <= 0:
            continue
        talla = info.get('talla') or 'Única'
        existing = ProductStock.query.filter_by(product_id=product_id, talla=talla, color='').first()
        if existing is None:
            existing = ProductStock(product_id=product_id, talla=talla, color='', stock=info['stock_quantity'])
            db.session.add(existing)
            count += 1

    db.session.commit()
    return count


def migrate_table(sqlite_con, sqlite_table, model, column_map):
    from sqlalchemy import DateTime

    cur = sqlite_con.cursor()
    try:
        cur.execute(f'SELECT {", ".join(column_map.keys())} FROM {sqlite_table}')
    except sqlite3.OperationalError as e:
        print(f'  ⚠️  Saltando {sqlite_table}: {e}')
        return 0

    datetime_fields = {
        c.name for c in model.__table__.columns if isinstance(c.type, DateTime)
    }

    rows = cur.fetchall()
    count = 0
    for row in rows:
        data = dict(zip(column_map.values(), row))
        for field in datetime_fields:
            if field in data:
                data[field] = _parse_datetime(data[field])
        pk = data.get('id')
        instance = db.session.get(model, pk) if pk is not None else None
        if instance is None:
            instance = model()
            db.session.add(instance)
        for field, value in data.items():
            setattr(instance, field, value)
        count += 1
    db.session.commit()
    return count


def reset_postgres_sequences(engine):
    """Después de insertar filas con IDs explícitos, las secuencias
    SERIAL de Postgres quedan desincronizadas. Las reajusta a MAX(id)+1
    para que las próximas inserciones automáticas no colisionen."""
    from sqlalchemy import text

    if engine.dialect.name != 'postgresql':
        return

    tables = [m.__table__.name for _, m, _ in TABLE_PLAN] + ['inventory_productstock']
    with engine.begin() as conn:
        for table in tables:
            conn.execute(text(f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table}), 1),
                    (SELECT MAX(id) IS NOT NULL FROM {table})
                )
            """))


def main():
    parser = argparse.ArgumentParser(description='Migra datos de SQLite (Django) a PostgreSQL (Flask).')
    parser.add_argument('--sqlite', default='db.sqlite3', help='Ruta al archivo db.sqlite3 original de Django')
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        print(f'❌ No se encontró el archivo SQLite: {sqlite_path}')
        sys.exit(1)

    app = create_app()
    with app.app_context():
        engine_name = db.engine.url.get_backend_name()
        print(f'→ Base de datos destino: {engine_name} ({db.engine.url.render_as_string(hide_password=True)})')
        if engine_name != 'postgresql':
            print('  ⚠️  ADVERTENCIA: DATABASE_URL no apunta a PostgreSQL. Continúa solo si es intencional.')

        sqlite_con = sqlite3.connect(str(sqlite_path))
        print(f'→ Leyendo datos de: {sqlite_path}\n')

        total = 0
        for table_name, model, column_map in TABLE_PLAN:
            count = migrate_table(sqlite_con, table_name, model, column_map)
            total += count
            print(f'  ✅ {table_name:32s} → {count:5d} filas migradas a {model.__tablename__}')

            if table_name == 'inventory_product':
                stock_count = migrate_product_stock(sqlite_con)
                total += stock_count
                print(f'  ✅ {"inventory_productcolorstock":32s} → {stock_count:5d} filas migradas a inventory_productstock (talla+color)')

        reset_postgres_sequences(db.engine)
        sqlite_con.close()

        print(f'\n✅ Migración completa: {total} filas migradas en total.')
        print('   Nota: las contraseñas de usuario migradas siguen siendo válidas')
        print('   (se mantiene compatibilidad automática con hashes pbkdf2_sha256 de Django).')


if __name__ == '__main__':
    main()
