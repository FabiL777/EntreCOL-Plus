"""Exportación PDF de reportes de entretenimiento. No altera datos."""
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from flask import Blueprint, Response, abort, current_app, request
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle


def crear_blueprint(conectar_bd, requiere_rol):
    bp = Blueprint("pdf_entretenimiento", __name__)

    @bp.get("/admin/reportes/entretenimiento/pdf")
    @requiere_rol("ADMINISTRADOR")
    def exportar():
        orden = request.args.get("orden", "asc").lower()
        if orden not in ("asc", "desc"):
            abort(400)
        direccion = "ASC" if orden == "asc" else "DESC"
        try:
            n = max(1, min(100, int(request.args.get("n", "10"))))
            generos_n = max(1, min(20, int(request.args.get("generos_n", "2"))))
            anio_inicio = int(request.args.get("anio_inicio", "1900"))
            anio_fin = int(request.args.get("anio_fin", "2100"))
        except (ValueError, TypeError):
            abort(400)
        if anio_inicio > anio_fin or not 1800 <= anio_inicio <= 2200 or not 1800 <= anio_fin <= 2200:
            abort(400)
        genero = request.args.get("genero", "").strip()[:100]
        descargar = request.args.get("descargar", "0") == "1"
        datos = {}
        conexion = cursor = None
        try:
            conexion = conectar_bd()
            cursor = conexion.cursor(dictionary=True)
            cursor.execute(f"""
                SELECT DISTINCT p.id_pelicula, p.titulo, p.anio_lanzamiento, g.nombre_genero
                FROM pelicula p JOIN pelicula_genero pg ON pg.id_pelicula=p.id_pelicula
                JOIN genero g ON g.id_genero=pg.id_genero
                WHERE p.anio_lanzamiento BETWEEN %s AND %s
                  AND (%s='' OR g.nombre_genero=%s)
                ORDER BY p.titulo {direccion}, g.nombre_genero ASC LIMIT 200
            """, (anio_inicio, anio_fin, genero, genero))
            datos["peliculas_fecha_genero"] = cursor.fetchall()
            cursor.execute(f"""
                SELECT id_libro, titulo, rating_promedio, cantidad_ratings
                FROM libro WHERE rating_promedio IS NOT NULL
                ORDER BY rating_promedio DESC, cantidad_ratings DESC, titulo {direccion}
                LIMIT %s
            """, (n,))
            datos["top_libros"] = cursor.fetchall()
            cursor.execute("""
                SELECT YEAR(fecha_publicacion) AS anio FROM libro
                WHERE fecha_publicacion IS NOT NULL GROUP BY YEAR(fecha_publicacion)
                ORDER BY anio DESC LIMIT 100
            """)
            anios = [x["anio"] for x in cursor.fetchall()]
            datos["mejores_por_anio"] = []
            datos["peores_por_anio"] = []
            for anio in anios:
                for clave, sentido in (("mejores_por_anio", "DESC"), ("peores_por_anio", "ASC")):
                    cursor.execute(f"""
                        SELECT titulo, rating_promedio, YEAR(fecha_publicacion) AS anio
                        FROM libro WHERE YEAR(fecha_publicacion)=%s AND rating_promedio IS NOT NULL
                        ORDER BY rating_promedio {sentido}, cantidad_ratings DESC,
                                 titulo {direccion} LIMIT 5
                    """, (anio,))
                    datos[clave].extend(cursor.fetchall())
            cursor.execute(f"""
                SELECT p.id_pelicula, p.titulo, COUNT(DISTINCT pg.id_genero) AS total_generos,
                       GROUP_CONCAT(DISTINCT g.nombre_genero ORDER BY g.nombre_genero SEPARATOR ', ') AS generos
                FROM pelicula p JOIN pelicula_genero pg ON pg.id_pelicula=p.id_pelicula
                JOIN genero g ON g.id_genero=pg.id_genero
                GROUP BY p.id_pelicula, p.titulo
                HAVING COUNT(DISTINCT pg.id_genero)=%s
                ORDER BY p.titulo {direccion} LIMIT 200
            """, (generos_n,))
            datos["peliculas_n_generos"] = cursor.fetchall()
            cursor.execute("""
                SELECT g.nombre_genero AS etiqueta, COUNT(DISTINCT pg.id_pelicula) AS cantidad
                FROM genero g LEFT JOIN pelicula_genero pg ON pg.id_genero=g.id_genero
                GROUP BY g.id_genero, g.nombre_genero ORDER BY cantidad DESC, etiqueta
            """)
            datos["frecuencia_generos"] = cursor.fetchall()
            cursor.execute("""
                SELECT YEAR(fecha_publicacion) AS etiqueta, COUNT(*) AS cantidad
                FROM libro WHERE fecha_publicacion IS NOT NULL
                  AND YEAR(fecha_publicacion) BETWEEN %s AND %s
                GROUP BY YEAR(fecha_publicacion) ORDER BY etiqueta
            """, (anio_inicio, anio_fin))
            datos["frecuencia_libros"] = cursor.fetchall()
        except Exception:
            current_app.logger.exception("Error generando PDF de entretenimiento")
            return "No se pudo generar el PDF de entretenimiento.", 500
        finally:
            if cursor is not None:
                cursor.close()
            if conexion is not None:
                conexion.close()

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name="EntrecolTitulo", parent=styles["Heading1"],
                                  fontSize=18, leading=22, textColor=colors.HexColor("#14253d")))
        styles.add(ParagraphStyle(name="EntrecolCelda", parent=styles["Normal"], fontSize=7, leading=9))
        styles.add(ParagraphStyle(name="EntrecolCabecera", parent=styles["EntrecolCelda"],
                                  textColor=colors.white))
        styles.add(ParagraphStyle(name="EntrecolNota", parent=styles["Normal"], fontSize=9, leading=12))
        def p(valor, estilo="EntrecolCelda"):
            return Paragraph(escape(str(valor if valor is not None else "—")), styles[estilo])

        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                                leftMargin=15*mm, rightMargin=15*mm,
                                topMargin=16*mm, bottomMargin=16*mm)
        story = [Paragraph("EntreCOL+ | Reportes de entretenimiento", styles["EntrecolTitulo"]),
                 Spacer(1, 4*mm),
                 p(f"Años: {anio_inicio}–{anio_fin} | Género: {genero or 'Todos'} | "
                   f"Top libros: {n} | Géneros por película: {generos_n} | Orden: {orden.upper()}",
                   "EntrecolNota"),
                 Spacer(1, 5*mm)]
        def tabla(titulo, cabeceras, filas, anchos):
            story.append(Paragraph(escape(titulo), styles["Heading2"]))
            if not filas:
                story.extend([p("Sin registros para esta consulta.", "EntrecolNota"), Spacer(1, 4*mm)])
                return
            matriz = [[p(c, "EntrecolCabecera") for c in cabeceras]]
            matriz += [[p(v) for v in fila] for fila in filas]
            t = LongTable(matriz, colWidths=anchos, repeatRows=1, hAlign="LEFT")
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14253d")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#f3f6fa")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.extend([t, Spacer(1, 6*mm)])

        tabla("1. Películas por género y rango de años",
              ["Título", "Año", "Género"],
              [(x["titulo"], x["anio_lanzamiento"], x["nombre_genero"])
               for x in datos["peliculas_fecha_genero"]], [140*mm, 24*mm, 98*mm])
        tabla("2. Libros mejor valorados (Top N)",
              ["Título", "Valoración", "Cantidad de valoraciones"],
              [(x["titulo"], x["rating_promedio"], x["cantidad_ratings"])
               for x in datos["top_libros"]], [165*mm, 35*mm, 62*mm])
        for titulo, clave in (("3a. Cinco mejores libros por año", "mejores_por_anio"),
                              ("3b. Cinco peores libros por año", "peores_por_anio")):
            tabla(titulo, ["Año", "Título", "Valoración"],
                  [(x["anio"], x["titulo"], x["rating_promedio"])
                   for x in datos[clave]], [27*mm, 195*mm, 40*mm])
        tabla("4. Películas con exactamente N géneros",
              ["Título", "N.º de géneros", "Géneros"],
              [(x["titulo"], x["total_generos"], x["generos"])
               for x in datos["peliculas_n_generos"]], [120*mm, 36*mm, 106*mm])
        tabla("5. Frecuencia de películas por género",
              ["Género", "Películas"],
              [(x["etiqueta"], x["cantidad"]) for x in datos["frecuencia_generos"]],
              [170*mm, 40*mm])
        tabla("6. Frecuencia de libros por año de publicación",
              ["Año", "Libros"],
              [(x["etiqueta"], x["cantidad"]) for x in datos["frecuencia_libros"]],
              [80*mm, 40*mm])
        def pie(canvas, document):
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#52647a"))
            canvas.drawString(15*mm, 9*mm, f"Generado: {datetime.now():%d/%m/%Y %H:%M}")
            canvas.drawRightString(280*mm, 9*mm, f"Página {document.page}")
            canvas.restoreState()
        doc.build(story, onFirstPage=pie, onLaterPages=pie)
        modo = "attachment" if descargar else "inline"
        return Response(buf.getvalue(), mimetype="application/pdf", headers={
            "Content-Disposition": f'{modo}; filename="entrecol_entretenimiento.pdf"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        })
    return bp
