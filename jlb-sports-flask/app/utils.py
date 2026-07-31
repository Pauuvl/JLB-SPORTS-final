"""
Utilidades compartidas: formato de pesos colombianos y filtros Jinja2
que reemplazan los template tags personalizados de Django
(inventory/templatetags/jlb_filters.py).
"""
from decimal import Decimal, InvalidOperation
from markupsafe import Markup


def pesos(value):
    """Convierte un número al formato de pesos colombianos. Ej: 500000 -> $500.000"""
    try:
        value = Decimal(str(value))
        if value == value.to_integral_value():
            formatted = f'{int(value):,}'.replace(',', '.')
        else:
            formatted = f'{value:,.0f}'.replace(',', '.')
        return f'${formatted}'
    except (ValueError, TypeError, InvalidOperation):
        return f'${value}'


def pesos_plain(value):
    """Formato de pesos sin símbolo $, para usar en inputs."""
    try:
        value = Decimal(str(value))
        return f'{int(value):,}'.replace(',', '.')
    except (ValueError, TypeError, InvalidOperation):
        return value


def stock_status(product):
    if product.stock_quantity == 0:
        return 'agotado'
    elif product.is_low_stock:
        return 'bajo'
    return 'ok'


def multiply(value, arg):
    try:
        return Decimal(str(value)) * Decimal(str(arg))
    except (ValueError, TypeError, InvalidOperation):
        return 0


def stock_badge(product):
    """Devuelve HTML del badge de estado de stock (equivalente a {% stock_badge %})."""
    if product.stock_quantity == 0:
        html = '<span class="badge-stock agotado">Agotado</span>'
    elif product.is_low_stock:
        html = f'<span class="badge-stock bajo">Stock Bajo ({product.stock_quantity})</span>'
    else:
        html = f'<span class="badge-stock ok">{product.stock_quantity} und.</span>'
    return Markup(html)


def dj_default(value, fallback):
    """Reemplaza el filtro Django `|default:'x'` (Jinja2 ya tiene `default` pero
    con otra sintaxis de llamado); usado en las plantillas convertidas como
    `{{ value|dj_default('info') }}`."""
    return value if value not in (None, '') else fallback


def floatformat(value, decimals=0):
    """Reemplaza el filtro Django |floatformat:N. Seguro ante None/Undefined."""
    try:
        if value is None or value == '':
            return ''
        return f'{float(value):.{int(decimals)}f}'
    except Exception:
        return ''


_MESES_FULL = ['', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
               'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
_MESES_SHORT = ['', 'ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']


def django_date(value, fmt='d/m/Y'):
    """Reemplaza el filtro Django |date:"..." con los códigos usados en
    este proyecto: d, m, Y, H, i, M, F. Los caracteres precedidos por
    '\\' se imprimen literalmente (igual que en Django), permitiendo
    formatos como 'd \\d\\e F \\d\\e Y' -> '29 de julio de 2026'."""
    if not value:
        return ''
    out = []
    i = 0
    while i < len(fmt):
        ch = fmt[i]
        if ch == '\\' and i + 1 < len(fmt):
            out.append(fmt[i + 1])
            i += 2
            continue
        if ch == 'd':
            out.append(f'{value.day:02d}')
        elif ch == 'm':
            out.append(f'{value.month:02d}')
        elif ch == 'Y':
            out.append(str(value.year))
        elif ch == 'H':
            out.append(f'{value.hour:02d}')
        elif ch == 'i':
            out.append(f'{value.minute:02d}')
        elif ch == 'F':
            out.append(_MESES_FULL[value.month])
        elif ch == 'M':
            out.append(_MESES_SHORT[value.month])
        else:
            out.append(ch)
        i += 1
    return ''.join(out)


def truncatechars(value, length):
    value = str(value)
    length = int(length)
    if len(value) <= length:
        return value
    return value[:length - 1] + '…'


def escapejs(value):
    """Escapa un valor para insertarlo de forma segura dentro de comillas
    simples en un atributo onclick="..." (equivalente a Django |escapejs)."""
    if value is None:
        return ''
    value = str(value)
    return (value.replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"')
            .replace('\n', '\\n').replace('\r', '').replace('</', '<\\/'))


def pluralize(count, suffix='s'):
    """Reemplaza el filtro Django |pluralize (por defecto agrega 's')."""
    try:
        return '' if int(count) == 1 else suffix
    except (ValueError, TypeError):
        return suffix


def register_filters(app):
    app.jinja_env.filters['pesos'] = pesos
    app.jinja_env.filters['pesos_plain'] = pesos_plain
    app.jinja_env.filters['stock_status'] = stock_status
    app.jinja_env.filters['multiply'] = multiply
    app.jinja_env.filters['dj_default'] = dj_default
    app.jinja_env.filters['floatformat'] = floatformat
    app.jinja_env.filters['django_date'] = django_date
    app.jinja_env.filters['truncatechars'] = truncatechars
    app.jinja_env.filters['escapejs'] = escapejs
    app.jinja_env.filters['pluralize'] = pluralize
    app.jinja_env.globals['stock_badge'] = stock_badge
