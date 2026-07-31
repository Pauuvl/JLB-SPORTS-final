"""
Generación de PDF con ReportLab — portado sin cambios de diseño desde
sales/views.py y quotes/views.py (Django). Sólo se adaptó el acceso a
datos (SQLAlchemy en vez de ORM Django) y `get_status_display()` que
ya existe como método en los modelos SQLAlchemy.
"""
import io
import os
from decimal import Decimal

from flask import current_app


def _static_path(*parts):
    return os.path.abspath(os.path.join(current_app.root_path, 'static', *parts))


def generate_sale_pdf(sale):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                     Paragraph, Spacer, HRFlowable, Image,
                                     KeepTogether)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                             rightMargin=1.8 * cm, leftMargin=1.8 * cm,
                             topMargin=1.8 * cm, bottomMargin=1.8 * cm)

    ROJO = colors.HexColor('#DC2626')
    NEGRO = colors.HexColor('#111111')
    GRIS = colors.HexColor('#6B7280')
    GRIS_FONDO = colors.HexColor('#F3F4F6')
    GRIS_BORDE = colors.HexColor('#E5E7EB')
    ROJO_LIGHT = colors.HexColor('#FEF2F2')
    BLANCO = colors.white

    s_sub = ParagraphStyle('sub', fontSize=8, textColor=BLANCO, fontName='Helvetica', alignment=TA_RIGHT)
    s_normal = ParagraphStyle('norm', fontSize=9, textColor=GRIS, fontName='Helvetica')
    s_footer = ParagraphStyle('footer', fontSize=7, textColor=GRIS, fontName='Helvetica', alignment=TA_CENTER)
    s_label = ParagraphStyle('label', fontSize=7, textColor=GRIS, fontName='Helvetica-Bold', spaceAfter=1)
    s_value = ParagraphStyle('value', fontSize=9, textColor=NEGRO, fontName='Helvetica')

    elements = []

    logo_path = _static_path('imagenes', 'logo_blanco.png')
    if os.path.exists(logo_path):
        logo_cell = Image(logo_path, width=5.5 * cm, height=1.7 * cm)
    else:
        logo_cell = Paragraph('<font color="white" size="16"><b>JLB SPORTS</b></font>', s_sub)

    estado_txt = sale.get_status_display()

    info_cell = Paragraph(
        f'<font size="14" color="white"><b>FACTURA #{sale.pk}</b></font><br/>'
        f'<font size="8" color="#fca5a5">{sale.created_at.strftime("%d/%m/%Y  %H:%M")}  ·  '
        f'<b>{estado_txt}</b></font>',
        s_sub
    )

    hdr = Table([[logo_cell, info_cell]], colWidths=[10 * cm, 7.4 * cm])
    hdr.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NEGRO),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
        ('LEFTPADDING', (0, 0), (0, -1), 16),
        ('RIGHTPADDING', (-1, 0), (-1, -1), 16),
        ('LINEBELOW', (0, 0), (-1, -1), 3, ROJO),
    ]))
    elements.append(hdr)
    elements.append(Spacer(1, 0.45 * cm))

    client = sale.client

    def info_block(label, value):
        return [Paragraph(label.upper(), s_label), Paragraph(str(value) if value else '—', s_value)]

    if client:
        cli_rows = [
            info_block('Cliente', client.name),
            info_block('Cédula / NIT', client.cedula or None),
            info_block('Teléfono', client.phone or None),
            info_block('Municipio', client.municipio or None),
        ]
        cli_rows = [r for r in cli_rows if r[1].text != '—' or r[0].text == 'CLIENTE']
    else:
        cli_rows = [info_block('Cliente', 'Venta Mostrador')]

    venta_rows = [
        info_block('Fecha', sale.created_at.strftime('%d/%m/%Y')),
        info_block('Hora', sale.created_at.strftime('%H:%M')),
        info_block('Vendedor', '—'),
    ]

    cli_flat = list(cli_rows)
    venta_flat = list(venta_rows)
    while len(cli_flat) < len(venta_flat):
        cli_flat.append([Paragraph('', s_label), Paragraph('', s_value)])
    while len(venta_flat) < len(cli_flat):
        venta_flat.append([Paragraph('', s_label), Paragraph('', s_value)])

    info_rows = [[cli_flat[i][0], cli_flat[i][1], venta_flat[i][0], venta_flat[i][1]]
                 for i in range(len(cli_flat))]

    info_tbl = Table(info_rows, colWidths=[2.8 * cm, 6 * cm, 2.8 * cm, 5.8 * cm])
    info_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), GRIS_FONDO),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('LINEAFTER', (1, 0), (1, -1), 0.5, GRIS_BORDE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(info_tbl)
    elements.append(Spacer(1, 0.45 * cm))

    col_headers = ['#', 'Código', 'Producto', 'Color', 'Cant.', 'Precio Unit.', 'Subtotal']
    rows = [col_headers]
    subtotal_sum = Decimal('0')

    for i, item in enumerate(sale.items, 1):
        subtotal_sum += item.subtotal
        rows.append([
            str(i),
            item.product.codigo or '—',
            item.product.name,
            item.color_vendido or '—',
            str(item.quantity),
            f'${int(item.unit_price):,}'.replace(',', '.'),
            f'${int(item.subtotal):,}'.replace(',', '.'),
        ])

    col_w = [0.7 * cm, 2.2 * cm, 5.8 * cm, 2.3 * cm, 1.3 * cm, 2.6 * cm, 2.5 * cm]
    prod_tbl = Table(rows, colWidths=col_w, repeatRows=1)
    prod_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NEGRO),
        ('TEXTCOLOR', (0, 0), (-1, 0), BLANCO),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 8),
        ('LINEBELOW', (0, 0), (-1, 0), 2, ROJO),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 8),
        ('TEXTCOLOR', (0, 1), (-1, -1), NEGRO),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [BLANCO, GRIS_FONDO]),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (4, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, GRIS_BORDE),
    ]))
    elements.append(prod_tbl)
    elements.append(Spacer(1, 0.3 * cm))

    totals = [['Subtotal:', f'${int(subtotal_sum):,}'.replace(',', '.')]]
    if sale.discount_applied:
        desc_monto = subtotal_sum - sale.total_amount
        totals.append([f'Descuento ({sale.discount_applied}%):', f'-${int(desc_monto):,}'.replace(',', '.')])
    totals.append(['TOTAL A PAGAR:', f'${int(sale.total_amount):,}'.replace(',', '.')])

    tot_tbl = Table(totals, colWidths=[13.9 * cm, 3.5 * cm])
    tot_tbl.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -2), 'Helvetica', 9),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 13),
        ('TEXTCOLOR', (0, 0), (-1, -2), GRIS),
        ('TEXTCOLOR', (0, -1), (0, -1), NEGRO),
        ('TEXTCOLOR', (-1, -1), (-1, -1), ROJO),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('BACKGROUND', (0, -1), (-1, -1), ROJO_LIGHT),
        ('LINEABOVE', (0, -1), (-1, -1), 2, ROJO),
        ('RIGHTPADDING', (-1, 0), (-1, -1), 0),
    ]))
    elements.append(KeepTogether([tot_tbl]))

    if sale.notes:
        elements.append(Spacer(1, 0.4 * cm))
        elements.append(HRFlowable(width='100%', thickness=0.5, color=GRIS_BORDE))
        elements.append(Spacer(1, 0.2 * cm))
        elements.append(Paragraph(f'<b>Observaciones:</b> {sale.notes}', s_normal))

    elements.append(Spacer(1, 0.7 * cm))
    elements.append(HRFlowable(width='100%', thickness=1, color=ROJO))
    elements.append(Spacer(1, 0.2 * cm))
    elements.append(Paragraph('JLB Sports  ·  Sistema de Gestión Comercial  ·  ¡Gracias por su compra!', s_footer))

    doc.build(elements)
    return buffer.getvalue()


def generate_quote_pdf(quote):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, Image
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                             rightMargin=2 * cm, leftMargin=2 * cm,
                             topMargin=2 * cm, bottomMargin=2 * cm)

    rojo = colors.HexColor('#DC2626')
    negro = colors.HexColor('#111111')
    gris = colors.HexColor('#6B7280')
    gris_fondo = colors.HexColor('#F3F4F6')
    rojo_fondo = colors.HexColor('#FEF2F2')

    sub_style = ParagraphStyle('sub', fontSize=9, textColor=colors.white, fontName='Helvetica', alignment=TA_CENTER)
    normal_style = ParagraphStyle('normal', fontSize=9, textColor=gris, fontName='Helvetica')

    elements = []

    logo_path = _static_path('imagenes', 'logo_blanco.png')
    if os.path.exists(logo_path):
        logo_cell = Image(logo_path, width=5 * cm, height=1.6 * cm)
    else:
        logo_cell = Paragraph('<font color="white"><b>JLB SPORTS</b></font>', sub_style)

    quote_info = Paragraph(
        f'<font color="white"><b>COTIZACIÓN #{quote.pk}</b></font><br/>'
        f'<font size="8" color="#fca5a5">{quote.created_at.strftime("%d/%m/%Y")} · Válida {quote.valid_days} días</font>',
        sub_style
    )

    header_table = Table([[logo_cell, quote_info]], colWidths=[11 * cm, 6 * cm])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), negro),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
        ('LEFTPADDING', (0, 0), (0, -1), 16),
        ('RIGHTPADDING', (-1, 0), (-1, -1), 16),
        ('LINEBELOW', (0, 0), (-1, 0), 3, rojo),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.5 * cm))

    client = quote.client
    display_name = client.name if client else (quote.client_name or 'Sin cliente')
    client_info = [['Cliente:', display_name]]
    if client:
        if client.cedula:
            client_info.append(['Cédula / NIT:', client.cedula])
        if client.phone:
            client_info.append(['Teléfono:', client.phone])
        if client.email:
            client_info.append(['Correo:', client.email])
        if client.municipio:
            client_info.append(['Municipio:', client.municipio])

    client_table = Table(client_info, colWidths=[4 * cm, 13 * cm])
    client_table.setStyle(TableStyle([
        ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 9),
        ('FONT', (1, 0), (1, -1), 'Helvetica', 9),
        ('TEXTCOLOR', (0, 0), (0, -1), negro),
        ('TEXTCOLOR', (1, 0), (1, -1), gris),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('BACKGROUND', (0, 0), (-1, -1), gris_fondo),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(client_table)
    elements.append(Spacer(1, 0.4 * cm))

    items_data = [['Descripción', 'Cant.', 'Precio Unit.', 'Subtotal']]
    subtotal_sum = Decimal('0')
    for item in quote.items:
        subtotal_sum += item.subtotal
        items_data.append([
            item.description,
            str(item.quantity),
            f'${int(item.unit_price):,}'.replace(',', '.'),
            f'${int(item.subtotal):,}'.replace(',', '.'),
        ])

    items_table = Table(items_data, colWidths=[9.5 * cm, 2 * cm, 3.5 * cm, 2 * cm])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), negro),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 8),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 8),
        ('TEXTCOLOR', (0, 1), (-1, -1), negro),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, gris_fondo]),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('LINEBELOW', (0, 0), (-1, 0), 2, rojo),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 0.3 * cm))

    totals_data = [['Subtotal:', f'${int(subtotal_sum):,}'.replace(',', '.')]]
    if quote.discount_applied:
        totals_data.append([f'Descuento ({quote.discount_applied}%):',
                             f'-${int(subtotal_sum - quote.total_amount):,}'.replace(',', '.')])
    totals_data.append(['TOTAL:', f'${int(quote.total_amount):,}'.replace(',', '.')])

    totals_table = Table(totals_data, colWidths=[13.5 * cm, 3.5 * cm])
    totals_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -2), 'Helvetica', 9),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 13),
        ('TEXTCOLOR', (0, 0), (-1, -2), gris),
        ('TEXTCOLOR', (0, -1), (0, -1), negro),
        ('TEXTCOLOR', (-1, -1), (-1, -1), rojo),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('BACKGROUND', (0, -1), (-1, -1), rojo_fondo),
        ('LINEABOVE', (0, -1), (-1, -1), 1.5, rojo),
        ('RIGHTPADDING', (-1, 0), (-1, -1), 0),
    ]))
    elements.append(totals_table)

    if quote.notes:
        elements.append(Spacer(1, 0.4 * cm))
        elements.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#E5E7EB')))
        elements.append(Spacer(1, 0.2 * cm))
        elements.append(Paragraph(f'<b>Observaciones:</b> {quote.notes}', normal_style))

    elements.append(Spacer(1, 0.5 * cm))
    elements.append(HRFlowable(width='100%', thickness=0.5, color=rojo))
    elements.append(Spacer(1, 0.2 * cm))
    footer_style = ParagraphStyle('footer', fontSize=7.5, textColor=gris, alignment=TA_CENTER)
    elements.append(Paragraph(
        f'Esta cotización es válida por {quote.valid_days} días a partir de su fecha de emisión · JLB Sports',
        footer_style
    ))

    doc.build(elements)
    return buffer.getvalue()
