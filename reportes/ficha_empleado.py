from flask import Blueprint, render_template, abort, current_app

def crear_blueprint(conectar_bd, requiere_rol):
    bp = Blueprint("ficha_empleado", __name__)

    @bp.get("/admin/empleados/<codigo_empleado>/ficha")
    @requiere_rol("ADMINISTRADOR")
    def ficha(codigo_empleado):
        conexion = None
        cursor = None
        try:
            conexion = conectar_bd()
            cursor = conexion.cursor(dictionary=True)
            cursor.execute("""
                SELECT codigo_empleado, nombre_empleado, documento,
                       fecha_nacimiento, direccion, telefono, correo,
                       fecha_ingreso_empresa, estado_empleado
                FROM empleado WHERE codigo_empleado = %s
            """, (codigo_empleado,))
            empleado = cursor.fetchone()
            if empleado is None:
                abort(404)

            cursor.execute("""
                SELECT c.nombre_cargo, d.nombre_dependencia, h.fecha_inicio, h.fecha_fin
                FROM empleado_historial_laboral h
                JOIN cargo c ON c.id_cargo = h.id_cargo
                JOIN dependencia d ON d.id_dependencia = h.id_dependencia
                WHERE h.codigo_empleado = %s
                ORDER BY h.fecha_inicio DESC, h.id_historial_laboral DESC
            """, (codigo_empleado,))
            historial_laboral = cursor.fetchall()
            laboral_actual = next((x for x in historial_laboral if
                x["fecha_inicio"] and x["fecha_inicio"] <= __import__("datetime").date.today()
                and (x["fecha_fin"] is None or x["fecha_fin"] >= __import__("datetime").date.today())), None)

            def afiliacion(tabla, entidad, campo, pk):
                # Los nombres de tabla y columna son constantes internas, no vienen del usuario.
                cursor.execute(f"""
                    SELECT e.{campo} AS nombre, h.fecha_inicio, h.fecha_fin
                    FROM {tabla} h
                    JOIN {entidad} e ON e.id_{entidad} = h.id_{entidad}
                    WHERE h.codigo_empleado = %s
                      AND h.fecha_inicio <= CURDATE()
                      AND (h.fecha_fin IS NULL OR h.fecha_fin >= CURDATE())
                    ORDER BY h.fecha_inicio DESC, h.{pk} DESC LIMIT 1
                """, (codigo_empleado,))
                return cursor.fetchone()

            eps = afiliacion("empleado_historial_eps", "eps", "nombre_eps", "id_historial_eps")
            pension = afiliacion("empleado_historial_pension", "pension", "nombre_pension", "id_historial_pension")
            arl = afiliacion("empleado_historial_arl", "arl", "nombre_arl", "id_historial_arl")

            cursor.execute("""
                SELECT salario, fecha_inicio, fecha_fin
                FROM empleado_historial_salario
                WHERE codigo_empleado = %s
                ORDER BY fecha_inicio DESC, id_historial_salario DESC
            """, (codigo_empleado,))
            salarios = cursor.fetchall()
            from datetime import date
            hoy = date.today()
            salario_actual = next((s for s in salarios if
                s["fecha_inicio"] <= hoy and (s["fecha_fin"] is None or s["fecha_fin"] >= hoy)), None)

            cursor.execute("""
                SELECT n.id_novedad, t.nombre_tipo, n.fecha_inicio, n.fecha_fin,
                       n.cantidad_dias, n.observacion, p.mes, p.anio
                FROM novedad n
                JOIN tipo_novedad t ON t.id_tipo_novedad = n.id_tipo_novedad
                JOIN nomina no ON no.id_nomina = n.id_nomina
                JOIN periodo_nomina p ON p.id_periodo = no.id_periodo
                WHERE no.codigo_empleado = %s
                ORDER BY p.anio DESC, p.mes DESC, n.id_novedad DESC
                LIMIT 100
            """, (codigo_empleado,))
            novedades = cursor.fetchall()
            return render_template("reportes/ficha_empleado.html",
                empleado=empleado, laboral_actual=laboral_actual,
                historial_laboral=historial_laboral, eps=eps, pension=pension,
                arl=arl, salario_actual=salario_actual, salarios=salarios,
                novedades=novedades)
        except Exception as exc:
            from werkzeug.exceptions import HTTPException
            if isinstance(exc, HTTPException):
                raise
            current_app.logger.exception("No se pudo consultar la ficha del empleado")
            return "No se pudo cargar la ficha del empleado.", 500
        finally:
            if cursor is not None:
                cursor.close()
            if conexion is not None:
                conexion.close()
    return bp
