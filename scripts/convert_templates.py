"""
Convierte las plantillas Django (portadas literalmente) a sintaxis
Jinja2/Flask. Se ejecuta una sola vez sobre app/templates/.

Transformaciones:
  - Elimina {% load ... %}
  - {% static 'x' %}                  -> {{ url_for('static', filename='x') }}
  - {% url 'name' %}                  -> {{ url_for('bp.name') }}
  - {% url 'name' obj.pk %}           -> {{ url_for('bp.name', pk=obj.pk) }}
  - {% csrf_token %}                  -> input hidden con csrf_token()
  - get_client_type_display           -> get_client_type_display()
  - get_status_display                -> get_status_display()
"""
import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / 'app' / 'templates'

URL_ENDPOINT_MAP = {
    'dashboard': 'dashboard.dashboard',
    'product_list': 'inventory.product_list',
    'product_create': 'inventory.product_create',
    'product_edit': 'inventory.product_edit',
    'product_delete': 'inventory.product_delete',
    'product_color_stock_api': 'inventory.product_color_stock_api',
    'category_list': 'inventory.category_list',
    'sale_list': 'sales.sale_list',
    'sale_create': 'sales.sale_create',
    'sale_detail': 'sales.sale_detail',
    'sale_cancel': 'sales.sale_cancel',
    'sale_pdf': 'sales.sale_pdf',
    'product_price_api': 'sales.get_product_price',
    'client_list': 'clients.client_list',
    'client_create': 'clients.client_create',
    'client_detail': 'clients.client_detail',
    'client_edit': 'clients.client_edit',
    'client_delete': 'clients.client_delete',
    'order_list': 'orders.order_list',
    'order_create': 'orders.order_create',
    'order_detail': 'orders.order_detail',
    'order_confirm': 'orders.order_confirm',
    'order_to_sale': 'orders.order_to_sale',
    'order_delete': 'orders.order_delete',
    'order_cancel': 'orders.order_cancel',
    'pricing_overview': 'pricing.pricing_overview',
    'price_list_create': 'pricing.price_list_create',
    'price_list_detail': 'pricing.price_list_detail',
    'add_price_list_item': 'pricing.add_price_list_item',
    'quote_list': 'quotes.quote_list',
    'quote_create': 'quotes.quote_create',
    'quote_detail': 'quotes.quote_detail',
    'quote_status': 'quotes.quote_status',
    'quote_delete': 'quotes.quote_delete',
    'quote_pdf': 'quotes.quote_pdf',
    'login': 'auth.login',
    'logout': 'auth.logout',
}

URL_NO_ARG_RE = re.compile(r"{%\s*url\s+'(\w+)'\s*%}")
URL_ONE_ARG_RE = re.compile(r"{%\s*url\s+'(\w+)'\s+([\w\.]+)\s*%}")
STATIC_RE = re.compile(r"{%\s*static\s+'([^']+)'\s*%}")
LOAD_RE = re.compile(r"^\s*{%\s*load\s+[^%]*%}\s*\n?", re.MULTILINE)
CSRF_RE = re.compile(r"{%\s*csrf_token\s*%}")
DISPLAY_RE = re.compile(r"(get_(?:client_type|status)_display)(?!\()")


def convert_text(text):
    text = LOAD_RE.sub('', text)
    text = STATIC_RE.sub(lambda m: "{{ url_for('static', filename='%s') }}" % m.group(1), text)

    def _url_one_arg(m):
        name, arg = m.group(1), m.group(2)
        endpoint = URL_ENDPOINT_MAP.get(name, name)
        return "{{ url_for('%s', pk=%s) }}" % (endpoint, arg)

    text = URL_ONE_ARG_RE.sub(_url_one_arg, text)
    text = URL_NO_ARG_RE.sub(lambda m: "{{ url_for('%s') }}" % URL_ENDPOINT_MAP.get(m.group(1), m.group(1)), text)
    text = CSRF_RE.sub('<input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>', text)
    text = DISPLAY_RE.sub(r'\1()', text)
    return text


def main():
    count = 0
    for path in TEMPLATES_DIR.rglob('*.html'):
        original = path.read_text(encoding='utf-8')
        converted = convert_text(original)
        if converted != original:
            path.write_text(converted, encoding='utf-8')
            count += 1
    print(f'Plantillas convertidas: {count}')


if __name__ == '__main__':
    main()
