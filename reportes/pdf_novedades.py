"""Exportación de novedades a PDF, solo lectura; conserva filtros y criterio histórico."""
import logging
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from flask import Blueprint, Response, request, abort
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, KeepTogether

log = logging.getLogger(__name__)


def crear_blueprint(conectar_bd, requiere_rol):
    bp = Blueprint('pdf_novedades', __name__)

    @bp.get('/admin/reportes/novedades/pdf')
    @requiere_rol('ADMINISTRADOR')
    def exportar_pdf():
        try:
            anio_inicio = request.args.get('anio_inicio', 2022, type=int)
            mes_inicio = request.args.get('mes_inicio', 1, type=int)
            anio_fin = request.args.get('anio_fin', 2026, type=int)
            mes_fin = request.args.get('mes_fin', 12, type=int)
            tipo = request.args.get('tipo', 0, type=int)
            dependencia = request.args.get('dependencia', 0, type=int)
            cargo = request.args.get('cargo', 0, type=int)
            if (not 1900 <= anio_inicio <= 2200 or not 1900 <= anio_fin <= 2200
                    or not 1 <= mes_inicio <= 12 or not 1 <= mes_fin <= 12
                    or min(tipo, dependencia, cargo) < 0):
                abort(400, 'Los filtros no son válidos.')
            desde = anio_inicio * 100 + mes_inicio
            hasta = anio_fin * 100 + mes_fin
            if desde > hasta:
                abort(400, 'El período inicial no puede ser posterior al final.')
        except (TypeError, ValueError):
            abort(400, 'Los filtros no son válidos.')

        base = """
          FROM novedad n
          INNER JOIN nomina no ON no.id_nomina = n.id_nomina
          INNER JOIN periodo_nomina pn ON pn.id_periodo = no.id_periodo
          INNER JOIN empleado e ON e.codigo_empleado = no.codigo_empleado
          INNER JOIN tipo_novedad tn ON tn.id_tipo_novedad = n.id_tipo_novedad
          LEFT JOIN empleado_historial_laboral hl
            ON hl.id_historial_laboral = (
              SELECT hl2.id_historial_laboral
              FROM empleado_historial_laboral hl2
              WHERE hl2.codigo_empleado = e.codigo_empleado
                AND hl2.fecha_inicio <= pn.fecha_fin
                AND (hl2.fecha_fin IS NULL OR hl2.fecha_fin >= pn.fecha_fin)
              ORDER BY hl2.fecha_inicio DESC, hl2.id_historial_laboral DESC
              LIMIT 1
            )
          LEFT JOIN cargo c ON c.id_cargo = hl.id_cargo
          LEFT JOIN dependencia d ON d.id_dependencia = hl.id_dependencia
          WHERE (pn.anio * 100 + pn.mes) BETWEEN %s AND %s
            AND (%s = 0 OR n.id_tipo_novedad = %s)
            AND (%s = 0 OR d.id_dependencia = %s)
            AND (%s = 0 OR c.id_cargo = %s)
        """
        params = (desde, hasta, tipo, tipo, dependencia, dependencia, cargo, cargo)
        conn = cursor = None
        try:
            conn = conectar_bd()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT COUNT(*) AS total_novedades,
                       COUNT(DISTINCT e.codigo_empleado) AS empleados_afectados,
                       COALESCE(SUM(n.cantidad_dias), 0) AS suma_cantidad_dias
            """ + base, params)
            resumen = cursor.fetchone()
            cursor.execute("""
                SELECT pn.anio, pn.mes, n.id_novedad, e.codigo_empleado,
                       e.nombre_empleado, tn.nombre_tipo,
                       COALESCE(d.nombre_dependencia, 'Sin asignación histórica') AS dependencia,
                       COALESCE(c.nombre_cargo, 'Sin asignación histórica') AS cargo,
                       n.fecha_inicio, n.fecha_fin, n.cantidad_dias, n.observacion
            """ + base + " ORDER BY pn.anio DESC, pn.mes DESC, n.id_novedad DESC LIMIT 500", params)
            detalle = cursor.fetchall()
            cursor.execute("""
                SELECT COALESCE(d.nombre_dependencia, 'Sin asignación histórica') AS etiqueta,
                       COUNT(*) AS novedades, COUNT(DISTINCT e.codigo_empleado) AS empleados
            """ + base + " GROUP BY etiqueta ORDER BY novedades DESC, etiqueta", params)
            por_dependencia = cursor.fetchall()
            cursor.execute("""
                SELECT COALESCE(c.nombre_cargo, 'Sin asignación histórica') AS etiqueta,
                       COUNT(*) AS novedades, COUNT(DISTINCT e.codigo_empleado) AS empleados
            """ + base + " GROUP BY etiqueta ORDER BY novedades DESC, etiqueta", params)
            por_cargo = cursor.fetchall()
            cursor.execute("""
                SELECT tn.nombre_tipo AS etiqueta, COUNT(*) AS novedades,
                       COUNT(DISTINCT e.codigo_empleado) AS empleados
            """ + base + " GROUP BY etiqueta ORDER BY novedades DESC, etiqueta", params)
            por_tipo = cursor.fetchall()
            cursor.execute("""
                SELECT pn.anio, pn.mes, COUNT(*) AS novedades,
                       COUNT(DISTINCT e.codigo_empleado) AS empleados
            """ + base + " GROUP BY pn.anio, pn.mes ORDER BY pn.anio DESC, pn.mes DESC", params)
            por_periodo = cursor.fetchall()
        except Exception:
            log.exception('Error al exportar novedades a PDF')
            return 'No se pudo generar el PDF de novedades. Revisa la terminal de Flask.', 500
        finally:
            if cursor is not None:
                cursor.close()
            if conn is not None:
                conn.close()

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='NovedadTitulo', parent=styles['Heading1'], fontSize=17,
                                  leading=20, textColor=colors.HexColor('#14253d')))
        styles.add(ParagraphStyle(name='NovedadCelda', parent=styles['Normal'], fontSize=7, leading=9,
                                  spaceAfter=0))
        styles.add(ParagraphStyle(name='NovedadCabecera', parent=styles['NovedadCelda'],
                                  textColor=colors.white))
        def par(valor, encabezado=False):
            if valor is None:
                valor = '—'
            if hasattr(valor, 'strftime'):
                valor = valor.strftime('%d/%m/%Y')
            return Paragraph(escape(str(valor)), styles['NovedadCabecera' if encabezado else 'NovedadCelda'])

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=13*mm,
                                rightMargin=13*mm, topMargin=16*mm, bottomMargin=16*mm)
        story = [Paragraph('EntreCOL+ | Reporte de novedades de nómina', styles['NovedadTitulo']),
                 Spacer(1, 3*mm),
                 Paragraph(f'Período: {mes_inicio:02d}/{anio_inicio} – {mes_fin:02d}/{anio_fin} | '
                           f'Tipo ID: {tipo or "Todos"} | Dependencia ID: {dependencia or "Todas"} | '
                           f'Cargo ID: {cargo or "Todos"}', styles['Normal']),
                 Spacer(1, 4*mm),
                 Paragraph('Resumen general', styles['Heading2']),
                 Paragraph(f'Novedades: {resumen["total_novedades"]} | '
                           f'Empleados afectados: {resumen["empleados_afectados"]} | '
                           f'Suma de días: {resumen["suma_cantidad_dias"]}', styles['Normal']),
                 Spacer(1, 5*mm)]

        def tabla(titulo, columnas, filas, anchos):
            story.append(Paragraph(escape(titulo), styles['Heading2']))
            if not filas:
                story.append(Paragraph('Sin registros para los filtros seleccionados.', styles['Normal']))
                story.append(Spacer(1, 4*mm))
                return
            matriz = [[par(c, True) for c in columnas]]
            matriz.extend([[par(v) for v in fila] for fila in filas])
            t = LongTable(matriz, colWidths=anchos, repeatRows=1, hAlign='LEFT')
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#14253d')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5f9')]),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.extend([t, Spacer(1, 5*mm)])

        tabla('1. Detalle de novedades (hasta 500 registros)',
              ['Período', 'ID', 'Código', 'Empleado', 'Tipo', 'Dependencia', 'Cargo',
               'Inicio', 'Fin', 'Días', 'Observación'],
              [(f'{x["mes"]:02d}/{x["anio"]}', x['id_novedad'], x['codigo_empleado'],
                x['nombre_empleado'], x['nombre_tipo'], x['dependencia'], x['cargo'],
                x['fecha_inicio'], x['fecha_fin'], x['cantidad_dias'], x['observacion'])
               for x in detalle],
              [19*mm, 12*mm, 18*mm, 36*mm, 28*mm, 35*mm, 30*mm, 20*mm, 20*mm, 12*mm, 37*mm])
        for titulo, datos in [('2. Novedades por dependencia', por_dependencia),
                              ('3. Novedades por cargo', por_cargo),
                              ('4. Novedades por tipo', por_tipo)]:
            tabla(titulo, ['Categoría', 'Novedades', 'Empleados afectados'],
                  [(x['etiqueta'], x['novedades'], x['empleados']) for x in datos],
                  [155*mm, 50*mm, 62*mm])
        tabla('5. Novedades por período', ['Año', 'Mes', 'Novedades', 'Empleados afectados'],
              [(x['anio'], x['mes'], x['novedades'], x['empleados']) for x in por_periodo],
              [55*mm, 50*mm, 70*mm, 92*mm])

        def pie(canvas, document):
            canvas.saveState()
            canvas.setFont('Helvetica', 8)
            canvas.setFillColor(colors.HexColor('#52647a'))
            canvas.drawString(13*mm, 9*mm, f'Generado: {datetime.now():%d/%m/%Y %H:%M}')
            canvas.drawRightString(284*mm, 9*mm, f'Página {document.page}')
            canvas.restoreState()

        try:
            doc.build(story, onFirstPage=pie, onLaterPages=pie)
        except Exception:
            log.exception('Error al construir el PDF de novedades')
            return 'No se pudo construir el PDF de novedades.', 500
        descargar = request.args.get('descargar', '0') == '1'
        modo = 'attachment' if descargar else 'inline'
        return Response(buffer.getvalue(), mimetype='application/pdf', headers={
            'Content-Disposition': f'{modo}; filename="entrecol_novedades.pdf"',
            'Cache-Control': 'private, no-store',
            'X-Content-Type-Options': 'nosniff',
        })

    return bp
