"""Vista previa y descarga de reportes de salud y pensión (solo lectura)."""
import logging
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from flask import Blueprint, Response, request
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle

log = logging.getLogger(__name__)


def crear_blueprint(conectar_bd, requiere_rol):
    bp = Blueprint("pdf_salud_pension", __name__)

    @bp.get("/admin/reportes/salud-pension/pdf")
    @requiere_rol("ADMINISTRADOR")
    def exportar():
        dependencia = request.args.get("dependencia", "", type=str).strip()
        cargo = request.args.get("cargo", "", type=str).strip()
        if len(dependencia) > 100 or len(cargo) > 100:
            return "Filtro demasiado largo", 400

        vigente_laboral = """
          LEFT JOIN empleado_historial_laboral hl
            ON hl.id_historial_laboral = (
              SELECT h2.id_historial_laboral FROM empleado_historial_laboral h2
              WHERE h2.codigo_empleado = e.codigo_empleado
                AND h2.fecha_inicio <= CURDATE()
                AND (h2.fecha_fin IS NULL OR h2.fecha_fin >= CURDATE())
              ORDER BY h2.fecha_inicio DESC, h2.id_historial_laboral DESC LIMIT 1)
          LEFT JOIN cargo c ON c.id_cargo = hl.id_cargo
          LEFT JOIN dependencia d ON d.id_dependencia = hl.id_dependencia
        """
        vigente_eps = """
          LEFT JOIN empleado_historial_eps he
            ON he.id_historial_eps = (
              SELECT h2.id_historial_eps FROM empleado_historial_eps h2
              WHERE h2.codigo_empleado = e.codigo_empleado
                AND h2.fecha_inicio <= CURDATE()
                AND (h2.fecha_fin IS NULL OR h2.fecha_fin >= CURDATE())
              ORDER BY h2.fecha_inicio DESC, h2.id_historial_eps DESC LIMIT 1)
          LEFT JOIN eps ep ON ep.id_eps = he.id_eps
        """
        vigente_pension = """
          LEFT JOIN empleado_historial_pension hp
            ON hp.id_historial_pension = (
              SELECT h2.id_historial_pension FROM empleado_historial_pension h2
              WHERE h2.codigo_empleado = e.codigo_empleado
                AND h2.fecha_inicio <= CURDATE()
                AND (h2.fecha_fin IS NULL OR h2.fecha_fin >= CURDATE())
              ORDER BY h2.fecha_inicio DESC, h2.id_historial_pension DESC LIMIT 1)
          LEFT JOIN pension pe ON pe.id_pension = hp.id_pension
        """
        base = (" FROM empleado e " + vigente_laboral + vigente_eps + vigente_pension +
                " WHERE e.estado_empleado = 'ACTIVO' "
                " AND (%s = '' OR d.nombre_dependencia = %s) "
                " AND (%s = '' OR c.nombre_cargo = %s) ")
        params = (dependencia, dependencia, cargo, cargo)
        conn = cur = None
        try:
            conn = conectar_bd()
            cur = conn.cursor(dictionary=True)
            cur.execute("""
              SELECT e.codigo_empleado, e.nombre_empleado,
                     COALESCE(d.nombre_dependencia, 'Sin dependencia') AS dependencia,
                     COALESCE(c.nombre_cargo, 'Sin cargo') AS cargo,
                     COALESCE(ep.nombre_eps, 'Sin EPS vigente') AS eps,
                     COALESCE(pe.nombre_pension, 'Sin pensión vigente') AS pension
            """ + base + " ORDER BY e.nombre_empleado, e.codigo_empleado LIMIT 500", params)
            empleados = cur.fetchall()

            cur.execute("""
              SELECT COALESCE(ep.nombre_eps, 'Sin EPS vigente') AS etiqueta,
                     COUNT(*) AS cantidad
            """ + base + " GROUP BY etiqueta ORDER BY cantidad DESC, etiqueta", params)
            frecuencia_eps = cur.fetchall()

            cur.execute("""
              SELECT COALESCE(pe.nombre_pension, 'Sin pensión vigente') AS etiqueta,
                     COUNT(*) AS cantidad
            """ + base + " GROUP BY etiqueta ORDER BY cantidad DESC, etiqueta", params)
            frecuencia_pension = cur.fetchall()

            cur.execute("""
              SELECT COALESCE(d.nombre_dependencia, 'Sin dependencia') AS dependencia,
                     COUNT(*) AS empleados,
                     SUM(CASE WHEN ep.id_eps IS NOT NULL THEN 1 ELSE 0 END) AS con_eps,
                     SUM(CASE WHEN pe.id_pension IS NOT NULL THEN 1 ELSE 0 END) AS con_pension
            """ + base + " GROUP BY dependencia ORDER BY dependencia", params)
            comparativo = cur.fetchall()
            total = sum(int(x["cantidad"]) for x in frecuencia_eps)
        except Exception:
            log.exception("Error al generar PDF de salud y pensión")
            return "No se pudo generar el PDF de salud y pensión.", 500
        finally:
            if cur is not None:
                cur.close()
            if conn is not None:
                conn.close()

        estilos = getSampleStyleSheet()
        estilos.add(ParagraphStyle(name="TituloEntreCOL", parent=estilos["Heading1"],
                                   fontSize=17, leading=21,
                                   textColor=colors.HexColor("#152f52")))
        estilos.add(ParagraphStyle(name="CeldaEntreCOL", parent=estilos["Normal"],
                                   fontSize=7, leading=9))
        estilos.add(ParagraphStyle(name="CabeceraEntreCOL", parent=estilos["CeldaEntreCOL"],
                                   textColor=colors.white))
        estilos.add(ParagraphStyle(name="NotaEntreCOL", parent=estilos["Normal"],
                                   fontSize=9, leading=12))

        def parrafo(valor, estilo="CeldaEntreCOL"):
            valor = "—" if valor is None else str(valor)
            return Paragraph(escape(valor), estilos[estilo])

        buffer = BytesIO()
        documento = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                                      leftMargin=13*mm, rightMargin=13*mm,
                                      topMargin=16*mm, bottomMargin=16*mm)
        contenido = [
            Paragraph("EntreCOL+ | Reportes de salud y pensión", estilos["TituloEntreCOL"]),
            Spacer(1, 4*mm),
            parrafo("Dependencia: {} | Cargo: {} | Total de empleados activos: {}".format(
                dependencia or "Todas", cargo or "Todos", total), "NotaEntreCOL"),
            Spacer(1, 5*mm),
        ]

        def agregar_tabla(titulo, cabeceras, filas, anchos):
            contenido.append(Paragraph(escape(titulo), estilos["Heading2"]))
            if not filas:
                contenido.extend([parrafo("Sin registros para los filtros seleccionados.",
                                          "NotaEntreCOL"), Spacer(1, 5*mm)])
                return
            celdas = [[parrafo(c, "CabeceraEntreCOL") for c in cabeceras]]
            celdas.extend([[parrafo(c) for c in fila] for fila in filas])
            tabla = LongTable(celdas, colWidths=anchos, repeatRows=1, hAlign="LEFT")
            tabla.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#152f52")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#eef3f9")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            contenido.extend([tabla, Spacer(1, 6*mm)])

        agregar_tabla("1. Empleados activos y afiliaciones vigentes (máximo 500)",
                      ["Código", "Empleado", "Dependencia", "Cargo", "EPS", "Pensión"],
                      [(x["codigo_empleado"], x["nombre_empleado"], x["dependencia"],
                        x["cargo"], x["eps"], x["pension"]) for x in empleados],
                      [24*mm, 55*mm, 48*mm, 43*mm, 46*mm, 55*mm])
        agregar_tabla("2. Frecuencia de afiliaciones por EPS",
                      ["EPS", "Cantidad de empleados"],
                      [(x["etiqueta"], x["cantidad"]) for x in frecuencia_eps],
                      [150*mm, 65*mm])
        agregar_tabla("3. Frecuencia de afiliaciones por pensión",
                      ["Fondo de pensión", "Cantidad de empleados"],
                      [(x["etiqueta"], x["cantidad"]) for x in frecuencia_pension],
                      [150*mm, 65*mm])
        agregar_tabla("4. Comparativo de afiliaciones por dependencia",
                      ["Dependencia", "Empleados", "Con EPS", "Con pensión"],
                      [(x["dependencia"], x["empleados"], x["con_eps"], x["con_pension"])
                       for x in comparativo],
                      [125*mm, 46*mm, 46*mm, 54*mm])

        def pie(pagina, doc):
            pagina.saveState()
            pagina.setFont("Helvetica", 8)
            pagina.setFillColor(colors.HexColor("#52647a"))
            pagina.drawString(13*mm, 9*mm, f"Generado: {datetime.now():%d/%m/%Y %H:%M}")
            pagina.drawRightString(284*mm, 9*mm, f"Página {doc.page}")
            pagina.restoreState()

        documento.build(contenido, onFirstPage=pie, onLaterPages=pie)
        modo = "attachment" if request.args.get("descargar") == "1" else "inline"
        return Response(buffer.getvalue(), mimetype="application/pdf", headers={
            "Content-Disposition": f'{modo}; filename="entrecol_salud_pension.pdf"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        })

    return bp
