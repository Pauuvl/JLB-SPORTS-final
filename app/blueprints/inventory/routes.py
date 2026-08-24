from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from sqlalchemy import or_, func, and_
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import Product, Category, ProductStock, parse_decimal
from app.sockets import emit_product_created, emit_product_updated, emit_product_deleted

bp = Blueprint('inventory', __name__)


def _save_product_stock(product, tallas, colores, cantidades):
    """Sincroniza las filas talla+color+stock desde el formulario.

    Cada índice i de las tres listas representa una combinación
    (talla, color, stock). Se actualiza lo existente, se crean las
    combinaciones nuevas y se eliminan las que ya no vienen en el form.
    """
    kept_keys = set()
    for talla, color, cantidad in zip(tallas, colores, cantidades):
        talla = talla.strip()
        color = color.strip()
        if not talla:
            continue
        kept_keys.add((talla, color))

    for row in list(product.stocks):
        if (row.talla, row.color) not in kept_keys:
            db.session.delete(row)

    existing = {(row.talla, row.color): row for row in product.stocks}
    for talla, color, cantidad in zip(tallas, colores, cantidades):
        talla = talla.strip()
        color = color.strip()
        if not talla:
            continue
        try:
            stock_val = int(cantidad)
        except (ValueError, TypeError):
            stock_val = 0
        row = existing.get((talla, color))
        if not row:
            row = ProductStock(product=product, talla=talla, color=color)
            db.session.add(row)
            existing[(talla, color)] = row
        row.stock = stock_val

    db.session.flush()
    product.recalculate_stock_quantity()


@bp.route('/products/')
@login_required
def product_list():
    query = request.args.get('q', '')
    category_id = request.args.get('category', '')
    stock_filter = request.args.get('stock', '')
    marca_filter = request.args.get('marca', '')
    talla_filter = request.args.get('talla', '')

    products_q = Product.query

    if query:
        like = f'%{query}%'
        products_q = products_q.filter(or_(
            Product.name.ilike(like), Product.codigo.ilike(like),
            Product.description.ilike(like), Product.marca.ilike(like),
        ))
    if category_id:
        products_q = products_q.filter(Product.category_id == category_id)
    if marca_filter:
        products_q = products_q.filter(Product.marca == marca_filter)
    if talla_filter:
        products_q = products_q.filter(Product.stocks.any(ProductStock.talla == talla_filter))
    if stock_filter == 'bajo':
        products_q = products_q.filter(Product.stock_quantity > 0, Product.stock_quantity <= Product.min_stock)
    elif stock_filter == 'agotado':
        products_q = products_q.filter(Product.stock_quantity == 0)
    elif stock_filter == 'ok':
        products_q = products_q.filter(Product.stock_quantity > Product.min_stock)

    products = (
        products_q.options(selectinload(Product.stocks))
        .order_by(Product.name).all()
    )
    categories = Category.query.order_by(Category.name).all()

    marcas = [r[0] for r in db.session.query(Product.marca).filter(
        Product.marca.isnot(None), Product.marca != ''
    ).distinct().order_by(Product.marca).all()]
    tallas = [r[0] for r in db.session.query(ProductStock.talla).filter(
        ProductStock.talla.isnot(None), ProductStock.talla != ''
    ).distinct().order_by(ProductStock.talla).all()]

    counts_row = db.session.query(
        func.count(Product.id),
        func.coalesce(func.sum(func.cast(
            and_(Product.stock_quantity > 0, Product.stock_quantity <= Product.min_stock), db.Integer
        )), 0),
        func.coalesce(func.sum(func.cast(Product.stock_quantity == 0, db.Integer)), 0),
    ).first()
    total_count, low_count, out_count = counts_row

    return render_template('inventory/product_list.html', products=products, categories=categories,
                            query=query, selected_category=category_id, stock_filter=stock_filter,
                            marcas=marcas, tallas=tallas, selected_marca=marca_filter, selected_talla=talla_filter,
                            total_count=total_count, low_count=low_count, out_count=out_count,
                            active_page='inventory')


@bp.route('/products/new/', methods=['GET', 'POST'])
@login_required
def product_create():
    categories = Category.query.order_by(Category.name).all()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        category_id = request.form.get('category') or None
        marca = request.form.get('marca', '').strip()
        cost_price = request.form.get('cost_price', '').strip()
        sale_price = request.form.get('sale_price', '').strip()
        min_stock = request.form.get('min_stock', '5').strip() or '5'
        description = request.form.get('description', '')

        stock_tallas = request.form.getlist('stock_talla[]')
        stock_colores = request.form.getlist('stock_color[]')
        stock_cantidades = request.form.getlist('stock_cantidad[]')

        if not all([name, cost_price, sale_price]):
            flash('Complete todos los campos requeridos: nombre, costo y precio de venta.', 'error')
        elif not any(t.strip() for t in stock_tallas):
            flash('Agrega al menos una talla con su stock.', 'error')
        else:
            try:
                product = Product(
                    name=name, category_id=category_id,
                    marca=marca,
                    cost_price=parse_decimal(cost_price, 'Precio de Costo'),
                    sale_price=parse_decimal(sale_price, 'Precio de Venta'),
                    min_stock=int(min_stock),
                    description=description,
                )
                db.session.add(product)
                db.session.flush()  # asigna el id autoincremental

                # Código automático: jlb000001, jlb000002, ... a partir del id.
                product.codigo = f'jlb{product.id:06d}'

                _save_product_stock(product, stock_tallas, stock_colores, stock_cantidades)

                db.session.commit()
                emit_product_created(product)
                flash(f'Producto "{name}" creado exitosamente con código {product.codigo}.', 'success')
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
        min_stock = request.form.get('min_stock', '5').strip() or '5'

        stock_tallas = request.form.getlist('stock_talla[]')
        stock_colores = request.form.getlist('stock_color[]')
        stock_cantidades = request.form.getlist('stock_cantidad[]')

        if not all([name, cost_price, sale_price]):
            flash('Complete todos los campos requeridos: nombre, costo y precio de venta.', 'error')
        elif not any(t.strip() for t in stock_tallas):
            flash('Agrega al menos una talla con su stock.', 'error')
        else:
            try:
                product.name = name
                product.category_id = request.form.get('category') or None
                product.marca = request.form.get('marca', '').strip()
                product.cost_price = parse_decimal(cost_price, 'Precio de Costo')
                product.sale_price = parse_decimal(sale_price, 'Precio de Venta')
                product.min_stock = int(min_stock)
                product.description = request.form.get('description', '')
                if not product.codigo:
                    # Productos migrados de antes que quedaron sin código automático.
                    product.codigo = f'jlb{product.id:06d}'

                _save_product_stock(product, stock_tallas, stock_colores, stock_cantidades)

                db.session.commit()
                emit_product_updated(product)
                flash(f'Producto "{product.name}" actualizado correctamente.', 'success')
                return redirect(url_for('inventory.product_list'))
            except ValueError as e:
                db.session.rollback()
                flash(str(e), 'error')

    stock_rows = list(product.stocks)
    return render_template('inventory/product_form.html', product=product, categories=categories,
                            stock_rows=stock_rows, active_page='inventory')


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
    """Retorna el detalle de stock por talla/color de un producto (JSON)."""
    product = Product.query.get_or_404(pk)
    stock = [{'talla': s.talla, 'color': s.color, 'stock': s.stock} for s in product.stocks]
    return jsonify({'stock': stock, 'product_name': product.name})
