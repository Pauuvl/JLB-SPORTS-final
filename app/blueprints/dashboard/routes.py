from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required
from sqlalchemy import func, and_

from app.extensions import db
from app.models import (Product, Category, Sale, SaleItem, Client, Order, now_co)

bp = Blueprint('dashboard', __name__)


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════
def _period_start(period):
    now = now_co()
    today = datetime(now.year, now.month, now.day)
    if period == 'today':
        return today
    if period == 'week':
        return today - timedelta(days=today.weekday())
    if period == 'month':
        return today.replace(day=1)
    if period == 'year':
        return today.replace(month=1, day=1)
    return None  # 'all'


def _compute_kpis():
    now = now_co()
    today_start = datetime(now.year, now.month, now.day)
    month_start = today_start.replace(day=1)

    # ── Una sola consulta agregada para todo el inventario ──────────
    inv_row = db.session.query(
        func.count(Product.id),
        func.coalesce(func.sum(func.cast(Product.stock_quantity == 0, db.Integer)), 0),
        func.coalesce(func.sum(func.cast(
            and_(Product.stock_quantity > 0, Product.stock_quantity <= Product.min_stock), db.Integer
        )), 0),
        func.coalesce(func.sum(Product.cost_price * Product.stock_quantity), 0),
    ).first()
    total_products, out_of_stock, low_stock_count, total_inventory_value = inv_row

    low_stock_products = Product.query.filter(
        Product.stock_quantity > 0, Product.stock_quantity <= Product.min_stock
    ).order_by(Product.stock_quantity).all()

    # ── Una sola consulta agregada para todas las métricas de ventas ─
    sales_row = db.session.query(
        func.count(Sale.id),
        func.coalesce(func.sum(Sale.total_amount), 0),
        func.coalesce(func.sum(func.cast(Sale.created_at >= today_start, db.Integer)), 0),
        func.coalesce(func.sum(func.cast(Sale.created_at >= month_start, db.Integer)), 0),
        func.coalesce(func.sum(
            func.cast(Sale.created_at >= month_start, db.Integer) * Sale.total_amount
        ), 0),
    ).filter(Sale.status == 'completed').first()
    total_sales, total_revenue, sales_today, sales_month, revenue_month = sales_row

    total_clients = Client.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()
    last_sale = Sale.query.order_by(Sale.created_at.desc()).first()

    return {
        'total_products': total_products,
        'active_products': total_products - out_of_stock,
        'out_of_stock': out_of_stock,
        'low_stock_count': low_stock_count,
        'total_inventory_value': float(total_inventory_value),
        'total_sales': total_sales,
        'total_revenue': float(total_revenue),
        'sales_today': sales_today,
        'sales_month': sales_month,
        'revenue_month': float(revenue_month),
        'total_clients': total_clients,
        'pending_orders': pending_orders,
        'last_sale': {
            'id': last_sale.id,
            'total_amount': float(last_sale.total_amount),
            'created_at': last_sale.created_at.strftime('%d/%m/%Y %H:%M'),
            'client': last_sale.display_client,
        } if last_sale else None,
    }, low_stock_products


@bp.route('/dashboard/')
@bp.route('/')
@login_required
def dashboard():
    kpis, low_stock_products = _compute_kpis()

    recent_sales = Sale.query.order_by(Sale.created_at.desc()).limit(6).all()

    top_products_rows = (
        db.session.query(Product.name, func.sum(SaleItem.quantity).label('total_vendido'))
        .join(SaleItem, SaleItem.product_id == Product.id)
        .group_by(Product.name)
        .order_by(func.sum(SaleItem.quantity).desc())
        .limit(5)
        .all()
    )
    top_products = [{'product__name': r[0], 'total_vendido': r[1]} for r in top_products_rows]

    return render_template('dashboard.html', low_stock_products=low_stock_products,
                            recent_sales=recent_sales,
                            top_products=top_products, active_page='dashboard', **kpis)


@bp.route('/dashboard/api/stats/')
@login_required
def api_stats():
    kpis, _ = _compute_kpis()
    return jsonify(kpis)


@bp.route('/dashboard/api/top-products/')
@login_required
def api_top_products():
    """Top 10 productos más vendidos con cantidad, ingresos, stock y % participación."""
    period = request.args.get('period', 'month')
    start = _period_start(period)

    q = (
        db.session.query(
            Product.id, Product.name,
            func.sum(SaleItem.quantity).label('cantidad'),
            func.sum(SaleItem.quantity * SaleItem.unit_price).label('ingresos'),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.status == 'completed')
    )
    if start:
        q = q.filter(Sale.created_at >= start)

    rows = q.group_by(Product.id, Product.name).order_by(func.sum(SaleItem.quantity).desc()).limit(10).all()

    total_vendido = sum(r.cantidad for r in rows) or 1
    products = Product.query.filter(Product.id.in_([r.id for r in rows])).all()
    stock_by_id = {p.id: p.stock_quantity for p in products}

    result = [{
        'id': r.id,
        'name': r.name,
        'cantidad_vendida': int(r.cantidad),
        'ingresos': float(r.ingresos or 0),
        'stock_restante': stock_by_id.get(r.id, 0),
        'porcentaje': round((r.cantidad / total_vendido) * 100, 1),
    } for r in rows]

    return jsonify({'period': period, 'products': result})


@bp.route('/dashboard/api/charts/')
@login_required
def api_charts():
    """Datos para las gráficas Chart.js del panel de estadísticas."""
    now = now_co()
    today = datetime(now.year, now.month, now.day)

    # ── Ventas de los últimos 14 días: 1 sola consulta, se agrupa en Python ──
    window_start_days = today - timedelta(days=13)
    day_sales = Sale.query.filter(
        Sale.status == 'completed', Sale.created_at >= window_start_days
    ).with_entities(Sale.created_at).all()

    counts_by_day = {}
    for (created_at,) in day_sales:
        key = created_at.date()
        counts_by_day[key] = counts_by_day.get(key, 0) + 1

    days = []
    for i in range(13, -1, -1):
        day = (today - timedelta(days=i)).date()
        days.append({'label': day.strftime('%d/%m'), 'ventas': counts_by_day.get(day, 0)})

    # ── Ingresos de los últimos 12 meses: 1 sola consulta, se agrupa en Python ──
    first_month_start = datetime(today.year, today.month, 1)
    for _ in range(11):
        first_month_start = (first_month_start - timedelta(days=1)).replace(day=1)

    month_sales = Sale.query.filter(
        Sale.status == 'completed', Sale.created_at >= first_month_start
    ).with_entities(Sale.created_at, Sale.total_amount).all()

    agg_by_month = {}
    for created_at, total_amount in month_sales:
        key = (created_at.year, created_at.month)
        rev, cnt = agg_by_month.get(key, (Decimal('0'), 0))
        agg_by_month[key] = (rev + (total_amount or Decimal('0')), cnt + 1)

    months = []
    cursor = first_month_start
    for _ in range(12):
        key = (cursor.year, cursor.month)
        rev, cnt = agg_by_month.get(key, (Decimal('0'), 0))
        months.append({'label': cursor.strftime('%b %Y'), 'ingresos': float(rev), 'ventas': cnt})
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)

    # Productos más vendidos (top 8, histórico)
    top_rows = (
        db.session.query(Product.name, func.sum(SaleItem.quantity).label('cant'))
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.status == 'completed')
        .group_by(Product.name)
        .order_by(func.sum(SaleItem.quantity).desc())
        .limit(8)
        .all()
    )
    top_products = [{'label': r[0], 'value': int(r[1])} for r in top_rows]

    # Categorías con mayores ventas (por ingresos)
    cat_rows = (
        db.session.query(Category.name, func.sum(SaleItem.quantity * SaleItem.unit_price).label('ingresos'))
        .join(Product, Product.category_id == Category.id)
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.status == 'completed')
        .group_by(Category.name)
        .order_by(func.sum(SaleItem.quantity * SaleItem.unit_price).desc())
        .all()
    )
    categories_sales = [{'label': r[0] or 'Sin categoría', 'value': float(r[1] or 0)} for r in cat_rows]

    # Inventario por categoría (unidades en stock)
    inv_rows = (
        db.session.query(Category.name, func.coalesce(func.sum(Product.stock_quantity), 0))
        .outerjoin(Product, Product.category_id == Category.id)
        .group_by(Category.name)
        .all()
    )
    inventory_by_category = [{'label': r[0], 'value': int(r[1])} for r in inv_rows]

    # Productos con bajo stock
    low_stock = Product.query.filter(
        Product.stock_quantity > 0, Product.stock_quantity <= Product.min_stock
    ).order_by(Product.stock_quantity).limit(15).all()
    low_stock_list = [{'name': p.name, 'stock': p.stock_quantity, 'min_stock': p.min_stock} for p in low_stock]

    return jsonify({
        'sales_by_day': days,
        'revenue_by_month': months,
        'top_products': top_products,
        'categories_sales': categories_sales,
        'inventory_by_category': inventory_by_category,
        'low_stock': low_stock_list,
    })


@bp.route('/dashboard/api/alerts/')
@login_required
def api_alerts():
    """Estado actual de alertas (para pintar al cargar la página, además
    de las que llegan en vivo por Socket.IO)."""
    out_of_stock = Product.query.filter(Product.stock_quantity == 0).all()
    low_stock = Product.query.filter(
        Product.stock_quantity > 0, Product.stock_quantity <= Product.min_stock
    ).all()
    return jsonify({
        'out_of_stock': [{'id': p.id, 'name': p.name} for p in out_of_stock],
        'low_stock': [{'id': p.id, 'name': p.name, 'stock_quantity': p.stock_quantity,
                        'min_stock': p.min_stock} for p in low_stock],
    })
