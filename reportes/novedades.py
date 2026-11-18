"""Reportes de novedades de nómina: solo lectura, por período y ubicación laboral histórica."""
import logging
from flask import Blueprint, render_template, request

logger = logging.getLogger(__name__)


def crear_blueprint(conectar_bd, requiere_rol):
    bp = Blueprint("reportes_novedades", __name__)

    @bp.get("/admin/reportes/novedades")
    @requiere_rol("ADMINISTRADOR")
    def novedades():
        try:
            anio_inicio = request.args.get("anio_inicio", 2022, type=int)
            mes_inicio = request.args.get("mes_inicio", 1, type=int)
            anio_fin = request.args.get("anio_fin", 2026, type=int)
            mes_fin = request.args.get("mes_fin", 12, type=int)
            tipo = request.args.get("tipo", 0, type=int)
            dependencia = request.args.get("dependencia", 0, type=int)
            cargo = request.args.get("cargo", 0, type=int)
            if (not 1900 <= anio_inicio <= 2200 or not 1900 <= anio_fin <= 2200
                    or not 1 <= mes_inicio <= 12 or not 1 <= mes_fin <= 12
                    or min(tipo, dependencia, cargo) < 0):
                return "Los filtros no son válidos.", 400
            desde = anio_inicio * 100 + mes_inicio
            hasta = anio_fin * 100 + mes_fin
            if desde > hasta:
                return "El período inicial no puede ser posterior al final.", 400
        except (TypeError, ValueError):
            return "Los filtros no son válidos.", 400

        # Se selecciona el cargo/dependencia vigente AL CIERRE del período de nómina.
        # Esto evita clasificar una novedad antigua según el cargo actual del empleado.
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
            cursor.execute("SELECT id_tipo_novedad, nombre_tipo FROM tipo_novedad ORDER BY nombre_tipo")
            tipos = cursor.fetchall()
            cursor.execute("SELECT id_dependencia, nombre_dependencia FROM dependencia ORDER BY nombre_dependencia")
            dependencias = cursor.fetchall()
            cursor.execute("SELECT id_cargo, nombre_cargo FROM cargo ORDER BY nombre_cargo")
            cargos = cursor.fetchall()

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
                       COUNT(*) AS novedades,
                       COUNT(DISTINCT e.codigo_empleado) AS empleados
            """ + base + " GROUP BY etiqueta ORDER BY novedades DESC, etiqueta", params)
            por_dependencia = cursor.fetchall()

            cursor.execute("""
                SELECT COALESCE(c.nombre_cargo, 'Sin asignación histórica') AS etiqueta,
                       COUNT(*) AS novedades,
                       COUNT(DISTINCT e.codigo_empleado) AS empleados
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
            logger.exception("No fue posible consultar los reportes de novedades")
            return "No se pudieron cargar los reportes de novedades. Revisa la terminal de Flask.", 500
        finally:
            if cursor is not None:
                cursor.close()
            if conn is not None:
                conn.close()

        # JSON seguro para Chart.js: no se envían fechas ni Decimal en los datasets.
        def grafico(filas):
            return [{"etiqueta": str(f["etiqueta"]),
                     "novedades": int(f["novedades"]),
                     "empleados": int(f["empleados"])} for f in filas]

        return render_template(
            "reportes/novedades.html",
            anio_inicio=anio_inicio, mes_inicio=mes_inicio,
            anio_fin=anio_fin, mes_fin=mes_fin,
            tipo=tipo, dependencia=dependencia, cargo=cargo,
            tipos=tipos, dependencias=dependencias, cargos=cargos,
            resumen=resumen, detalle=detalle, por_periodo=por_periodo,
            por_dependencia=por_dependencia, por_cargo=por_cargo, por_tipo=por_tipo,
            grafico_dependencia=grafico(por_dependencia),
            grafico_cargo=grafico(por_cargo), grafico_tipo=grafico(por_tipo)
        )

    return bp
