"""Reportes de afiliaciones EPS y pensión. Solo lectura."""
import logging
from flask import Blueprint, render_template, request

log = logging.getLogger(__name__)

def crear_blueprint(conectar_bd, requiere_rol):
    bp = Blueprint("reportes_salud_pension", __name__)

    @bp.get("/admin/reportes/salud-pension")
    @requiere_rol("ADMINISTRADOR")
    def salud_pension():
        dependencia = request.args.get("dependencia", "", type=str).strip()
        cargo = request.args.get("cargo", "", type=str).strip()
        if len(dependencia) > 100 or len(cargo) > 100:
            return "Filtro demasiado largo", 400

        # Una sola fila vigente por empleado y tipo de afiliación.
        # Se elige el historial más reciente cuya fecha de inicio no sea futura.
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
            cur.execute("SELECT nombre_dependencia FROM dependencia ORDER BY nombre_dependencia")
            dependencias = [x["nombre_dependencia"] for x in cur.fetchall()]
            cur.execute("SELECT nombre_cargo FROM cargo ORDER BY nombre_cargo")
            cargos = [x["nombre_cargo"] for x in cur.fetchall()]

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
            log.exception("Error en reportes de salud y pensión")
            return "No se pudieron cargar los reportes de salud y pensión.", 500
        finally:
            if cur is not None:
                cur.close()
            if conn is not None:
                conn.close()
        return render_template(
            "reportes/salud_pension.html", empleados=empleados,
            frecuencia_eps=frecuencia_eps, frecuencia_pension=frecuencia_pension,
            comparativo=comparativo, dependencias=dependencias, cargos=cargos,
            dependencia=dependencia, cargo=cargo, total=total
        )
    return bp
