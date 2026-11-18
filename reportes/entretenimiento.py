"""Reportes oficiales de entretenimiento, separados del catálogo."""
from flask import Blueprint, render_template, request
from mysql.connector import Error


def crear_blueprint(conectar_bd, requiere_rol):
    bp = Blueprint("reportes_entretenimiento", __name__)

    @bp.route("/admin/reportes/entretenimiento")
    @requiere_rol("ADMINISTRADOR")
    def entretenimiento():
        orden = request.args.get("orden", "asc").lower()
        orden = orden if orden in ("asc", "desc") else "asc"
        direccion = "ASC" if orden == "asc" else "DESC"
        try:
            n = max(1, min(100, int(request.args.get("n", "10"))))
            generos_n = max(1, min(20, int(request.args.get("generos_n", "2"))))
            anio_inicio = int(request.args.get("anio_inicio", "1900"))
            anio_fin = int(request.args.get("anio_fin", "2100"))
        except (ValueError, TypeError):
            return "Los filtros numéricos deben ser válidos.", 400
        if anio_inicio > anio_fin or not 1800 <= anio_inicio <= 2200 or not 1800 <= anio_fin <= 2200:
            return "El rango de años no es válido.", 400
        genero = request.args.get("genero", "").strip()[:100]
        datos = {}
        conexion = None
        cursor = None
        try:
            conexion = conectar_bd()
            cursor = conexion.cursor(dictionary=True)
            cursor.execute("SELECT id_genero, nombre_genero FROM genero ORDER BY nombre_genero")
            datos["generos"] = cursor.fetchall()
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
            # Compatible con MariaDB 10.4 sin depender de funciones ventana.
            for anio in anios:
                for clave, dir_rating in (("mejores_por_anio", "DESC"), ("peores_por_anio", "ASC")):
                    cursor.execute(f"""
                        SELECT titulo, rating_promedio, YEAR(fecha_publicacion) AS anio
                        FROM libro WHERE YEAR(fecha_publicacion)=%s AND rating_promedio IS NOT NULL
                        ORDER BY rating_promedio {dir_rating}, cantidad_ratings DESC, titulo {direccion} LIMIT 5
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
        except Error:
            bp.logger.exception("Error consultando reportes de entretenimiento") if hasattr(bp, "logger") else None
            return "No se pudieron consultar los reportes de entretenimiento.", 500
        finally:
            if cursor is not None: cursor.close()
            if conexion is not None and conexion.is_connected(): conexion.close()
        return render_template("reportes/entretenimiento.html", datos=datos,
                               orden=orden, n=n, generos_n=generos_n,
                               anio_inicio=anio_inicio, anio_fin=anio_fin, genero=genero)
    return bp
