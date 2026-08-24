import json
from decimal import Decimal

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import login_required
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import Sale, SaleItem, Product, ProductStock, Client
from app.pdf import generate_sale_pdf
from app.sockets import emit_sale_created, emit_sale_cancelled, emit_stock_changed

bp = Blueprint('sales', __name__)


def _fmt_pesos(value):
    try:
        val = int(Decimal(str(value)))
        return f'${val:,}'.replace(',', '.')
    except Exception:
        return f'${value}'


def _build_products_json(products):
    data = []
    for p in products:
        stock_detail = [{'talla': s.talla, 'color': s.color, 'stock': s.stock} for s in p.stocks]
        data.append({
            'id': p.pk, 'nombre': p.name, 'codigo': p.codigo or '',
            'precio': float(p.sale_price), 'stock': p.stock_quantity,
            'tallas': p.get_tallas_lista(), 'detalle_stock': stock_detail,
        })
    return json.dumps(data, ensure_ascii=False)


@bp.route('/')
@login_required
def sale_list():
    sales = Sale.query.order_by(Sale.created_at.desc()).all()
    total_completadas = sum((s.total_amount for s in sales if s.status == 'completed'), Decimal('0'))
    return render_template('sales/sale_list.html', sales=sales, total_completadas=total_completadas,
                            active_page='sales')


@bp.route('/new/', methods=['GET', 'POST'])
@login_required
def sale_create():
    products = Product.query.options(selectinload(Product.stocks)).order_by(Product.name).all()
    clients = Client.query.order_by(Client.name).all()

    if request.method == 'POST':
        client_id = request.form.get('client') or None
        client_name = request.form.get('client_name', '').strip()
        vendedor = request.form.get('vendedor', '').strip()
        notes = request.form.get('notes', '')
        discount_pct = request.form.get('discount_percent', '0') or '0'
        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')
        tallas = request.form.getlist('talla_vendida[]')
        colores = request.form.getlist('color_vendido[]')

        def _render_form_error():
            return render_template('sales/sale_form.html', products=products, clients=clients,
                                    products_json=_build_products_json(products), active_page='sales')

        if not product_ids:
            flash('Debe agregar al menos un producto a la venta.', 'error')
            return _render_form_error()

        client = Client.query.get(client_id) if client_id else None
        if not client and not client_name:
            client_name = 'Mostrador'

        try:
            discount = Decimal(str(discount_pct))
            if discount < 0 or discount > 100:
                raise ValueError('El descuento debe estar entre 0% y 100%.')
        except Exception:
            discount = Decimal('0')

        try:
            sale = Sale(client=client, client_name=('' if client else client_name),
                        vendedor=vendedor, notes=notes, discount_applied=discount)
            db.session.add(sale)
            db.session.flush()

            touched_products = []
            for i, (pid, qty) in enumerate(zip(product_ids, quantities)):
                product = Product.query.with_for_update().get(pid)
                if product is None:
                    raise ValueError('Uno de los productos seleccionados no fue encontrado.')
                qty = int(qty)
                talla = tallas[i] if i < len(tallas) else ''
                color = colores[i] if i < len(colores) else ''

                if not talla:
                    raise ValueError(f'Debe seleccionar la talla vendida para "{product.name}".')

                stock_row = ProductStock.query.with_for_update().filter_by(
                    product_id=product.id, talla=talla, color=color
                ).first()
                if stock_row is None:
                    raise ValueError(
                        f'La combinación talla "{talla}" / color "{color or "—"}" '
                        f'no está registrada para "{product.name}".'
                    )
                if stock_row.stock < qty:
                    raise ValueError(
                        f'Stock insuficiente para "{product.name}" (talla {talla}, {color or "sin color"}). '
                        f'Disponible: {stock_row.stock}, Solicitado: {qty}'
                    )

                unit_price = Decimal(str(product.sale_price))
                db.session.add(SaleItem(
                    sale=sale, product=product, quantity=qty,
                    unit_price=unit_price.quantize(Decimal('1')),
                    talla_vendida=talla, color_vendido=color,
                ))

                stock_row.stock -= qty
                product.recalculate_stock_quantity()
                touched_products.append(product)

            db.session.flush()
            sale.calculate_total()
            db.session.commit()

            for p in touched_products:
                emit_stock_changed(p)
            emit_sale_created(sale)

            total_fmt = _fmt_pesos(sale.total_amount)
            flash(f'✅ Venta #{sale.pk} registrada. Total: {total_fmt}', 'success')
            return redirect(url_for('sales.sale_detail', pk=sale.pk))

        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'error')

    return render_template('sales/sale_form.html', products=products, clients=clients,
                            products_json=_build_products_json(products), active_page='sales')


@bp.route('/<int:pk>/')
@login_required
def sale_detail(pk):
    sale = Sale.query.get_or_404(pk)
    return render_template('sales/sale_detail.html', sale=sale, active_page='sales')


@bp.route('/<int:pk>/cancel/', methods=['GET', 'POST'])
@login_required
def sale_cancel(pk):
    sale = Sale.query.get_or_404(pk)
    if request.method == 'POST':
        if sale.status == 'completed':
            touched = []
            for item in sale.items:
                stock_row = ProductStock.query.filter_by(
                    product_id=item.product_id, talla=item.talla_vendida, color=item.color_vendido
                ).first()
                if stock_row:
                    stock_row.stock += item.quantity
                else:
                    # La combinación fue borrada del catálogo después de la venta;
                    # se recrea para no perder el stock devuelto.
                    stock_row = ProductStock(product_id=item.product_id, talla=item.talla_vendida,
                                              color=item.color_vendido, stock=item.quantity)
                    db.session.add(stock_row)
                item.product.recalculate_stock_quantity()
                touched.append(item.product)
            sale.status = 'cancelled'
            db.session.commit()
            for p in touched:
                emit_stock_changed(p)
            emit_sale_cancelled(sale)
            flash(f'Venta #{sale.pk} anulada. Stock restaurado.', 'success')
        else:
            flash('Esta venta ya fue anulada.', 'warning')
        return redirect(url_for('sales.sale_list'))
    return render_template('sales/sale_cancel_confirm.html', sale=sale, active_page='sales')


@bp.route('/<int:pk>/pdf/')
@login_required
def sale_pdf(pk):
    sale = Sale.query.get_or_404(pk)
    pdf_bytes = generate_sale_pdf(sale)
    return Response(pdf_bytes, mimetype='application/pdf',
                     headers={'Content-Disposition': f'inline; filename="factura_{sale.pk}.pdf"'})


@bp.route('/api/product-price/')
@login_required
def get_product_price():
    product_id = request.args.get('product_id')
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'No encontrado'}), 404
    stock_detail = [{'talla': s.talla, 'color': s.color, 'stock': s.stock} for s in product.stocks]
    return jsonify({
        'price': int(round(float(product.sale_price))),
        'stock': product.stock_quantity,
        'name': product.name,
        'codigo': product.codigo,
        'tallas': product.get_tallas_lista(),
        'detalle_stock': stock_detail,
        'status': 'agotado' if product.stock_quantity == 0 else ('bajo' if product.is_low_stock else 'ok'),
    })
