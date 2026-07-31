from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from sqlalchemy import or_

from app.extensions import db
from app.models import Product, Category, ProductColorStock, parse_decimal
from app.sockets import emit_product_created, emit_product_updated, emit_product_deleted

bp = Blueprint('inventory', __name__)


def _save_product_colors(product, color_names, color_stocks):
    """Sincroniza los registros de stock por color desde el formulario."""
    kept = {n.strip() for n in color_names if n.strip()}
    for cs in list(product.color_stocks):
        if cs.color not in kept:
            db.session.delete(cs)

    existing = {cs.color: cs for cs in product.color_stocks}
    for name, stock in zip(color_names, color_stocks):
        name = name.strip()
        if not name:
            continue
        try:
            stock_val = int(stock)
        except (ValueError, TypeError):
            stock_val = 0
        obj = existing.get(name)
        if not obj:
            obj = ProductColorStock(product=product, color=name)
            db.session.add(obj)
        obj.stock = stock_val


@bp.route('/products/')
@login_required
def product_list():
    query = request.args.get('q', '')
    category_id = request.args.get('category', '')
    stock_filter = request.args.get('stock', '')

    products_q = Product.query

    if query:
        like = f'%{query}%'
        products_q = products_q.filter(or_(
            Product.name.ilike(like), Product.codigo.ilike(like),
            Product.description.ilike(like), Product.marca.ilike(like),
            Product.talla.ilike(like), Product.color.ilike(like),
        ))
    if category_id:
        products_q = products_q.filter(Product.category_id == category_id)
    if stock_filter == 'bajo':
        products_q = products_q.filter(Product.stock_quantity > 0, Product.stock_quantity <= Product.min_stock)
    elif stock_filter == 'agotado':
        products_q = products_q.filter(Product.stock_quantity == 0)
    elif stock_filter == 'ok':
        products_q = products_q.filter(Product.stock_quantity > Product.min_stock)

    products = products_q.order_by(Product.name).all()
    categories = Category.query.order_by(Category.name).all()
    total_count = Product.query.count()
    low_count = Product.query.filter(Product.stock_quantity > 0, Product.stock_quantity <= Product.min_stock).count()
    out_count = Product.query.filter(Product.stock_quantity == 0).count()

    return render_template('inventory/product_list.html', products=products, categories=categories,
                            query=query, selected_category=category_id, stock_filter=stock_filter,
                            total_count=total_count, low_count=low_count, out_count=out_count,
                            active_page='inventory')


@bp.route('/products/new/', methods=['GET', 'POST'])
@login_required
def product_create():
    categories = Category.query.order_by(Category.name).all()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        codigo = request.form.get('codigo', '').strip() or None
        category_id = request.form.get('category') or None
        marca = request.form.get('marca', '').strip()
        talla = request.form.get('talla', '').strip()
        color = request.form.get('color', '').strip()
        cost_price = request.form.get('cost_price', '').strip()
        sale_price = request.form.get('sale_price', '').strip()
        stock_quantity = request.form.get('stock_quantity', '').strip()
        min_stock = request.form.get('min_stock', '5').strip() or '5'
        description = request.form.get('description', '')

        if not all([name, cost_price, sale_price, stock_quantity]):
            flash('Complete todos los campos requeridos: nombre, costo, precio de venta y stock.', 'error')
        else:
            try:
                product = Product(
                    name=name, codigo=codigo, category_id=category_id,
                    marca=marca, talla=talla, color=color,
                    cost_price=parse_decimal(cost_price, 'Precio de Costo'),
                    sale_price=parse_decimal(sale_price, 'Precio de Venta'),
                    stock_quantity=int(stock_quantity),
                    min_stock=int(min_stock),
                    description=description,
                )
                db.session.add(product)
                db.session.flush()

                color_names = request.form.getlist('color_nombre[]')
                color_stocks = request.form.getlist('color_stock[]')
                _save_product_colors(product, color_names, color_stocks)

                db.session.commit()
                emit_product_created(product)
                flash(f'Producto "{name}" creado exitosamente.', 'success')
                return redirect(url_for('inventory.product_list'))
            except ValueError as e:
                db.session.rollback()
                flash(str(e), 'error')

    return render_template('inventory/product_form.html', product=None, categories=categories, active_page='inventory')


@bp.route('/products/<int:pk>/edit/', methods=['GET', 'POST'])
@login_required
def product_edit(pk):
    product = Product.query.get_or_404(pk)
    categories = Category.query.order_by(Category.name).all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        cost_price = request.form.get('cost_price', '').strip()
        sale_price = request.form.get('sale_price', '').strip()
        stock_quantity = request.form.get('stock_quantity', '').strip()
        min_stock = request.form.get('min_stock', '5').strip() or '5'

        if not all([name, cost_price, sale_price, stock_quantity]):
            flash('Complete todos los campos requeridos: nombre, costo, precio de venta y stock.', 'error')
        else:
            try:
                product.name = name
                product.codigo = request.form.get('codigo', '').strip() or None
                product.category_id = request.form.get('category') or None
                product.marca = request.form.get('marca', '').strip()
                product.talla = request.form.get('talla', '').strip()
                product.color = request.form.get('color', '').strip()
                product.cost_price = parse_decimal(cost_price, 'Precio de Costo')
                product.sale_price = parse_decimal(sale_price, 'Precio de Venta')
                product.stock_quantity = int(stock_quantity)
                product.min_stock = int(min_stock)
                product.description = request.form.get('description', '')

                color_names = request.form.getlist('color_nombre[]')
                color_stocks = request.form.getlist('color_stock[]')
                _save_product_colors(product, color_names, color_stocks)

                db.session.commit()
                emit_product_updated(product)
                flash(f'Producto "{product.name}" actualizado correctamente.', 'success')
                return redirect(url_for('inventory.product_list'))
            except ValueError as e:
                db.session.rollback()
                flash(str(e), 'error')

    color_stocks = list(product.color_stocks)
    return render_template('inventory/product_form.html', product=product, categories=categories,
                            color_stocks=color_stocks, active_page='inventory')


@bp.route('/products/<int:pk>/delete/', methods=['GET', 'POST'])
@login_required
def product_delete(pk):
    product = Product.query.get_or_404(pk)
    if request.method == 'POST':
        name = product.name
        pid = product.id
        db.session.delete(product)
        db.session.commit()
        emit_product_deleted(pid, name)
        flash(f'Producto "{name}" eliminado.', 'success')
        return redirect(url_for('inventory.product_list'))
    return render_template('inventory/product_confirm_delete.html', product=product, active_page='inventory')


@bp.route('/categories/', methods=['GET', 'POST'])
@login_required
def category_list():
    if request.method == 'POST':
        action = request.form.get('action', 'create')

        if action == 'create':
            name = request.form.get('name', '').strip()
            if not name:
                flash('El nombre es requerido.', 'error')
            elif Category.query.filter(Category.name.ilike(name)).first():
                flash(f'Ya existe una categoría llamada "{name}".', 'error')
            else:
                db.session.add(Category(name=name, description=request.form.get('description', '')))
                db.session.commit()
                flash(f'Categoría "{name}" creada.', 'success')

        elif action == 'edit':
            cat_id = request.form.get('cat_id')
            name = request.form.get('name', '').strip()
            cat = Category.query.get_or_404(cat_id)
            dup = Category.query.filter(Category.name.ilike(name), Category.id != cat_id).first()
            if dup:
                flash(f'Ya existe una categoría llamada "{name}".', 'error')
            else:
                cat.name = name
                cat.description = request.form.get('description', '')
                db.session.commit()
                flash('Categoría actualizada.', 'success')

        elif action == 'delete':
            cat_id = request.form.get('cat_id')
            cat = Category.query.get_or_404(cat_id)
            for p in cat.products:
                p.category_id = None
            db.session.delete(cat)
            db.session.commit()
            flash('Categoría eliminada.', 'success')

        return redirect(url_for('inventory.category_list'))

    categories = Category.query.order_by(Category.name).all()
    return render_template('inventory/category_list.html', categories=categories, active_page='inventory')


@bp.route('/products/<int:pk>/color-stock/')
@login_required
def product_color_stock_api(pk):
    """Retorna el stock por color de un producto (JSON)."""
    product = Product.query.get_or_404(pk)
    colors = [{'color': cs.color, 'stock': cs.stock} for cs in product.color_stocks]
    return jsonify({'colors': colors, 'product_name': product.name})
