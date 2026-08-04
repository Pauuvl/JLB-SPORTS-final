"""
Modelos SQLAlchemy — traducción 1:1 de los modelos Django originales
(inventory, clients, sales, orders, pricing, quotes) preservando
exactamente los mismos campos, relaciones, valores por defecto y
lógica de negocio (propiedades y métodos).

Nota de compatibilidad de plantillas: se agrega la propiedad `pk`
como alias de `id` en el mixin base para que las plantillas Jinja2
(portadas de Django) sigan usando `objeto.pk` sin cambios.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


class PkMixin:
    """Alias `.pk` -> `.id`, igual que Django, para reusar plantillas."""

    @property
    def pk(self):
        return self.id


# ══════════════════════════════════════════════════════════════════
# AUTENTICACIÓN (reemplaza django.contrib.auth.User)
# ══════════════════════════════════════════════════════════════════
class User(db.Model, UserMixin, PkMixin):
    __tablename__ = 'auth_user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False, index=True)
    email = db.Column(db.String(254), default='')
    first_name = db.Column(db.String(150), default='')
    last_name = db.Column(db.String(150), default='')
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    is_superuser = db.Column(db.Boolean, default=False)
    is_staff = db.Column(db.Boolean, default=False)
    date_joined = db.Column(db.DateTime, default=datetime.now)
    last_login = db.Column(db.DateTime, nullable=True)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        # Compatibilidad con hashes migrados desde Django (formato
        # 'pbkdf2_sha256$iteraciones$salt$hash'), para que los usuarios
        # existentes no tengan que resetear su contraseña tras migrar.
        if self.password_hash and self.password_hash.startswith('pbkdf2_sha256$'):
            return self._check_django_password(raw_password)
        return check_password_hash(self.password_hash, raw_password)

    def _check_django_password(self, raw_password):
        import base64
        import hashlib
        import hmac

        try:
            algorithm, iterations, salt, hash_b64 = self.password_hash.split('$', 3)
            iterations = int(iterations)
            derived = hashlib.pbkdf2_hmac('sha256', raw_password.encode(), salt.encode(), iterations)
            derived_b64 = base64.b64encode(derived).decode().strip()
            return hmac.compare_digest(derived_b64, hash_b64)
        except (ValueError, AttributeError):
            return False

    def get_full_name(self):
        full = f'{self.first_name} {self.last_name}'.strip()
        return full or self.username

    # Flask-Login usa get_id(); is_active ya lo provee UserMixin pero
    # lo sobreescribimos porque tenemos nuestra propia columna.
    @property
    def is_active_(self):
        return self.is_active

    def __repr__(self):
        return f'<User {self.username}>'


# ══════════════════════════════════════════════════════════════════
# INVENTORY
# ══════════════════════════════════════════════════════════════════
class Category(db.Model, PkMixin):
    __tablename__ = 'inventory_category'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default='')

    products = db.relationship('Product', back_populates='category')

    def __str__(self):
        return self.name


class Product(db.Model, PkMixin):
    __tablename__ = 'inventory_product'

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=True, default=None)
    name = db.Column(db.String(200), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('inventory_category.id', ondelete='SET NULL'), nullable=True)
    marca = db.Column(db.String(100), default='')
    # 'talla' y 'color' (texto plano) se conservan por compatibilidad con
    # datos antiguos, pero ya no se usan para capturar inventario: ahora
    # el detalle real vive en ProductStock (una fila por talla+color).
    talla = db.Column(db.String(20), default='')
    color = db.Column(db.String(100), default='')
    description = db.Column(db.Text, default='')
    cost_price = db.Column(db.Numeric(10, 2), nullable=False)
    sale_price = db.Column(db.Numeric(10, 2), nullable=False)
    stock_quantity = db.Column(db.Integer, default=0, nullable=False)
    min_stock = db.Column(db.Integer, default=5, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    category = db.relationship('Category', back_populates='products')
    stocks = db.relationship(
        'ProductStock', back_populates='product',
        cascade='all, delete-orphan', order_by='ProductStock.talla, ProductStock.color'
    )

    def __str__(self):
        return self.name

    def get_tallas_lista(self):
        """Tallas distintas registradas para este producto, en orden de creación."""
        seen = []
        for s in self.stocks:
            if s.talla not in seen:
                seen.append(s.talla)
        return seen

    def get_colores_por_talla(self):
        """Agrupa el stock por talla: {'M': [{'color': 'Rojo', 'stock': 5}, ...], ...}"""
        grouped = {}
        for s in self.stocks:
            grouped.setdefault(s.talla, []).append({'color': s.color, 'stock': s.stock})
        return grouped

    def recalculate_stock_quantity(self):
        """Recalcula el total agregado a partir del detalle por talla/color."""
        self.stock_quantity = sum(s.stock for s in self.stocks)

    @property
    def stock_value(self):
        return (self.cost_price or Decimal('0')) * self.stock_quantity

    @property
    def is_low_stock(self):
        return self.stock_quantity > 0 and self.stock_quantity <= self.min_stock

    @property
    def profit_margin(self):
        if self.cost_price and self.cost_price > 0:
            return ((self.sale_price - self.cost_price) / self.cost_price) * 100
        return 0


class ProductStock(db.Model, PkMixin):
    """Stock individual por combinación talla + color de un producto."""
    __tablename__ = 'inventory_productstock'
    __table_args__ = (db.UniqueConstraint('product_id', 'talla', 'color', name='uq_product_talla_color'),)

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('inventory_product.id', ondelete='CASCADE'), nullable=False)
    talla = db.Column(db.String(20), nullable=False, default='')
    color = db.Column(db.String(100), nullable=False, default='')
    stock = db.Column(db.Integer, default=0)

    product = db.relationship('Product', back_populates='stocks')

    def __str__(self):
        return f'{self.product.name} — Talla {self.talla} / {self.color}: {self.stock}'


# Alias de compatibilidad por si algún código o migración antigua todavía
# referencia el nombre anterior.
ProductColorStock = ProductStock


# ══════════════════════════════════════════════════════════════════
# CLIENTS
# ══════════════════════════════════════════════════════════════════
CLIENT_TYPES = [
    ('regular', 'Regular'),
    ('Distribuidor', 'Distribuidor'),
    ('Almacen', 'Almacen'),
    ('Entrenador', 'Entrenador'),
]
CLIENT_TYPE_LABELS = dict(CLIENT_TYPES)


class Client(db.Model, PkMixin):
    __tablename__ = 'clients_client'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    cedula = db.Column(db.String(30), default='')
    client_type = db.Column(db.String(20), default='regular')
    email = db.Column(db.String(254), default='')
    phone = db.Column(db.String(20), default='')
    municipio = db.Column(db.String(100), default='')
    address = db.Column(db.Text, default='')
    discount_percent = db.Column(db.Numeric(5, 2), default=0)
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.now)

    sales = db.relationship('Sale', back_populates='client')
    orders = db.relationship('Order', back_populates='client')
    quotes = db.relationship('Quote', back_populates='client')

    def __str__(self):
        return f'{self.name} ({self.get_client_type_display()})'

    def get_client_type_display(self):
        return CLIENT_TYPE_LABELS.get(self.client_type, self.client_type)

    @property
    def price_multiplier(self):
        total_discount = float(self.discount_percent or 0)
        return 1 - (total_discount / 100)


# ══════════════════════════════════════════════════════════════════
# SALES
# ══════════════════════════════════════════════════════════════════
SALE_STATUS_CHOICES = [('completed', 'Completada'), ('cancelled', 'Anulada')]
SALE_STATUS_LABELS = dict(SALE_STATUS_CHOICES)


class Sale(db.Model, PkMixin):
    __tablename__ = 'sales_sale'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients_client.id', ondelete='SET NULL'), nullable=True)
    client_name = db.Column(db.String(200), default='')  # nombre libre si el cliente no está registrado
    vendedor = db.Column(db.String(150), default='')
    status = db.Column(db.String(20), default='completed')
    notes = db.Column(db.Text, default='')
    total_amount = db.Column(db.Numeric(12, 2), default=0)
    discount_applied = db.Column(db.Numeric(5, 2), default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)

    client = db.relationship('Client', back_populates='sales')
    items = db.relationship('SaleItem', back_populates='sale', cascade='all, delete-orphan')

    def __str__(self):
        return f'Venta #{self.pk} - {self.display_client} - ${self.total_amount}'

    def get_status_display(self):
        return SALE_STATUS_LABELS.get(self.status, self.status)

    @property
    def display_client(self):
        if self.client:
            return self.client.name
        return self.client_name or 'Mostrador'

    def calculate_total(self):
        subtotal = sum((item.subtotal for item in self.items), Decimal('0'))
        if self.discount_applied:
            factor = 1 - (Decimal(str(self.discount_applied)) / 100)
            self.total_amount = subtotal * factor
        else:
            self.total_amount = subtotal
        db.session.commit()


class SaleItem(db.Model, PkMixin):
    __tablename__ = 'sales_saleitem'

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales_sale.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('inventory_product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    talla_vendida = db.Column(db.String(20), default='')
    color_vendido = db.Column(db.String(100), default='')

    sale = db.relationship('Sale', back_populates='items')
    product = db.relationship('Product')

    def __str__(self):
        color_str = f' ({self.color_vendido})' if self.color_vendido else ''
        return f'{self.product.name}{color_str} x{self.quantity}'

    @property
    def subtotal(self):
        return self.unit_price * self.quantity


# ══════════════════════════════════════════════════════════════════
# ORDERS (Pedidos)
# ══════════════════════════════════════════════════════════════════
ORDER_STATUS_CHOICES = [
    ('pending', 'Pendiente'),
    ('confirmed', 'Confirmado'),
    ('converted', 'Convertido a Venta'),
    ('cancelled', 'Cancelado'),
]
ORDER_STATUS_LABELS = dict(ORDER_STATUS_CHOICES)


class Order(db.Model, PkMixin):
    __tablename__ = 'orders_order'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients_client.id', ondelete='SET NULL'), nullable=True)
    status = db.Column(db.String(20), default='pending')
    notes = db.Column(db.Text, default='')
    total_amount = db.Column(db.Numeric(12, 2), default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)
    confirmed_at = db.Column(db.DateTime, nullable=True)

    client = db.relationship('Client', back_populates='orders')
    items = db.relationship('OrderItem', back_populates='order', cascade='all, delete-orphan')

    def __str__(self):
        client_name = self.client.name if self.client else 'Mostrador'
        return f'Pedido #{self.pk} - {client_name} ({self.get_status_display()})'

    def get_status_display(self):
        return ORDER_STATUS_LABELS.get(self.status, self.status)

    def calculate_total(self):
        total = sum((item.subtotal for item in self.items), Decimal('0'))
        self.total_amount = total
        db.session.commit()

    def confirm(self):
        """Descuenta stock de todos los items y marca el pedido como confirmado."""
        for item in self.items:
            product = Product.query.with_for_update().get(item.product_id)
            if product.stock_quantity < item.quantity:
                raise ValueError(
                    f'Stock insuficiente para "{product.name}". '
                    f'Disponible: {product.stock_quantity}, Requerido: {item.quantity}'
                )
            product.stock_quantity -= item.quantity
        self.status = 'confirmed'
        self.confirmed_at = datetime.now()
        db.session.commit()


class OrderItem(db.Model, PkMixin):
    __tablename__ = 'orders_orderitem'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders_order.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('inventory_product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)

    order = db.relationship('Order', back_populates='items')
    product = db.relationship('Product')

    def __str__(self):
        return f'{self.product.name} x{self.quantity}'

    @property
    def subtotal(self):
        return self.unit_price * self.quantity


# ══════════════════════════════════════════════════════════════════
# PRICING
# ══════════════════════════════════════════════════════════════════
class PriceList(db.Model, PkMixin):
    __tablename__ = 'pricing_pricelist'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    client_type = db.Column(db.String(20), default='')
    description = db.Column(db.Text, default='')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    items = db.relationship('PriceListItem', back_populates='price_list', cascade='all, delete-orphan')

    def __str__(self):
        return self.name


class PriceListItem(db.Model, PkMixin):
    __tablename__ = 'pricing_pricelistitem'
    __table_args__ = (db.UniqueConstraint('price_list_id', 'product_id', name='uq_pricelist_product'),)

    id = db.Column(db.Integer, primary_key=True)
    price_list_id = db.Column(db.Integer, db.ForeignKey('pricing_pricelist.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('inventory_product.id', ondelete='CASCADE'), nullable=False)
    custom_price = db.Column(db.Numeric(10, 2), nullable=False)

    price_list = db.relationship('PriceList', back_populates='items')
    product = db.relationship('Product')

    def __str__(self):
        return f'{self.price_list.name} - {self.product.name}: ${self.custom_price}'


# ══════════════════════════════════════════════════════════════════
# QUOTES (Cotizaciones)
# ══════════════════════════════════════════════════════════════════
QUOTE_STATUS_CHOICES = [
    ('draft', 'Borrador'),
    ('sent', 'Enviada'),
    ('accepted', 'Aceptada'),
    ('rejected', 'Rechazada'),
]
QUOTE_STATUS_LABELS = dict(QUOTE_STATUS_CHOICES)


class Quote(db.Model, PkMixin):
    __tablename__ = 'quotes_quote'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients_client.id', ondelete='SET NULL'), nullable=True)
    client_name = db.Column(db.String(200), default='')
    status = db.Column(db.String(20), default='draft')
    notes = db.Column(db.Text, default='')
    valid_days = db.Column(db.Integer, default=15)
    discount_applied = db.Column(db.Numeric(5, 2), default=0)
    total_amount = db.Column(db.Numeric(12, 2), default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)

    client = db.relationship('Client', back_populates='quotes')
    items = db.relationship('QuoteItem', back_populates='quote', cascade='all, delete-orphan')

    def __str__(self):
        return f'Cotizacion #{self.pk} — {self.display_client}'

    def get_status_display(self):
        return QUOTE_STATUS_LABELS.get(self.status, self.status)

    def calculate_total(self):
        subtotal = sum((item.subtotal for item in self.items), Decimal('0'))
        if self.discount_applied:
            factor = 1 - (Decimal(str(self.discount_applied)) / 100)
            self.total_amount = subtotal * factor
        else:
            self.total_amount = subtotal
        db.session.commit()

    @property
    def display_client(self):
        if self.client:
            return self.client.name
        return self.client_name or 'Sin cliente'


class QuoteItem(db.Model, PkMixin):
    __tablename__ = 'quotes_quoteitem'

    id = db.Column(db.Integer, primary_key=True)
    quote_id = db.Column(db.Integer, db.ForeignKey('quotes_quote.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('inventory_product.id', ondelete='SET NULL'), nullable=True)
    description = db.Column(db.String(300), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)

    quote = db.relationship('Quote', back_populates='items')
    product = db.relationship('Product')

    @property
    def subtotal(self):
        return self.unit_price * self.quantity


def parse_decimal(value, field_name):
    """Parsea un valor Decimal desde un formulario, con mensaje de error claro."""
    try:
        val = Decimal(str(value).strip())
        if val < 0:
            raise ValueError(f'"{field_name}" no puede ser negativo.')
        return val
    except InvalidOperation:
        raise ValueError(f'"{field_name}" no es un número válido.')
