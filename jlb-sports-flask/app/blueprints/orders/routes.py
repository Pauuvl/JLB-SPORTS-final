import json
from decimal import Decimal

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from app.extensions import db
from app.models import Order, OrderItem, Product, Client, Sale, SaleItem
from app.sockets import emit_order_event, emit_stock_changed, emit_sale_created

bp = Blueprint('orders', __name__)


@bp.route('/')
@login_required
def order_list():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template('orders/order_list.html', orders=orders, active_page='orders')


@bp.route('/new/', methods=['GET', 'POST'])
@login_required
def order_create():
    products = Product.query.order_by(Product.name).all()
    products_json = json.dumps([
        {'id': p.pk, 'nombre': p.name, 'precio': float(p.sale_price), 'stock': p.stock_quantity}
        for p in products
    ])
    clients = Client.query.order_by(Client.name).all()

    if request.method == 'POST':
        client_id = request.form.get('client') or None
        notes = request.form.get('notes', '')
        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')

        if not product_ids:
            flash('Debe agregar al menos un producto.', 'error')
            return render_template('orders/order_form.html', products=products, products_json=products_json,
                                    clients=clients, active_page='orders')

        client = Client.query.get(client_id) if client_id else None
        price_multiplier = client.price_multiplier if client else 1.0

        order = Order(client=client, notes=notes)
        db.session.add(order)
        db.session.flush()

        for pid, qty in zip(product_ids, quantities):
            product = Product.query.get(pid)
            unit_price = Decimal(str(product.sale_price)) * Decimal(str(price_multiplier))
            db.session.add(OrderItem(
                order=order, product=product, quantity=int(qty),
                unit_price=unit_price.quantize(Decimal('0.01')),
            ))

        db.session.flush()
        order.calculate_total()
        db.session.commit()
        emit_order_event('order_created', order)

        flash(f'Pedido #{order.pk} creado.', 'success')
        return redirect(url_for('orders.order_list'))

    return render_template('orders/order_form.html', products=products, products_json=products_json,
                            clients=clients, active_page='orders')


@bp.route('/<int:pk>/')
@login_required
def order_detail(pk):
    order = Order.query.get_or_404(pk)
    return render_template('orders/order_detail.html', order=order, active_page='orders')


@bp.route('/<int:pk>/confirm/', methods=['GET', 'POST'])
@login_required
def order_confirm(pk):
    order = Order.query.get_or_404(pk)
    if request.method == 'POST':
        if order.status != 'pending':
            flash('Este pedido ya fue procesado.', 'warning')
            return redirect(url_for('orders.order_detail', pk=pk))
        try:
            order.confirm()
            for item in order.items:
                emit_stock_changed(item.product)
            emit_order_event('order_confirmed', order)
            flash(f'Pedido #{order.pk} confirmado. Stock descontado.', 'success')
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'error')
        return redirect(url_for('orders.order_detail', pk=pk))
    return render_template('orders/order_confirm.html', order=order, active_page='orders')


@bp.route('/<int:pk>/to-sale/', methods=['GET', 'POST'])
@login_required
def order_to_sale(pk):
    order = Order.query.get_or_404(pk)
    if request.method == 'POST':
        if order.status != 'confirmed':
            flash('Solo los pedidos confirmados pueden convertirse en venta.', 'error')
            return redirect(url_for('orders.order_detail', pk=pk))

        sale = Sale(
            client=order.client,
            notes=f'Generado desde Pedido #{order.pk}. {order.notes}'.strip(),
            discount_applied=(order.client.discount_percent if order.client else 0),
            total_amount=order.total_amount,
        )
        db.session.add(sale)
        db.session.flush()

        for item in order.items:
            db.session.add(SaleItem(sale=sale, product=item.product, quantity=item.quantity,
                                     unit_price=item.unit_price))

        order.status = 'converted'
        db.session.commit()
        emit_sale_created(sale)
        emit_order_event('order_converted', order)

        flash(f'✅ Venta #{sale.pk} registrada desde el Pedido #{order.pk}.', 'success')
        return redirect(url_for('sales.sale_detail', pk=sale.pk))

    return render_template('orders/order_to_sale_confirm.html', order=order, active_page='orders')


@bp.route('/<int:pk>/delete/', methods=['GET', 'POST'])
@login_required
def order_delete(pk):
    order = Order.query.get_or_404(pk)
    if request.method == 'POST':
        touched = []
        if order.status == 'confirmed':
            for item in order.items:
                item.product.stock_quantity += item.quantity
                touched.append(item.product)
        db.session.delete(order)
        db.session.commit()
        for p in touched:
            emit_stock_changed(p)
        flash(f'Pedido #{pk} eliminado.', 'success')
        return redirect(url_for('orders.order_list'))
    return render_template('orders/order_delete_confirm.html', order=order, active_page='orders')


@bp.route('/<int:pk>/cancel/', methods=['GET', 'POST'])
@login_required
def order_cancel(pk):
    order = Order.query.get_or_404(pk)
    if request.method == 'POST':
        if order.status == 'pending':
            order.status = 'cancelled'
            db.session.commit()
            emit_order_event('order_cancelled', order)
            flash(f'Pedido #{order.pk} cancelado.', 'success')
        else:
            flash('Solo los pedidos pendientes se pueden cancelar.', 'warning')
        return redirect(url_for('orders.order_list'))
    return render_template('orders/order_cancel_confirm.html', order=order, active_page='orders')
