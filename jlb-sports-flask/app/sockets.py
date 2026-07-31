"""
Capa de tiempo real con Flask-SocketIO.

Cada vez que se crea/edita/elimina un producto, se registra una venta,
o cambia el inventario, se emite un evento por WebSocket a todos los
clientes conectados para que actualicen la UI sin recargar la página.

Eventos emitidos (namespace por defecto '/'):
  - 'product_created' / 'product_updated' / 'product_deleted'
  - 'stock_changed'            {product_id, name, stock_quantity, is_low_stock}
  - 'sale_created' / 'sale_cancelled'
  - 'order_created' / 'order_confirmed' / 'order_cancelled'
  - 'low_stock_alert'          producto cruzó el umbral de stock bajo
  - 'out_of_stock_alert'       producto llegó a cero
  - 'unusual_sale_alert'       venta con monto inusualmente alto
  - 'dashboard_refresh'        señal genérica para refrescar KPIs/gráficas
"""
from flask import current_app
from flask_socketio import emit

from app.extensions import socketio


def _emit(event, payload):
    """Emite un evento a todos los clientes conectados (broadcast)."""
    try:
        socketio.emit(event, payload)
    except Exception as exc:  # pragma: no cover - nunca debe tumbar una request
        current_app.logger.warning('No se pudo emitir evento socket %s: %s', event, exc)


def emit_product_created(product):
    _emit('product_created', {'id': product.id, 'name': product.name})
    _emit('dashboard_refresh', {'reason': 'product_created'})
    check_stock_alerts(product)


def emit_product_updated(product):
    _emit('product_updated', {'id': product.id, 'name': product.name,
                               'stock_quantity': product.stock_quantity})
    _emit('dashboard_refresh', {'reason': 'product_updated'})
    check_stock_alerts(product)


def emit_product_deleted(product_id, name):
    _emit('product_deleted', {'id': product_id, 'name': name})
    _emit('dashboard_refresh', {'reason': 'product_deleted'})


def emit_stock_changed(product):
    _emit('stock_changed', {
        'id': product.id,
        'name': product.name,
        'stock_quantity': product.stock_quantity,
        'is_low_stock': product.is_low_stock,
    })
    check_stock_alerts(product)


def emit_sale_created(sale):
    _emit('sale_created', {
        'id': sale.id,
        'total_amount': float(sale.total_amount),
        'client': sale.client.name if sale.client else 'Mostrador',
    })
    _emit('dashboard_refresh', {'reason': 'sale_created'})
    check_unusual_sale(sale)


def emit_sale_cancelled(sale):
    _emit('sale_cancelled', {'id': sale.id})
    _emit('dashboard_refresh', {'reason': 'sale_cancelled'})


def emit_order_event(name, order):
    _emit(name, {'id': order.id, 'status': order.status})
    _emit('dashboard_refresh', {'reason': name})


def check_stock_alerts(product):
    """Emite alertas automáticas de stock bajo / agotado."""
    if product.stock_quantity == 0:
        _emit('out_of_stock_alert', {
            'id': product.id,
            'name': product.name,
            'message': f'⚠️ "{product.name}" se quedó SIN STOCK.',
        })
    elif product.is_low_stock:
        _emit('low_stock_alert', {
            'id': product.id,
            'name': product.name,
            'stock_quantity': product.stock_quantity,
            'min_stock': product.min_stock,
            'message': f'⚠️ Stock bajo en "{product.name}": quedan {product.stock_quantity} unidades.',
        })


def check_unusual_sale(sale):
    """Emite una alerta si el monto de la venta es inusualmente alto
    comparado con el promedio histórico de ventas completadas."""
    from sqlalchemy import func
    from app.extensions import db
    from app.models import Sale

    multiplier = current_app.config.get('UNUSUAL_SALE_MULTIPLIER', 3)
    avg_total = db.session.query(func.avg(Sale.total_amount)).filter(
        Sale.status == 'completed', Sale.id != sale.id
    ).scalar()

    if avg_total and sale.total_amount and float(sale.total_amount) > float(avg_total) * multiplier:
        _emit('unusual_sale_alert', {
            'id': sale.id,
            'total_amount': float(sale.total_amount),
            'average': float(avg_total),
            'message': f'📈 Venta inusualmente alta detectada: #{sale.id} por {sale.total_amount:,.0f}.',
        })


@socketio.on('connect')
def handle_connect():
    emit('connected', {'message': 'Conectado al servidor JLB Sports en tiempo real.'})
