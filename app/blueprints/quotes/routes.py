import json
from decimal import Decimal

from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from flask_login import login_required
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import Quote, QuoteItem, Product, Client
from app.pdf import generate_quote_pdf

bp = Blueprint('quotes', __name__)


def _build_products_json(products):
    data = [{'id': p.pk, 'nombre': p.name, 'codigo': p.codigo or '',
             'precio': float(p.sale_price), 'stock': p.stock_quantity} for p in products]
    return json.dumps(data, ensure_ascii=False)


@bp.route('/')
@login_required
def quote_list():
    quotes = Quote.query.order_by(Quote.created_at.desc()).all()
    return render_template('quotes/quote_list.html', quotes=quotes, active_page='quotes')


@bp.route('/new/', methods=['GET', 'POST'])
@login_required
def quote_create():
    products = Product.query.options(selectinload(Product.stocks)).order_by(Product.name).all()
    clients = Client.query.order_by(Client.name).all()

    if request.method == 'POST':
        client_id = request.form.get('client') or None
        client_name = request.form.get('client_name', '').strip()
        notes = request.form.get('notes', '')
        valid_days = request.form.get('valid_days', 15)
        discount_pct = request.form.get('discount_percent', '0') or '0'
        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')
        prices = request.form.getlist('unit_price[]')
        descs = request.form.getlist('description[]')

        if not product_ids:
            flash('Debe agregar al menos un producto.', 'error')
            return render_template('quotes/quote_form.html', products=products, clients=clients,
                                    products_json=_build_products_json(products), active_page='quotes')

        try:
            discount = Decimal(str(discount_pct))
            if discount < 0 or discount > 100:
                discount = Decimal('0')
        except Exception:
            discount = Decimal('0')

        client = Client.query.get(client_id) if client_id else None

        quote = Quote(client=client, client_name=(client_name if not client else ''), notes=notes,
                       valid_days=valid_days, discount_applied=discount)
        db.session.add(quote)
        db.session.flush()

        for pid, qty, price, desc in zip(product_ids, quantities, prices, descs):
            product = Product.query.get(pid) if pid else None
            db.session.add(QuoteItem(
                quote=quote, product=product,
                description=desc or (product.name if product else ''),
                quantity=int(qty), unit_price=Decimal(price),
            ))

        db.session.flush()
        quote.calculate_total()
        db.session.commit()

        flash(f'Cotización #{quote.pk} creada.', 'success')
        return redirect(url_for('quotes.quote_detail', pk=quote.pk))

    return render_template('quotes/quote_form.html', products=products, clients=clients,
                            products_json=_build_products_json(products), active_page='quotes')


@bp.route('/<int:pk>/')
@login_required
def quote_detail(pk):
    quote = Quote.query.get_or_404(pk)
    return render_template('quotes/quote_detail.html', quote=quote, active_page='quotes')


@bp.route('/<int:pk>/status/', methods=['POST'])
@login_required
def quote_status(pk):
    quote = Quote.query.get_or_404(pk)
    new_status = request.form.get('status')
    if new_status in ['draft', 'sent', 'accepted', 'rejected']:
        quote.status = new_status
        db.session.commit()
        flash(f'Cotización #{quote.pk} marcada como {quote.get_status_display()}.', 'success')
    return redirect(url_for('quotes.quote_detail', pk=pk))


@bp.route('/<int:pk>/delete/', methods=['GET', 'POST'])
@login_required
def quote_delete(pk):
    quote = Quote.query.get_or_404(pk)
    if request.method == 'POST':
        db.session.delete(quote)
        db.session.commit()
        flash(f'Cotización #{pk} eliminada.', 'success')
        return redirect(url_for('quotes.quote_list'))
    return render_template('quotes/quote_delete_confirm.html', quote=quote, active_page='quotes')


@bp.route('/<int:pk>/pdf/')
@login_required
def quote_pdf(pk):
    quote = Quote.query.get_or_404(pk)
    pdf_bytes = generate_quote_pdf(quote)
    return Response(pdf_bytes, mimetype='application/pdf',
                     headers={'Content-Disposition': f'inline; filename="cotizacion_{quote.pk}.pdf"'})
