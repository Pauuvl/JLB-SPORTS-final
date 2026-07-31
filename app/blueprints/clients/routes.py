from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import or_

from app.extensions import db
from app.models import Client, Sale, CLIENT_TYPES

bp = Blueprint('clients', __name__)


def _save_client_from_form(client, form):
    client.name = form.get('name', '').strip()
    client.cedula = form.get('cedula', '').strip()
    client.client_type = form.get('client_type', 'regular')
    client.email = form.get('email', '')
    client.phone = form.get('phone', '')
    client.municipio = form.get('municipio', '').strip()
    client.address = form.get('address', '')
    client.discount_percent = form.get('discount_percent') or 0
    client.notes = form.get('notes', '')
    return client


@bp.route('/')
@login_required
def client_list():
    query = request.args.get('q', '')
    client_type = request.args.get('type', '')
    clients_q = Client.query

    if query:
        like = f'%{query}%'
        clients_q = clients_q.filter(or_(Client.name.ilike(like), Client.email.ilike(like), Client.cedula.ilike(like)))
    if client_type:
        clients_q = clients_q.filter(Client.client_type == client_type)

    clients = clients_q.order_by(Client.name).all()
    return render_template('clients/client_list.html', clients=clients, query=query,
                            selected_type=client_type, client_types=CLIENT_TYPES, active_page='clients')


@bp.route('/new/', methods=['GET', 'POST'])
@login_required
def client_create():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('El nombre del cliente es requerido.', 'error')
        else:
            client = _save_client_from_form(Client(), request.form)
            db.session.add(client)
            db.session.commit()
            flash(f'Cliente "{name}" registrado exitosamente.', 'success')
            return redirect(url_for('clients.client_list'))
    return render_template('clients/client_form.html', client=None, client_types=CLIENT_TYPES, active_page='clients')


@bp.route('/<int:pk>/edit/', methods=['GET', 'POST'])
@login_required
def client_edit(pk):
    client = Client.query.get_or_404(pk)
    if request.method == 'POST':
        client = _save_client_from_form(client, request.form)
        db.session.commit()
        flash(f'Cliente "{client.name}" actualizado.', 'success')
        return redirect(url_for('clients.client_detail', pk=pk))
    return render_template('clients/client_form.html', client=client, client_types=CLIENT_TYPES, active_page='clients')


@bp.route('/<int:pk>/delete/', methods=['GET', 'POST'])
@login_required
def client_delete(pk):
    client = Client.query.get_or_404(pk)
    if request.method == 'POST':
        name = client.name
        db.session.delete(client)
        db.session.commit()
        flash(f'Cliente "{name}" eliminado.', 'success')
        return redirect(url_for('clients.client_list'))
    return render_template('clients/client_confirm_delete.html', client=client, active_page='clients')


@bp.route('/<int:pk>/')
@login_required
def client_detail(pk):
    client = Client.query.get_or_404(pk)
    sales = Sale.query.filter_by(client_id=pk).order_by(Sale.created_at.desc()).limit(10).all()
    return render_template('clients/client_detail.html', client=client, sales=sales, active_page='clients')
