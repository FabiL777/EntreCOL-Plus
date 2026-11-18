"""Vista previa y descarga PDF del reporte de nómina (solo lectura)."""
from datetime import datetime
from io import BytesIO
from urllib.parse import urlencode

from flask import Blueprint, Response, abort, request, current_app
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from xml.sax.saxutils import escape


def crear_blueprint(conectar_bd, requiere_rol):
    bp = Blueprint("pdf_nomina", __name__)

    @bp.get('/admin/reportes/nomina/pdf')
    @requiere_rol('ADMINISTRADOR')
    def exportar_nomina():
        orden = request.args.get('orden', 'asc').lower()
        dependencia = request.args.get('dependencia', '').strip()
        cargo = request.args.get('cargo', '').strip()
        estado = request.args.get('estado', '').strip().upper()
        descargar = request.args.get('descargar', '0') == '1'
        if (orden not in ('asc', 'desc') or len(dependencia) > 100 or
                len(cargo) > 100 or estado not in ('', 'ACTIVO', 'INACTIVO')):
            abort(400)

        conexion = cursor = None
        try:
            conexion = conectar_bd()
            cursor = conexion.cursor(dictionary=True)
            cursor.execute('''
                SELECT e.codigo_empleado, e.nombre_empleado, e.estado_empleado,
                       COALESCE(d.nombre_dependencia, 'Sin dependencia') AS nombre_dependencia,
                       COALESCE(c.nombre_cargo, 'Sin cargo') AS nombre_cargo
                FROM empleado e
                LEFT JOIN empleado_historial_laboral hl
                  ON hl.id_historial_laboral = (
                    SELECT h2.id_historial_laboral FROM empleado_historial_laboral h2
                    WHERE h2.codigo_empleado = e.codigo_empleado
                      AND h2.fecha_inicio <= CURDATE()
                      AND (h2.fecha_fin IS NULL OR h2.fecha_fin >= CURDATE())
                    ORDER BY h2.fecha_inicio DESC, h2.id_historial_laboral DESC LIMIT 1
                  )
                LEFT JOIN dependencia d ON d.id_dependencia = hl.id_dependencia
                LEFT JOIN cargo c ON c.id_cargo = hl.id_cargo
                WHERE (%s = '' OR d.nombre_dependencia = %s)
                  AND (%s = '' OR c.nombre_cargo = %s)
                  AND (%s = '' OR e.estado_empleado = %s)
            ''', (dependencia, dependencia, cargo, cargo, estado, estado))
            empleados = cursor.fetchall()
        except Exception:
            current_app.logger.exception('Error al generar PDF de nómina')
            return 'No se pudo generar el PDF de nómina.', 500
        finally:
            if cursor is not None:
                cursor.close()
            if conexion is not None:
                conexion.close()

        empleados.sort(key=lambda e: (str(e['nombre_empleado']).casefold(), str(e['codigo_empleado'])),
                       reverse=(orden == 'desc'))
        por_dependencia = {}
        por_cargo = {}
        for e in empleados:
            d, c = e['nombre_dependencia'], e['nombre_cargo']
            por_dependencia[d] = por_dependencia.get(d, 0) + 1
            por_cargo[(d, c)] = por_cargo.get((d, c), 0) + 1

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='TituloEntrecol', parent=styles['Heading1'],
                                  fontSize=19, leading=23, textColor=colors.HexColor('#14253d')))
        styles.add(ParagraphStyle(name='CeldaEntrecol', parent=styles['Normal'], fontSize=8, leading=10))
        styles.add(ParagraphStyle(name='EncabezadoEntrecol', parent=styles['Normal'],
                                  fontSize=8, leading=10, textColor=colors.white))
        styles.add(ParagraphStyle(name='NotaEntrecol', parent=styles['Normal'], fontSize=9, leading=13))
        celda = lambda x: Paragraph(escape(str(x if x is not None else '—')), styles['CeldaEntrecol'])
        encabezado = lambda x: Paragraph(escape(str(x)), styles['EncabezadoEntrecol'])

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                                leftMargin=16*mm, rightMargin=16*mm,
                                topMargin=17*mm, bottomMargin=17*mm)
        story = [Paragraph('EntreCOL+ | Reporte de nómina', styles['TituloEntrecol']), Spacer(1, 6*mm)]
        filtros = (f'Dependencia: {dependencia or "Todas"}  |  Cargo: {cargo or "Todos"}  |  '
                   f'Estado: {estado or "Todos"}  |  Orden: {orden.upper()}')
        story.extend([Paragraph(escape(filtros), styles['NotaEntrecol']), Spacer(1, 3*mm),
                      Paragraph(f'Empleados encontrados: {len(empleados)}', styles['NotaEntrecol']),
                      Spacer(1, 6*mm)])

        def agregar_tabla(titulo, cabeceras, filas, anchos):
            story.append(Paragraph(escape(titulo), styles['Heading2']))
            if not filas:
                story.append(Paragraph('No hay registros para los filtros seleccionados.', styles['NotaEntrecol']))
                story.append(Spacer(1, 5*mm))
                return
            data = [[encabezado(x) for x in cabeceras]] + [[celda(x) for x in fila] for fila in filas]
            tabla = Table(data, colWidths=anchos, repeatRows=1, hAlign='LEFT')
            tabla.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#14253d')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f6fa')]),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                ('TOPPADDING', (0, 0), (-1, -1), 7),
                ('LINEBELOW', (0, -1), (-1, -1), .3, colors.HexColor('#dce5ef')),
            ]))
            story.extend([tabla, Spacer(1, 7*mm)])

        agregar_tabla('Listado general', ['Código', 'Empleado', 'Dependencia', 'Cargo', 'Estado'],
                      [(e['codigo_empleado'], e['nombre_empleado'], e['nombre_dependencia'],
                        e['nombre_cargo'], e['estado_empleado']) for e in empleados],
                      [31*mm, 68*mm, 65*mm, 65*mm, 32*mm])
        agregar_tabla('Empleados por dependencia', ['Dependencia', 'Cantidad'],
                      [(d, n) for d, n in sorted(por_dependencia.items(), key=lambda x: (-x[1], x[0]))],
                      [110*mm, 32*mm])
        agregar_tabla('Empleados por cargo y dependencia', ['Dependencia', 'Cargo', 'Cantidad'],
                      [(d, c, n) for (d, c), n in sorted(por_cargo.items())],
                      [90*mm, 90*mm, 30*mm])

        def pie_pagina(canvas, documento):
            canvas.saveState()
            canvas.setFont('Helvetica', 8)
            canvas.setFillColor(colors.HexColor('#52647a'))
            canvas.drawString(16*mm, 10*mm, f'Generado: {datetime.now():%d/%m/%Y %H:%M}')
            canvas.drawRightString(281*mm, 10*mm, f'Página {documento.page}')
            canvas.restoreState()

        doc.build(story, onFirstPage=pie_pagina, onLaterPages=pie_pagina)
        modo = 'attachment' if descargar else 'inline'
        return Response(buffer.getvalue(), mimetype='application/pdf', headers={
            'Content-Disposition': f'{modo}; filename="entrecol_nomina.pdf"',
            'Cache-Control': 'private, no-store',
            'X-Content-Type-Options': 'nosniff',
        })
    return bp
