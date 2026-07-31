from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from app.extensions import db
from app.models import Product, PriceList, PriceListItem, CLIENT_TYPES

bp = Blueprint('pricing', __name__)


@bp.route('/')
@login_required
def pricing_overview():
    products = Product.query.order_by(Product.name).all()
    price_lists = PriceList.query.filter_by(is_active=True).order_by(PriceList.name).all()
    return render_template('pricing/pricing_overview.html', products=products, price_lists=price_lists,
                            active_page='pricing')


@bp.route('/new/', methods=['GET', 'POST'])
@login_required
def price_list_create():
    if request.method == 'POST':
        name = request.form.get('name')
        client_type = request.form.get('client_type', '')
        description = request.form.get('description', '')
        if name:
            db.session.add(PriceList(name=name, client_type=client_type, description=description))
            db.session.commit()
            flash(f'Lista de precios "{name}" creada.', 'success')
            return redirect(url_for('pricing.pricing_overview'))
    return render_template('pricing/price_list_form.html', client_types=CLIENT_TYPES, active_page='pricing')


@bp.route('/<int:pk>/')
@login_required
def price_list_detail(pk):
    price_list = PriceList.query.get_or_404(pk)
    products = Product.query.order_by(Product.name).all()
    return render_template('pricing/price_list_detail.html', price_list=price_list, items=price_list.items,
                            products=products, active_page='pricing')


@bp.route('/<int:pk>/add-item/', methods=['POST'])
@login_required
def add_price_list_item(pk):
    price_list = PriceList.query.get_or_404(pk)
    product_id = request.form.get('product')
    custom_price = request.form.get('custom_price')
    if product_id and custom_price:
        item = PriceListItem.query.filter_by(price_list_id=pk, product_id=product_id).first()
        if item:
            item.custom_price = custom_price
        else:
            db.session.add(PriceListItem(price_list_id=pk, product_id=product_id, custom_price=custom_price))
        db.session.commit()
        flash('Precio actualizado.', 'success')
    return redirect(url_for('pricing.price_list_detail', pk=pk))
