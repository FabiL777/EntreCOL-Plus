from flask import Flask, render_template, request, session, redirect, url_for, flash
from werkzeug.security import check_password_hash, generate_password_hash
from flask_wtf.csrf import CSRFProtect
import mysql.connector
from dotenv import load_dotenv
from pathlib import Path
import requests
import os
from functools import wraps
from flask import abort
import re


# Cargar la configuración de la base de datos.
load_dotenv(
    dotenv_path=Path(__file__).resolve().parent / ".env",
    override=True
)


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]

# Activar la protección CSRF en Flask
csrf = CSRFProtect(app)



# CONEXIÓN A MYSQL
def conectar_bd():
    conexion = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME")
    )
    return conexion

 #Verificar CAPTCHA con Cloudflare Turnstile 
def verificar_captcha(token):
    if not token:
        return False

    clave_secreta = os.getenv("TURNSTILE_SECRET_KEY")

    if not clave_secreta:
        return False

    try:
        respuesta = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={
                "secret": clave_secreta,
                "response": token
            },
            timeout=10
        )

        respuesta.raise_for_status()
        resultado = respuesta.json()

        if resultado.get("success") is not True:
            app.logger.warning(
                "Turnstile rechazó la verificación. "
                "Códigos de error: %s",
                resultado.get("error-codes", [])
            )

        return resultado.get("success") is True

    except (requests.RequestException, ValueError):
        app.logger.exception(
            "No se pudo verificar el CAPTCHA"
        )
        return False


def requiere_rol(*roles_permitidos):
    def decorador(funcion):
        @wraps(funcion)
        def funcion_protegida(*args, **kwargs):

            if "id_usuario" not in session:
                return redirect(url_for("login"))

            conexion = None
            cursor = None

            try:
                conexion = conectar_bd()
                cursor = conexion.cursor(dictionary=True)

                cursor.execute(
                    """
                    SELECT
                        u.estado_usuario,
                        r.nombre_rol
                    FROM usuario AS u
                    INNER JOIN rol AS r
                        ON u.id_rol = r.id_rol
                    WHERE u.id_usuario = %s
                    """,
                    (session["id_usuario"],)
                )

                usuario = cursor.fetchone()

                if (
                    usuario is None
                    or usuario["estado_usuario"] != "ACTIVO"
                ):
                    session.clear()
                    return redirect(url_for("login"))

                if usuario["nombre_rol"] not in roles_permitidos:
                    abort(403)

            except mysql.connector.Error:
                app.logger.exception(
                    "Error al verificar permisos"
                )
                abort(503)

            finally:
                if cursor is not None:
                    cursor.close()

                if conexion is not None and conexion.is_connected():
                    conexion.close()

            return funcion(*args, **kwargs)

        return funcion_protegida

    return decorador

# REGISTRO PÚBLICO DE USUARIOS
@app.route("/registro", methods=["GET", "POST"])
def registro():

    if "id_usuario" in session:
        return redirect(url_for("panel_usuario"))

    if request.method == "POST":

        nombre = request.form.get("nombre_usuario", "").strip()
        correo = request.form.get("correo_electronico", "").strip().lower()
        contrasena = request.form.get("contrasena", "")
        confirmar = request.form.get("confirmar_contrasena", "")

        datos = {
            "nombre_usuario": nombre,
            "correo_electronico": correo
        }

        errores = []

        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,60}", nombre):
            errores.append(
                "El nombre de usuario debe tener entre 3 y 60 "
                "caracteres: letras, números, puntos, guiones o guion bajo."
            )

        if (
            len(correo) > 150
            or not re.fullmatch(
                r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
                correo
            )
        ):
            errores.append("Ingresa un correo electrónico válido.")

        if len(contrasena) < 8 or len(contrasena) > 128:
            errores.append(
                "La contraseña debe tener entre 8 y 128 caracteres."
            )

        if contrasena != confirmar:
            errores.append("Las contraseñas no coinciden.")

        if errores:
            return render_template(
                "registro.html",
                errores=[],
                datos={},
                turnstile_site_key=os.environ["TURNSTILE_SITE_KEY"]
            )

        conexion = None
        cursor = None

        try:
            conexion = conectar_bd()
            cursor = conexion.cursor(dictionary=True)

            # Obtener el rol público desde la base de datos.
            cursor.execute("""
                SELECT id_rol
                FROM rol
                WHERE nombre_rol = 'CONSULTA'
                LIMIT 1
            """)

            rol = cursor.fetchone()

            if rol is None:
                raise RuntimeError("No existe el rol CONSULTA.")

            # Verificar duplicados.
            cursor.execute("""
                SELECT nombre_usuario, correo_electronico
                FROM usuario
                WHERE nombre_usuario = %s
                   OR correo_electronico = %s
                LIMIT 1
            """, (nombre, correo))

            if cursor.fetchone():
                return render_template(
                    "registro.html",
                    errores=[
                        "El nombre de usuario o correo ya está registrado."
                    ],
                    datos=datos
                ), 400

            hash_contrasena = generate_password_hash(contrasena)

            cursor.execute("""
                INSERT INTO usuario (
                    nombre_usuario,
                    correo_electronico,
                    contrasena_hash,
                    id_rol,
                    codigo_empleado,
                    estado_usuario
                )
                VALUES (%s, %s, %s, %s, NULL, 'ACTIVO')
            """, (
                nombre,
                correo,
                hash_contrasena,
                rol["id_rol"]
            ))

            conexion.commit()

            flash(
                "Tu cuenta se creó correctamente. Ya puedes iniciar sesión.",
                "success"
            )

            return redirect(url_for("login"))

        except mysql.connector.IntegrityError:
            if conexion is not None:
                conexion.rollback()

            return render_template(
                "registro.html",
                errores=["El nombre de usuario o correo ya está registrado."],
                datos=datos
            ), 400

        except Exception:
            if conexion is not None:
                conexion.rollback()

            app.logger.exception("Error durante el registro de usuarios")

            return render_template(
                "registro.html",
                errores=["No fue posible crear la cuenta. Inténtalo nuevamente."],
                datos=datos
            ), 500

        finally:
            if cursor is not None:
                cursor.close()

            if conexion is not None and conexion.is_connected():
                conexion.close()

    return render_template(
        "registro.html",
        errores=[],
        datos={},
        turnstile_site_key=os.environ["TURNSTILE_SITE_KEY"]
    )

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        # Obtener el token de Cloudflare Turnstile
        token = request.form.get(
            "cf-turnstile-response", ""
        )

        # Verificar el CAPTCHA una sola vez
        if not verificar_captcha(token):
            return (
                "No se pudo verificar el CAPTCHA. "
                "Inténtalo nuevamente.",
                400
            )

        # Obtener los datos del formulario
        nombre_usuario = request.form.get(
            "nombre_usuario", ""
        ).strip()

        contrasena = request.form.get(
            "contrasena", ""
        )

        conexion = None
        cursor = None

        try:
            conexion = conectar_bd()
            cursor = conexion.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT
                    u.id_usuario,
                    u.nombre_usuario,
                    u.contrasena_hash,
                    u.estado_usuario,
                    u.codigo_empleado,
                    r.nombre_rol
                FROM usuario AS u
                INNER JOIN rol AS r
                    ON u.id_rol = r.id_rol
                WHERE u.nombre_usuario = %s
                LIMIT 1
                """,
                (nombre_usuario,)
            )

            usuario = cursor.fetchone()

            if (
                usuario is None
                or usuario["estado_usuario"] != "ACTIVO"
                or not check_password_hash(
                    usuario["contrasena_hash"],
                    contrasena
                )
            ):
                return (
                    "Usuario o contraseña incorrectos, "
                    "o cuenta no disponible.",
                    401
                )

            session.clear()

            session["id_usuario"] = usuario["id_usuario"]
            session["nombre_usuario"] = usuario["nombre_usuario"]
            session["rol"] = usuario["nombre_rol"]
            session["codigo_empleado"] = usuario["codigo_empleado"]

            cursor.execute(
                """
                UPDATE usuario
                SET ultimo_acceso = NOW()
                WHERE id_usuario = %s
                """,
                (usuario["id_usuario"],)
            )

            conexion.commit()

            
            if usuario["nombre_rol"] == "ADMINISTRADOR":
                return redirect(url_for("inicio"))

            elif usuario["nombre_rol"] == "EMPLEADO":
                return redirect(url_for("panel_empleado"))

            else:
                return redirect(url_for("panel_usuario"))



        except mysql.connector.Error:
            app.logger.exception(
                "Error de MySQL durante el inicio de sesión"
            )
            return "No se pudo iniciar sesión.", 500

        finally:
            if cursor is not None:
                cursor.close()

            if conexion is not None and conexion.is_connected():
                conexion.close()

    return render_template(
        "login.html",
        turnstile_site_key=os.environ["TURNSTILE_SITE_KEY"]
    )



@app.route("/mi-panel")
@requiere_rol("CONSULTA", "EMPLEADO", "ADMINISTRADOR")
def panel_usuario():

    if session["rol"] == "ADMINISTRADOR":
        return redirect(url_for("inicio"))

    if session["rol"] == "EMPLEADO":
        return redirect(url_for("panel_empleado"))

    return render_template(
        "mi_panel.html",
        nombre_usuario=session["nombre_usuario"],
        rol=session["rol"]
    )


@app.route("/empleado/mis-novedades")
@requiere_rol("EMPLEADO")
def mis_novedades_laborales():

    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                n.id_novedad,
                tn.nombre_tipo,
                n.fecha_inicio,
                n.fecha_fin,
                n.cantidad_dias,
                n.observacion
            FROM novedad AS n
            INNER JOIN nomina AS nom
                ON n.id_nomina = nom.id_nomina
            INNER JOIN tipo_novedad AS tn
                ON n.id_tipo_novedad = tn.id_tipo_novedad
            INNER JOIN usuario AS u
                ON nom.codigo_empleado = u.codigo_empleado
            WHERE u.id_usuario = %s
            ORDER BY
                n.fecha_inicio DESC,
                n.id_novedad DESC
            """,
            (session["id_usuario"],)
        )

        novedades = cursor.fetchall()

        return render_template(
            "mis_novedades_laborales.html",
            novedades=novedades
        )

    except mysql.connector.Error:
        app.logger.exception(
            "Error al consultar las novedades laborales"
        )
        return "No se pudieron cargar tus novedades laborales.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


@app.route("/empleado/mis-solicitudes", methods=["GET", "POST"])
@requiere_rol("EMPLEADO")
def mis_solicitudes():

    conexion = None
    cursor = None

    tipos_permitidos = (
        "VACACIONES",
        "PERMISO LABORAL",
        "LICENCIA",
        "CERTIFICADO LABORAL",
        "OTRA"
    )

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor(dictionary=True)

        if request.method == "POST":

            tipo = request.form.get(
                "tipo_solicitud", ""
            ).strip()

            titulo = request.form.get(
                "titulo", ""
            ).strip()

            descripcion = request.form.get(
                "descripcion", ""
            ).strip()

            if (
                tipo not in tipos_permitidos
                or not titulo
                or not descripcion
                or len(titulo) > 150
                or len(descripcion) > 5000
            ):
                flash(
                    "Verifica los datos de la solicitud.",
                    "error"
                )
                return redirect(
                    url_for("mis_solicitudes")
                )

            cursor.execute(
                """
                INSERT INTO solicitud (
                    id_usuario_solicitante,
                    tipo_solicitud,
                    titulo,
                    descripcion
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    session["id_usuario"],
                    tipo,
                    titulo,
                    descripcion
                )
            )

            conexion.commit()

            flash(
                "Tu solicitud se registró correctamente.",
                "success"
            )

            return redirect(
                url_for("mis_solicitudes")
            )

        cursor.execute(
            """
            SELECT
                id_solicitud,
                tipo_solicitud,
                titulo,
                descripcion,
                estado,
                prioridad,
                respuesta,
                fecha_creacion,
                fecha_actualizacion,
                fecha_cierre
            FROM solicitud
            WHERE id_usuario_solicitante = %s
            ORDER BY fecha_creacion DESC, id_solicitud DESC
            """,
            (session["id_usuario"],)
        )

        solicitudes = cursor.fetchall()

        return render_template(
            "mis_solicitudes.html",
            solicitudes=solicitudes
        )

    except mysql.connector.Error:
        if conexion is not None:
            conexion.rollback()

        app.logger.exception(
            "Error al gestionar las solicitudes"
        )

        return "No se pudieron gestionar tus solicitudes.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


@app.route("/empleado/mis-datos")
@requiere_rol("EMPLEADO")
def mis_datos_laborales():

    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                e.codigo_empleado,
                e.nombre_empleado,
                e.documento,
                e.fecha_nacimiento,
                e.direccion,
                e.telefono,
                e.correo,
                e.fecha_ingreso_empresa,
                e.estado_empleado
            FROM empleado AS e
            INNER JOIN usuario AS u
                ON e.codigo_empleado = u.codigo_empleado
            WHERE u.id_usuario = %s
            """,
            (session["id_usuario"],)
        )

        empleado = cursor.fetchone()

        # Consultar el cargo y la dependencia actual
        cursor.execute(
            """
            SELECT
                c.nombre_cargo,
                d.nombre_dependencia,
                h.fecha_inicio AS fecha_inicio_cargo
            FROM empleado_historial_laboral AS h
            INNER JOIN cargo AS c
                ON h.id_cargo = c.id_cargo
            INNER JOIN dependencia AS d
                ON h.id_dependencia = d.id_dependencia
            INNER JOIN usuario AS u
                ON h.codigo_empleado = u.codigo_empleado
            WHERE u.id_usuario = %s
              AND h.fecha_fin IS NULL
            ORDER BY h.fecha_inicio DESC,
                     h.id_historial_laboral DESC
            LIMIT 1
            """,
            (session["id_usuario"],)
        )

        cargo_actual = cursor.fetchone()

        # Consultar la EPS actual del empleado
        cursor.execute(
            """
            SELECT
                eps.nombre_eps,
                h.fecha_inicio AS fecha_inicio_eps
            FROM empleado_historial_eps AS h
            INNER JOIN eps
                ON h.id_eps = eps.id_eps
            INNER JOIN usuario AS u
                ON h.codigo_empleado = u.codigo_empleado
            WHERE u.id_usuario = %s
              AND h.fecha_fin IS NULL
              AND h.fecha_inicio <= CURDATE()
            ORDER BY h.fecha_inicio DESC,
                     h.id_historial_eps DESC
            LIMIT 1
            """,
            (session["id_usuario"],)
        )

        eps_actual = cursor.fetchone()

        # Consultar la ARL actual del empleado
        cursor.execute(
            """
            SELECT
                arl.nombre_arl,
                h.fecha_inicio AS fecha_inicio_arl
            FROM empleado_historial_arl AS h
            INNER JOIN arl
                ON h.id_arl = arl.id_arl
            INNER JOIN usuario AS u
                ON h.codigo_empleado = u.codigo_empleado
            WHERE u.id_usuario = %s
              AND h.fecha_fin IS NULL
              AND h.fecha_inicio <= CURDATE()
            ORDER BY h.fecha_inicio DESC,
                     h.id_historial_arl DESC
            LIMIT 1
            """,
            (session["id_usuario"],)
        )

        arl_actual = cursor.fetchone()

        if empleado is None:
            return (
                "Tu cuenta no tiene información laboral asociada.",
                404
            )

        return render_template(
            "mis_datos_laborales.html",
            empleado=empleado,
            cargo_actual=cargo_actual,
            eps_actual=eps_actual,
            arl_actual=arl_actual
        )

    except mysql.connector.Error:
        app.logger.exception(
            "Error al consultar los datos laborales"
        )
        return "No se pudieron cargar tus datos laborales.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()

@app.route("/empleado")
@requiere_rol("EMPLEADO")
def panel_empleado():
    return render_template(
        "panel_empleado.html",
        nombre_usuario=session["nombre_usuario"],
        rol=session["rol"]
    )
    if "id_usuario" not in session:
        return redirect(url_for("login"))

    return render_template(
        "mi_panel.html",
        nombre_usuario=session["nombre_usuario"],
        rol=session["rol"]
    )



@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))





@app.route("/libros")
def catalogo_libros():
    busqueda = request.args.get("q", "").strip()

    try:
        pagina = int(request.args.get("pagina", 1))
    except (ValueError, TypeError):
        pagina = 1

    pagina = max(1, pagina)

    por_pagina = 12
    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor(dictionary=True)

        filtro = ""
        parametros = ()

        if busqueda:
            filtro = """
                WHERE l.titulo LIKE %s
                   OR EXISTS (
                       SELECT 1
                       FROM libro_autor AS la2
                       INNER JOIN autor AS a2
                           ON la2.id_autor = a2.id_autor
                       WHERE la2.id_libro = l.id_libro
                         AND a2.nombre_autor LIKE %s
                   )
            """

            termino = f"%{busqueda}%"
            parametros = (termino, termino)

        # Contar todos los libros que coinciden
        consulta_total = f"""
            SELECT COUNT(*) AS total
            FROM libro AS l
            {filtro}
        """

        cursor.execute(consulta_total, parametros)
        total_libros = cursor.fetchone()["total"]

        total_paginas = max(
            1,
            (total_libros + por_pagina - 1) // por_pagina
        )

        # Evitar páginas fuera del rango
        pagina = min(pagina, total_paginas)

        desplazamiento = (pagina - 1) * por_pagina

        # Consultar solamente los libros de la página
        consulta = f"""
            SELECT
                l.id_libro,
                l.titulo,
                l.rating_promedio,
                l.numero_paginas,
                l.fecha_publicacion,
                GROUP_CONCAT(
                    DISTINCT a.nombre_autor
                    ORDER BY a.nombre_autor
                    SEPARATOR ', '
                ) AS autores
            FROM libro AS l
            LEFT JOIN libro_autor AS la
                ON l.id_libro = la.id_libro
            LEFT JOIN autor AS a
                ON la.id_autor = a.id_autor
            {filtro}
            GROUP BY
                l.id_libro,
                l.titulo,
                l.rating_promedio,
                l.numero_paginas,
                l.fecha_publicacion
            ORDER BY l.id_libro ASC
            LIMIT %s OFFSET %s
        """

        cursor.execute(
            consulta,
            parametros + (por_pagina, desplazamiento)
        )

        libros = cursor.fetchall()

        return render_template(
            "libros.html",
            libros=libros,
            busqueda=busqueda,
            pagina=pagina,
            total_paginas=total_paginas,
            total_libros=total_libros
        )

    except mysql.connector.Error:
        app.logger.exception(
            "Error al consultar el catálogo de libros"
        )
        return "No se pudo cargar el catálogo de libros.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


@app.route("/libros/<int:id_libro>")
def detalle_libro(id_libro):
    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor(dictionary=True)

        consulta = """
            SELECT
                l.id_libro,
                l.titulo,
                l.rating_promedio,
                l.numero_paginas,
                l.fecha_publicacion,
                l.isbn,
                l.isbn13,
                l.cantidad_ratings,
                l.cantidad_resenas,
                GROUP_CONCAT(
                    DISTINCT a.nombre_autor
                    ORDER BY a.nombre_autor
                    SEPARATOR ', '
                ) AS autores
            FROM libro AS l
            LEFT JOIN libro_autor AS la
                ON l.id_libro = la.id_libro
            LEFT JOIN autor AS a
                ON la.id_autor = a.id_autor
            WHERE l.id_libro = %s
            GROUP BY
                l.id_libro,
                l.titulo,
                l.rating_promedio,
                l.numero_paginas,
                l.fecha_publicacion,
                l.isbn,
                l.isbn13,
                l.cantidad_ratings,
                l.cantidad_resenas
        """

        cursor.execute(consulta, (id_libro,))
        libro = cursor.fetchone()

        if libro is None:
            return "El libro solicitado no existe.", 404

        # Registrar la consulta del libro si el usuario inició sesión
        if session.get("id_usuario"):
            cursor.execute(
                """
                INSERT INTO historial_consulta (
                    id_usuario,
                    id_libro,
                    id_pelicula,
                    fecha_consulta
                )
                VALUES (%s, %s, NULL, NOW())
                """,
                (session["id_usuario"], id_libro)
            )

            conexion.commit()

        es_favorito = False

        if session.get("id_usuario"):
            cursor.execute(
                """
                SELECT id_favorito
                FROM favorito
                WHERE id_usuario = %s
                  AND id_libro = %s
                LIMIT 1
                """,
                (session["id_usuario"], id_libro)
            )

            es_favorito = cursor.fetchone() is not None

        cursor.execute(
            """
            SELECT
                r.id_resena,
                r.id_usuario,
                r.calificacion,
                r.comentario,
                r.fecha_publicacion,
                u.nombre_usuario
            FROM resena AS r
            INNER JOIN usuario AS u
                ON r.id_usuario = u.id_usuario
            WHERE r.id_libro = %s
            ORDER BY r.fecha_publicacion DESC
            """,
            (id_libro,)
        )

        resenas = cursor.fetchall()

        ya_reseno = False

        
        ya_reseno = False

        if session.get("id_usuario"):
            ya_reseno = any(
                resena["id_usuario"] == session["id_usuario"]
                for resena in resenas
            )

        return render_template(
            "detalle_libro.html",
            libro=libro,
            es_favorito=es_favorito,
            resenas=resenas,
            ya_reseno=ya_reseno
        )

    except mysql.connector.Error:
        app.logger.exception(
            "Error al consultar los detalles del libro"
        )
        return "No se pudo cargar el libro.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


@app.route("/libros/<int:id_libro>/resenas/agregar", methods=["POST"])
def agregar_resena_libro(id_libro):

    if not session.get("id_usuario"):
        return redirect(url_for("login"))

    calificacion_texto = request.form.get("calificacion", "")
    comentario = request.form.get("comentario", "").strip()

    try:
        calificacion = int(calificacion_texto)
    except (ValueError, TypeError):
        return "La calificación no es válida.", 400

    if calificacion < 1 or calificacion > 5:
        return "La calificación debe estar entre 1 y 5.", 400

    if not comentario or len(comentario) > 2000:
        return "El comentario debe tener entre 1 y 2000 caracteres.", 400

    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor(dictionary=True)

        cursor.execute(
            "SELECT id_libro FROM libro WHERE id_libro = %s",
            (id_libro,)
        )

        if cursor.fetchone() is None:
            return "El libro solicitado no existe.", 404

        cursor.execute(
            """
            SELECT id_resena
            FROM resena
            WHERE id_usuario = %s
              AND id_libro = %s
            LIMIT 1
            """,
            (session["id_usuario"], id_libro)
        )

        if cursor.fetchone() is not None:
            return "Ya has publicado una reseña de este libro.", 409

        cursor.execute(
            """
            INSERT INTO resena (
                id_usuario,
                id_libro,
                id_pelicula,
                calificacion,
                comentario
            )
            VALUES (%s, %s, NULL, %s, %s)
            """,
            (
                session["id_usuario"],
                id_libro,
                calificacion,
                comentario
            )
        )

        conexion.commit()

        return redirect(
            url_for("detalle_libro", id_libro=id_libro)
        )

    except mysql.connector.Error:
        if conexion is not None:
            conexion.rollback()

        app.logger.exception(
            "Error al guardar la reseña del libro"
        )

        return "No se pudo guardar la reseña.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()

@app.route("/favoritos/libros/<int:id_libro>/agregar", methods=["POST"])
def agregar_libro_favorito(id_libro):

    if "id_usuario" not in session:
        return redirect(url_for("login"))

    id_usuario = session["id_usuario"]

    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor()

        consulta = """
            INSERT INTO favorito (
                id_usuario,
                id_libro,
                id_pelicula,
                fecha_guardado
            )
            VALUES (%s, %s, NULL, NOW())
        """

        cursor.execute(
            consulta,
            (id_usuario, id_libro)
        )

        conexion.commit()

    except mysql.connector.IntegrityError:
        if conexion is not None:
            conexion.rollback()

    except mysql.connector.Error:
        if conexion is not None:
            conexion.rollback()

        app.logger.exception(
            "Error al guardar el libro favorito"
        )

        return "No se pudo guardar el favorito.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()

    return redirect(
        url_for("detalle_libro", id_libro=id_libro)
    )


@app.route("/favoritos/peliculas/<int:id_pelicula>/agregar", methods=["POST"])
def agregar_pelicula_favorita(id_pelicula):

    if "id_usuario" not in session:
        return redirect(url_for("login"))

    id_usuario = session["id_usuario"]

    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor()

        consulta = """
            INSERT INTO favorito (
                id_usuario,
                id_libro,
                id_pelicula,
                fecha_guardado
            )
            VALUES (%s, NULL, %s, NOW())
        """

        cursor.execute(
            consulta,
            (id_usuario, id_pelicula)
        )

        conexion.commit()

    except mysql.connector.IntegrityError:
        if conexion is not None:
            conexion.rollback()

    except mysql.connector.Error:
        if conexion is not None:
            conexion.rollback()

        app.logger.exception(
            "Error al guardar la película favorita"
        )

        return "No se pudo guardar la película.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()

    return redirect(
        url_for("detalle_pelicula", id_pelicula=id_pelicula)
    )


@app.route("/favoritos/peliculas/<int:id_pelicula>/quitar", methods=["POST"])
def quitar_pelicula_favorita(id_pelicula):

    if "id_usuario" not in session:
        return redirect(url_for("login"))

    id_usuario = session["id_usuario"]

    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor()

        consulta = """
            DELETE FROM favorito
            WHERE id_usuario = %s
              AND id_pelicula = %s
        """

        cursor.execute(
            consulta,
            (id_usuario, id_pelicula)
        )

        conexion.commit()

    except mysql.connector.Error:
        if conexion is not None:
            conexion.rollback()

        app.logger.exception(
            "Error al quitar la película de favoritos"
        )

        return "No se pudo quitar la película de favoritos.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()

 
    if request.form.get("origen") == "mis_favoritos":
        return redirect(url_for("mis_favoritos"))

    return redirect(
        url_for("detalle_pelicula", id_pelicula=id_pelicula)
    )

@app.route("/favoritos/libros/<int:id_libro>/quitar", methods=["POST"])
def quitar_libro_favorito(id_libro):

    if "id_usuario" not in session:
        return redirect(url_for("login"))

    id_usuario = session["id_usuario"]

    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor()

        consulta = """
            DELETE FROM favorito
            WHERE id_usuario = %s
              AND id_libro = %s
        """

        cursor.execute(
            consulta,
            (id_usuario, id_libro)
        )

        conexion.commit()

    except mysql.connector.Error:
        if conexion is not None:
            conexion.rollback()

        app.logger.exception(
            "Error al quitar el libro de favoritos"
        )

        return "No se pudo quitar el favorito.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


    if request.form.get("origen") == "mis_favoritos":
        return redirect(url_for("mis_favoritos"))

    return redirect(
        url_for("detalle_libro", id_libro=id_libro)
    )


@app.route("/reportar-problema", methods=["GET", "POST"])
@requiere_rol("CONSULTA", "EMPLEADO", "ADMINISTRADOR")
def reportar_problema():

    if request.method == "POST":

        asunto = request.form.get("asunto", "").strip()
        descripcion = request.form.get("descripcion", "").strip()

        # Validar los datos del formulario
        if not asunto or len(asunto) > 150:
            return "El asunto debe tener entre 1 y 150 caracteres.", 400

        if not descripcion or len(descripcion) > 3000:
            return "La descripción debe tener entre 1 y 3000 caracteres.", 400

        conexion = None
        cursor = None

        try:
            conexion = conectar_bd()
            cursor = conexion.cursor()

            cursor.execute(
                """
                INSERT INTO reporte_problema (
                    id_usuario,
                    asunto,
                    descripcion
                )
                VALUES (%s, %s, %s)
                """,
                (
                    session["id_usuario"],
                    asunto,
                    descripcion
                )
            )

            conexion.commit()

            return redirect(
                url_for("reportar_problema", enviado=1)
            )

        except mysql.connector.Error:
            if conexion is not None:
                conexion.rollback()

            app.logger.exception(
                "Error al guardar el reporte de problema"
            )

            return "No se pudo enviar el reporte.", 500

        finally:
            if cursor is not None:
                cursor.close()

            if conexion is not None and conexion.is_connected():
                conexion.close()

    enviado = request.args.get("enviado") == "1"

    return render_template(
        "reportar_problema.html",
        enviado=enviado
    )

@app.route("/mi-historial")
@requiere_rol("CONSULTA", "EMPLEADO", "ADMINISTRADOR")
def mi_historial():
    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                h.id_consulta,
                h.id_libro,
                h.id_pelicula,
                h.fecha_consulta,
                CASE
                    WHEN h.id_libro IS NOT NULL THEN 'Libro'
                    ELSE 'Película'
                END AS tipo_contenido,
                COALESCE(l.titulo, p.titulo) AS titulo
            FROM historial_consulta AS h
            LEFT JOIN libro AS l
                ON h.id_libro = l.id_libro
            LEFT JOIN pelicula AS p
                ON h.id_pelicula = p.id_pelicula
            WHERE h.id_usuario = %s
            ORDER BY h.fecha_consulta DESC, h.id_consulta DESC
            LIMIT 100
            """,
            (session["id_usuario"],)
        )

        historial = cursor.fetchall()

        return render_template(
            "mi_historial.html",
            historial=historial
        )

    except mysql.connector.Error:
        app.logger.exception("Error al consultar el historial")
        return "No se pudo cargar el historial.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()

@app.route("/mis-favoritos")
def mis_favoritos():

    if "id_usuario" not in session:
        return redirect(url_for("login"))

    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                f.id_favorito,
                f.id_libro,
                l.titulo AS titulo_libro,
                f.id_pelicula,
                p.titulo AS titulo_pelicula,
                f.fecha_guardado
            FROM favorito AS f
            LEFT JOIN libro AS l
                ON f.id_libro = l.id_libro
            LEFT JOIN pelicula AS p
                ON f.id_pelicula = p.id_pelicula
            WHERE f.id_usuario = %s
            ORDER BY f.fecha_guardado DESC
            """,
            (session["id_usuario"],)
        )

        favoritos = cursor.fetchall()

    except mysql.connector.Error:
        app.logger.exception("Error al consultar los favoritos")
        return "No se pudieron cargar los favoritos.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()

    return render_template(
        "mis_favoritos.html",
        favoritos=favoritos
    )

@app.route("/peliculas")
def catalogo_peliculas():
    busqueda = request.args.get("q", "").strip()

    traducciones_generos = {
        "Action": "Acción",
        "Adventure": "Aventura",
        "Animation": "Animación",
        "Children": "Infantil",
        "Comedy": "Comedia",
        "Crime": "Crimen",
        "Documentary": "Documental",
        "Drama": "Drama",
        "Fantasy": "Fantasía",
        "Film-Noir": "Cine negro",
        "Horror": "Terror",
        "IMAX": "IMAX",
        "Musical": "Musical",
        "Mystery": "Misterio",
        "Romance": "Romance",
        "Sci-Fi": "Ciencia ficción",
        "Thriller": "Suspenso",
        "War": "Bélico",
        "Western": "Oeste",
        "(no genres listed)": "Sin género",
        "Genero de prueba": "Género de prueba"
    }

    # Permitir buscar géneros en español o inglés
    busqueda_sql = busqueda

    for ingles, espanol in traducciones_generos.items():
        if busqueda.casefold() == espanol.casefold():
            busqueda_sql = ingles
            break


    try:
        pagina = int(request.args.get("pagina", 1))
    except (ValueError, TypeError):
        pagina = 1

    pagina = max(1, pagina)
    por_pagina = 12

    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor(dictionary=True)

        filtro = ""
        parametros = ()

        if busqueda:
            filtro = """
                WHERE p.titulo LIKE %s
                   OR EXISTS (
                       SELECT 1
                       FROM pelicula_genero AS pg2
                       INNER JOIN genero AS g2
                           ON pg2.id_genero = g2.id_genero
                       WHERE pg2.id_pelicula = p.id_pelicula
                         AND g2.nombre_genero LIKE %s
                   )
            """

            termino = f"%{busqueda_sql}%"
            parametros = (termino, termino)

        # Contar las películas que coinciden
        consulta_total = f"""
            SELECT COUNT(*) AS total
            FROM pelicula AS p
            {filtro}
        """

        cursor.execute(consulta_total, parametros)
        total_peliculas = cursor.fetchone()["total"]

        total_paginas = max(
            1,
            (total_peliculas + por_pagina - 1) // por_pagina
        )

        pagina = min(pagina, total_paginas)
        desplazamiento = (pagina - 1) * por_pagina

        # Obtener las películas de la página actual
        consulta = f"""
            SELECT
                p.id_pelicula,
                p.titulo,
                p.anio_lanzamiento,
                GROUP_CONCAT(
                    DISTINCT g.nombre_genero
                    ORDER BY g.nombre_genero
                    SEPARATOR ', '
                ) AS generos
            FROM pelicula AS p
            LEFT JOIN pelicula_genero AS pg
                ON p.id_pelicula = pg.id_pelicula
            LEFT JOIN genero AS g
                ON pg.id_genero = g.id_genero
            {filtro}
            GROUP BY
                p.id_pelicula,
                p.titulo,
                p.anio_lanzamiento
            ORDER BY p.id_pelicula ASC
            LIMIT %s OFFSET %s
        """

        cursor.execute(
            consulta,
            parametros + (por_pagina, desplazamiento)
        )

        peliculas = cursor.fetchall()

        for pelicula in peliculas:
            if pelicula["generos"]:
                lista_generos = pelicula["generos"].split(", ")

                generos_espanol = [
                    traducciones_generos.get(genero, genero)
                    for genero in lista_generos
                ]

                pelicula["generos"] = ", ".join(generos_espanol)

        return render_template(
            "peliculas.html",
            peliculas=peliculas,
            busqueda=busqueda,
            pagina=pagina,
            total_paginas=total_paginas,
            total_peliculas=total_peliculas
        )

    except mysql.connector.Error:
        app.logger.exception(
            "Error al consultar el catálogo de películas"
        )
        return "No se pudo cargar el catálogo de películas.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


@app.route("/peliculas/<int:id_pelicula>")
def detalle_pelicula(id_pelicula):
    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor(dictionary=True)

        consulta = """
            SELECT
                p.id_pelicula,
                p.titulo,
                p.anio_lanzamiento,
                GROUP_CONCAT(
                    DISTINCT g.nombre_genero
                    ORDER BY g.nombre_genero
                    SEPARATOR ', '
                ) AS generos
            FROM pelicula AS p
            LEFT JOIN pelicula_genero AS pg
                ON p.id_pelicula = pg.id_pelicula
            LEFT JOIN genero AS g
                ON pg.id_genero = g.id_genero
            WHERE p.id_pelicula = %s
            GROUP BY
                p.id_pelicula,
                p.titulo,
                p.anio_lanzamiento
        """

        cursor.execute(consulta, (id_pelicula,))
        pelicula = cursor.fetchone()

        if pelicula is None:
            return "La película solicitada no existe.", 404

        # Registrar la consulta de la película si el usuario inició sesión
        if session.get("id_usuario"):
            cursor.execute(
                """
                INSERT INTO historial_consulta (
                    id_usuario,
                    id_libro,
                    id_pelicula,
                    fecha_consulta
                )
                VALUES (%s, NULL, %s, NOW())
                """,
                (session["id_usuario"], id_pelicula)
            )

            conexion.commit()

        es_favorita = False

        if session.get("id_usuario"):
            cursor.execute(
                """
                SELECT id_favorito
                FROM favorito
                WHERE id_usuario = %s
                  AND id_pelicula = %s
                LIMIT 1
                """,
                (session["id_usuario"], id_pelicula)
            )

            es_favorita = cursor.fetchone() is not None

        traducciones_generos = {
            "Action": "Acción",
            "Adventure": "Aventura",
            "Animation": "Animación",
            "Children": "Infantil",
            "Comedy": "Comedia",
            "Crime": "Crimen",
            "Documentary": "Documental",
            "Drama": "Drama",
            "Fantasy": "Fantasía",
            "Film-Noir": "Cine negro",
            "Horror": "Terror",
            "IMAX": "IMAX",
            "Musical": "Musical",
            "Mystery": "Misterio",
            "Romance": "Romance",
            "Sci-Fi": "Ciencia ficción",
            "Thriller": "Suspenso",
            "War": "Bélico",
            "Western": "Oeste",
            "(no genres listed)": "Sin género",
            "Genero de prueba": "Género de prueba"
        }

        if pelicula["generos"]:
            lista_generos = pelicula["generos"].split(", ")

            generos_espanol = [
                traducciones_generos.get(genero, genero)
                for genero in lista_generos
            ]

            pelicula["generos"] = ", ".join(generos_espanol)

        
        cursor.execute(
            """
            SELECT
                r.id_resena,
                r.id_usuario,
                r.calificacion,
                r.comentario,
                r.fecha_publicacion,
                u.nombre_usuario
            FROM resena AS r
            INNER JOIN usuario AS u
                ON r.id_usuario = u.id_usuario
            WHERE r.id_pelicula = %s
            ORDER BY r.fecha_publicacion DESC
            """,
            (id_pelicula,)
        )

        resenas = cursor.fetchall()

        ya_reseno = False

        if session.get("id_usuario"):
            ya_reseno = any(
                resena["id_usuario"] == session["id_usuario"]
                for resena in resenas
            )

        return render_template(
            "detalle_pelicula.html",
            pelicula=pelicula,
            es_favorita=es_favorita,
            resenas=resenas,
            ya_reseno=ya_reseno
        )

    except mysql.connector.Error:
        app.logger.exception(
            "Error al consultar los detalles de la película"
        )
        return "No se pudo cargar la película.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


@app.route("/peliculas/<int:id_pelicula>/resenas/agregar", methods=["POST"])
def agregar_resena_pelicula(id_pelicula):

    if not session.get("id_usuario"):
        return redirect(url_for("login"))

    calificacion_texto = request.form.get("calificacion", "")
    comentario = request.form.get("comentario", "").strip()

    try:
        calificacion = int(calificacion_texto)
    except (ValueError, TypeError):
        return "La calificación no es válida.", 400

    if calificacion < 1 or calificacion > 5:
        return "La calificación debe estar entre 1 y 5.", 400

    if not comentario or len(comentario) > 2000:
        return "El comentario debe tener entre 1 y 2000 caracteres.", 400

    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor(dictionary=True)

        cursor.execute(
            "SELECT id_pelicula FROM pelicula WHERE id_pelicula = %s",
            (id_pelicula,)
        )

        if cursor.fetchone() is None:
            return "La película solicitada no existe.", 404

        cursor.execute(
            """
            SELECT id_resena
            FROM resena
            WHERE id_usuario = %s
              AND id_pelicula = %s
            LIMIT 1
            """,
            (session["id_usuario"], id_pelicula)
        )

        if cursor.fetchone() is not None:
            return "Ya has publicado una reseña de esta película.", 409

        cursor.execute(
            """
            INSERT INTO resena (
                id_usuario,
                id_libro,
                id_pelicula,
                calificacion,
                comentario
            )
            VALUES (%s, NULL, %s, %s, %s)
            """,
            (
                session["id_usuario"],
                id_pelicula,
                calificacion,
                comentario
            )
        )

        conexion.commit()

        return redirect(
            url_for("detalle_pelicula", id_pelicula=id_pelicula)
        )

    except mysql.connector.Error:
        if conexion is not None:
            conexion.rollback()

        app.logger.exception(
            "Error al guardar la reseña de la película"
        )

        return "No se pudo guardar la reseña.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()

@app.route("/")
def pagina_publica():
    return render_template("publico.html")

@app.route("/admin/reportes/<int:id_reporte>/estado", methods=["POST"])
@requiere_rol("ADMINISTRADOR")
def actualizar_estado_reporte(id_reporte):

    nuevo_estado = request.form.get("estado", "").strip()

    estados_permitidos = (
        "PENDIENTE",
        "EN_REVISION",
        "RESUELTO",
        "DESCARTADO"
    )

    if nuevo_estado not in estados_permitidos:
        return "El estado seleccionado no es válido.", 400

    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT id_reporte
             FROM reporte_problema
             WHERE id_reporte = %s
            """,
            (id_reporte,)
        )
        reporte = cursor.fetchone()

        if reporte is None:
            return "El reporte solicitado no existe.", 404

        # Actualizar el estado
        cursor.execute(
            """
            UPDATE reporte_problema
            SET estado = %s
            WHERE id_reporte = %s
            """,
             (nuevo_estado, id_reporte)
)   

        conexion.commit()

        return redirect(url_for("admin_reportes"))

    except mysql.connector.Error:
        if conexion is not None:
            conexion.rollback()

        app.logger.exception(
            "Error al actualizar el estado del reporte"
        )

        return "No se pudo actualizar el reporte.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


@app.errorhandler(403)
def acceso_denegado(error):
    return render_template("403.html"), 403

# ADMINISTRACIÓN DE EMPLEADOS
@app.route("/admin/empleados")
@requiere_rol("ADMINISTRADOR")
def admin_empleados():

    conexion = conectar_bd()
    cursor = None

    try:
        cursor = conexion.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                e.codigo_empleado,
                e.nombre_empleado,
                e.documento,
                e.correo,
                e.telefono,
                e.fecha_ingreso_empresa,
                e.estado_empleado,
                c.nombre_cargo AS cargo_actual,
                d.nombre_dependencia AS dependencia_actual,
                hl.fecha_inicio AS fecha_inicio_cargo

            FROM empleado AS e

            LEFT JOIN empleado_historial_laboral AS hl
                ON e.codigo_empleado = hl.codigo_empleado
                AND hl.fecha_fin IS NULL

            LEFT JOIN cargo AS c
                ON hl.id_cargo = c.id_cargo

            LEFT JOIN dependencia AS d
                ON hl.id_dependencia = d.id_dependencia

            ORDER BY e.nombre_empleado ASC
        """)

        empleados = cursor.fetchall()

        return render_template(
            "admin_empleados.html",
            empleados=empleados
        )

    except Exception as error:
        print("Error al consultar empleados:", error)
        flash("No fue posible cargar los empleados.", "error")
        return redirect(url_for("inicio"))

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None:
            conexion.close()

# ACTIVAR / DESACTIVAR EMPLEADOS
@app.route(
    "/admin/empleados/<codigo_empleado>/estado",
    methods=["POST"]
)
@requiere_rol("ADMINISTRADOR")
def cambiar_estado_empleado(codigo_empleado):

    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor(dictionary=True)

        # Consultar el estado actual
        cursor.execute("""
            SELECT codigo_empleado, estado_empleado
            FROM empleado
            WHERE codigo_empleado = %s
        """, (codigo_empleado,))

        empleado = cursor.fetchone()

        if empleado is None:
            flash("El empleado no existe.", "error")
            return redirect(url_for("admin_empleados"))

        # Alternar entre ACTIVO e INACTIVO
        estado_actual = empleado["estado_empleado"]

        if estado_actual == "ACTIVO":
            nuevo_estado = "INACTIVO"
        elif estado_actual == "INACTIVO":
            nuevo_estado = "ACTIVO"
        else:
            flash("El empleado tiene un estado no reconocido.", "error")
            return redirect(url_for("admin_empleados"))

        cursor.execute("""
            UPDATE empleado
            SET estado_empleado = %s
            WHERE codigo_empleado = %s
        """, (nuevo_estado, codigo_empleado))

        conexion.commit()

        flash(
            f"El empleado ahora está {nuevo_estado.lower()}.",
            "success"
        )

    except Exception as error:
        if conexion is not None:
            conexion.rollback()

        print("Error al cambiar estado del empleado:", error)
        flash("No fue posible actualizar el estado.", "error")

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None:
            conexion.close()

    return redirect(url_for("admin_empleados"))

# FORMULARIO DE REGISTRO DE EMPLEADOS
@app.route("/admin/empleados/nuevo", methods=["GET", "POST"])
@requiere_rol("ADMINISTRADOR")
def nuevo_empleado():

    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor(dictionary=True)

        if request.method == "POST":
            print("POST RECIBIDO: procesando registro de empleado", flush=True)

            codigo = request.form.get("codigo_empleado", "").strip()
            nombre = request.form.get("nombre_empleado", "").strip()
            documento = request.form.get("documento", "").strip() or None
            correo = request.form.get("correo", "").strip() or None
            telefono = request.form.get("telefono", "").strip() or None
            direccion = request.form.get("direccion", "").strip() or None

            fecha_nacimiento = (
                request.form.get("fecha_nacimiento", "").strip() or None
            )

            fecha_ingreso = request.form.get(
                "fecha_ingreso_empresa", ""
            ).strip()

            estado = request.form.get("estado_empleado", "").strip()

            id_cargo = request.form.get("id_cargo", "").strip()
            id_dependencia = request.form.get(
                "id_dependencia", ""
            ).strip()

            # VALIDACIONES DE FORMATO

            errores = []

            if not re.fullmatch(r"[A-Za-z0-9-]{2,30}", codigo):
                errores.append(
                    "El código debe tener entre 2 y 30 caracteres "
                    "y contener únicamente letras, números o guiones."
                )

            if not re.fullmatch(
                r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ .'-]{3,150}",
                nombre
            ):
                errores.append(
                    "El nombre debe contener entre 3 y 150 caracteres "
                    "y utilizar únicamente letras y signos permitidos."
                )

            if documento and not re.fullmatch(r"[0-9]{5,15}", documento):
                errores.append(
                    "El documento debe contener entre 5 y 15 dígitos."
                )
            if correo and (
                len(correo) > 120
                or not re.fullmatch(
                    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
                    correo
                )
            ):
                errores.append(
                    "El correo electrónico no tiene un formato válido. "
                    "Ejemplo: usuario@empresa.com."
                )
            if telefono and not re.fullmatch(
                r"\+?[0-9]{7,15}",
                telefono
            ):
                errores.append(
                    "El teléfono debe contener entre 7 y 15 números, "
                    "con + opcional al inicio."
                )

            if direccion and not re.fullmatch(
                r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 #.,°º/-]{1,180}",
                direccion
            ):
                errores.append(
                    "La dirección contiene caracteres no permitidos."
                )
            if errores:
                print("=== REGISTRO RECHAZADO ===", flush=True)

                for mensaje in errores:
                    print("ERROR:", mensaje, flush=True)
                    flash(mensaje, "error")

                print("=========================", flush=True)

                return redirect(url_for("nuevo_empleado"))
            # Validar campos obligatorios
            if not all([
                codigo, nombre, fecha_ingreso,
                estado, id_cargo, id_dependencia
            ]):
                flash("Completa todos los campos obligatorios.", "error")
                return redirect(url_for("nuevo_empleado"))

            if estado not in ("ACTIVO", "INACTIVO"):
                flash("El estado seleccionado no es válido.", "error")
                return redirect(url_for("nuevo_empleado"))

            # Validar fechas
            from datetime import date

            try:
                ingreso = date.fromisoformat(fecha_ingreso)

                if fecha_nacimiento:
                    nacimiento = date.fromisoformat(fecha_nacimiento)

                    if nacimiento > ingreso:
                        raise ValueError("Fecha de nacimiento inválida")

                if ingreso > date.today():
                    raise ValueError("Fecha de ingreso futura")

            except ValueError:
                flash("Verifica las fechas ingresadas.", "error")
                return redirect(url_for("nuevo_empleado"))

            # Validar cargo y dependencia
            try:
                id_cargo = int(id_cargo)
                id_dependencia = int(id_dependencia)
            except ValueError:
                flash("Selecciona un cargo y dependencia válidos.", "error")
                return redirect(url_for("nuevo_empleado"))

            cursor.execute(
                "SELECT id_cargo FROM cargo WHERE id_cargo = %s",
                (id_cargo,)
            )

            if cursor.fetchone() is None:
                flash("El cargo seleccionado no existe.", "error")
                return redirect(url_for("nuevo_empleado"))

            cursor.execute(
                """
                SELECT id_dependencia
                FROM dependencia
                WHERE id_dependencia = %s
                """,
                (id_dependencia,)
            )

            if cursor.fetchone() is None:
                flash("La dependencia seleccionada no existe.", "error")
                return redirect(url_for("nuevo_empleado"))

            # Verificar código duplicado
            cursor.execute(
                """
                SELECT codigo_empleado
                FROM empleado
                WHERE codigo_empleado = %s
                """,
                (codigo,)
            )

            if cursor.fetchone():
                flash("Ya existe un empleado con ese código.", "error")
                return redirect(url_for("nuevo_empleado"))

            # Verificar documento duplicado
            if documento:
                cursor.execute(
                    """
                    SELECT codigo_empleado
                    FROM empleado
                    WHERE documento = %s
                    """,
                    (documento,)
                )

                if cursor.fetchone():
                    flash("Ya existe un empleado con ese documento.", "error")
                    return redirect(url_for("nuevo_empleado"))

            # Registrar empleado
            cursor.execute(
                """
                INSERT INTO empleado (
                    codigo_empleado,
                    nombre_empleado,
                    documento,
                    fecha_nacimiento,
                    direccion,
                    telefono,
                    correo,
                    fecha_ingreso_empresa,
                    estado_empleado
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    codigo, nombre, documento,
                    fecha_nacimiento, direccion,
                    telefono, correo, fecha_ingreso,
                    estado
                )
            )

            # Registrar asignación laboral inicial
            cursor.execute(
                """
                INSERT INTO empleado_historial_laboral (
                    codigo_empleado,
                    id_cargo,
                    id_dependencia,
                    fecha_inicio,
                    fecha_fin
                )
                VALUES (%s, %s, %s, %s, NULL)
                """,
                (
                    codigo,
                    id_cargo,
                    id_dependencia,
                    fecha_ingreso
                )
            )

            conexion.commit()
            print("EMPLEADO GUARDADO CORRECTAMENTE", flush=True)
            flash("Empleado registrado correctamente.", "success")
            return redirect(url_for("admin_empleados"))

        # Cargar formulario
        cursor.execute("""
            SELECT id_cargo, nombre_cargo
            FROM cargo
            ORDER BY nombre_cargo
        """)
        cargos = cursor.fetchall()

        cursor.execute("""
            SELECT id_dependencia, nombre_dependencia
            FROM dependencia
            ORDER BY nombre_dependencia
        """)
        dependencias = cursor.fetchall()

        return render_template(
            "admin_empleado_nuevo.html",
            cargos=cargos,
            dependencias=dependencias
        )

    except Exception as error:
        if conexion is not None:
            conexion.rollback()

        print("Error al registrar empleado:", error)
        flash("No fue posible registrar el empleado.", "error")
        return redirect(url_for("admin_empleados"))

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None:
            conexion.close()

@app.route("/admin/reportes")
@requiere_rol("ADMINISTRADOR")
def admin_reportes():
    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                r.id_reporte,
                r.asunto,
                r.descripcion,
                r.estado,
                r.fecha_reporte,
                u.nombre_usuario
            FROM reporte_problema AS r
            INNER JOIN usuario AS u
                ON r.id_usuario = u.id_usuario
            ORDER BY
                r.fecha_reporte DESC,
                r.id_reporte DESC
            """
        )

        reportes = cursor.fetchall()

        return render_template(
            "admin_reportes.html",
            reportes=reportes
        )

    except mysql.connector.Error:
        app.logger.exception(
            "Error al consultar los reportes administrativos"
        )
        return "No se pudieron cargar los reportes.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()

@app.route("/admin/solicitudes")
@requiere_rol("ADMINISTRADOR")
def administrar_solicitudes():

    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                s.id_solicitud,
                s.tipo_solicitud,
                s.titulo,
                s.descripcion,
                s.estado,
                s.prioridad,
                s.respuesta,
                s.fecha_creacion,
                s.fecha_actualizacion,
                u.nombre_usuario AS solicitante
            FROM solicitud AS s
            INNER JOIN usuario AS u
                ON s.id_usuario_solicitante = u.id_usuario
            ORDER BY
                s.fecha_creacion DESC,
                s.id_solicitud DESC
        """)

        solicitudes = cursor.fetchall()

        return render_template(
            "admin_solicitudes.html",
            solicitudes=solicitudes
        )

    except mysql.connector.Error:
        app.logger.exception(
            "Error al consultar las solicitudes administrativas"
        )
        return "No se pudieron cargar las solicitudes.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


@app.route("/admin/solicitudes/<int:id_solicitud>/actualizar", methods=["POST"])
@requiere_rol("ADMINISTRADOR")
def actualizar_solicitud(id_solicitud):

    estados_permitidos = (
        "PENDIENTE",
        "EN_REVISION",
        "REQUIERE_INFORMACION",
        "RESUELTO",
        "RECHAZADO"
    )

    prioridades_permitidas = (
        "BAJA",
        "MEDIA",
        "ALTA"
    )

    estado = request.form.get("estado", "").strip()
    prioridad = request.form.get("prioridad", "").strip()
    respuesta = request.form.get("respuesta", "").strip()

    # Validar los datos recibidos
    if (
        estado not in estados_permitidos
        or prioridad not in prioridades_permitidas
        or len(respuesta) > 5000
    ):
        flash("Verifica los datos de la solicitud.", "error")
        return redirect(url_for("administrar_solicitudes"))

    # Exigir respuesta cuando se toma una decisión
    if estado in ("RESUELTO", "RECHAZADO") and not respuesta:
        flash(
            "Debes escribir una respuesta para finalizar la solicitud.",
            "error"
        )
        return redirect(url_for("administrar_solicitudes"))

    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor()

        cursor.execute(
            """
            UPDATE solicitud
            SET
                estado = %s,
                prioridad = %s,
                respuesta = %s,
                id_usuario_responsable = %s,
                fecha_actualizacion = NOW(),
                fecha_cierre = CASE
                    WHEN %s IN ('RESUELTO', 'RECHAZADO')
                    THEN COALESCE(fecha_cierre, NOW())
                    ELSE NULL
                END
            WHERE id_solicitud = %s
            """,
            (
                estado,
                prioridad,
                respuesta or None,
                session["id_usuario"],
                estado,
                id_solicitud
            )
        )

        if cursor.rowcount == 0:
            conexion.rollback()
            flash("No se encontró la solicitud.", "error")
            return redirect(url_for("administrar_solicitudes"))

        conexion.commit()

        flash(
            "La solicitud se actualizó correctamente.",
            "success"
        )

        return redirect(url_for("administrar_solicitudes"))

    except mysql.connector.Error:
        if conexion is not None:
            conexion.rollback()

        app.logger.exception(
            "Error al actualizar la solicitud %s",
            id_solicitud
        )

        flash(
            "No se pudo actualizar la solicitud.",
            "error"
        )

        return redirect(url_for("administrar_solicitudes"))

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


# REPORTES OFICIALES - ENTRECOL+
@app.route("/admin/reportes/nomina")
@requiere_rol("ADMINISTRADOR")
def reporte_nomina():
    orden = request.args.get("orden", "asc").lower()
    if orden not in ("asc", "desc"):
        orden = "asc"
    dependencia = request.args.get("dependencia", "").strip()
    cargo = request.args.get("cargo", "").strip()
    estado = request.args.get("estado", "").strip().upper()
    if len(dependencia) > 100 or len(cargo) > 100 or estado not in ("", "ACTIVO", "INACTIVO"):
        abort(400)

    conexion = None
    cursor = None
    try:
        conexion = conectar_bd()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT nombre_dependencia FROM dependencia ORDER BY nombre_dependencia")
        dependencias_filtro = [x["nombre_dependencia"] for x in cursor.fetchall()]
        cursor.execute("SELECT nombre_cargo FROM cargo ORDER BY nombre_cargo")
        cargos_filtro = [x["nombre_cargo"] for x in cursor.fetchall()]

        # Una asignación laboral vigente como máximo por empleado.
        # El registro debe cubrir la fecha actual y se prioriza el más reciente.
        cursor.execute("""
            SELECT e.codigo_empleado, e.nombre_empleado, e.estado_empleado,
                   COALESCE(d.nombre_dependencia, 'Sin dependencia') AS nombre_dependencia,
                   COALESCE(c.nombre_cargo, 'Sin cargo') AS nombre_cargo
            FROM empleado e
            LEFT JOIN empleado_historial_laboral hl
              ON hl.id_historial_laboral = (
                SELECT h2.id_historial_laboral
                FROM empleado_historial_laboral h2
                WHERE h2.codigo_empleado = e.codigo_empleado
                  AND h2.fecha_inicio <= CURDATE()
                  AND (h2.fecha_fin IS NULL OR h2.fecha_fin >= CURDATE())
                ORDER BY h2.fecha_inicio DESC, h2.id_historial_laboral DESC
                LIMIT 1
              )
            LEFT JOIN dependencia d ON d.id_dependencia = hl.id_dependencia
            LEFT JOIN cargo c ON c.id_cargo = hl.id_cargo
            WHERE (%s = '' OR d.nombre_dependencia = %s)
              AND (%s = '' OR c.nombre_cargo = %s)
              AND (%s = '' OR e.estado_empleado = %s)
        """, (dependencia, dependencia, cargo, cargo, estado, estado))
        empleados = cursor.fetchall()
        empleados.sort(key=lambda e: (e["nombre_empleado"].casefold(), str(e["codigo_empleado"])),
                       reverse=(orden == "desc"))

        # Derivar tablas y gráficos del mismo conjunto filtrado para que coincidan.
        por_dependencia = {}
        por_cargo = {}
        for e in empleados:
            d = e["nombre_dependencia"]
            c = e["nombre_cargo"]
            por_dependencia[d] = por_dependencia.get(d, 0) + 1
            por_cargo[(d, c)] = por_cargo.get((d, c), 0) + 1
        empleados_por_dependencia = [
            {"nombre_dependencia": d, "total_empleados": n}
            for d, n in sorted(por_dependencia.items(), key=lambda x: (-x[1], x[0]))
        ]
        empleados_por_cargo = [
            {"nombre_dependencia": d, "nombre_cargo": c, "total_empleados": n}
            for (d, c), n in sorted(por_cargo.items())
        ]
        return render_template(
            "reporte_nomina.html", total_empleados=len(empleados),
            empleados=empleados, orden=orden,
            empleados_por_dependencia=empleados_por_dependencia,
            empleados_por_cargo=empleados_por_cargo,
            dependencias_filtro=dependencias_filtro, cargos_filtro=cargos_filtro,
            dependencia_seleccionada=dependencia, cargo_seleccionado=cargo,
            estado_seleccionado=estado
        )
    except mysql.connector.Error:
        app.logger.exception("Error al consultar el reporte de nómina")
        return {"error": "No se pudo generar el reporte."}, 500
    finally:
        if cursor is not None:
            cursor.close()
        if conexion is not None and conexion.is_connected():
            conexion.close()


# PÁGINA PRINCIPAL
@app.route("/admin")
@requiere_rol("ADMINISTRADOR")
def inicio():


    conexion = None
    cursor = None

    try:
        conexion = conectar_bd()
        cursor = conexion.cursor()

        # Tablas y estadísticas del sistema.
        tablas = {
            "total_empleados": "empleado",
            "total_peliculas": "pelicula",
            "total_libros": "libro",
            "total_autores": "autor",
            "total_generos": "genero",
            "total_editoriales": "editorial",
            "total_idiomas": "idioma",
            "total_novedades": "novedad"
        }

        estadisticas = {}

        for nombre, tabla in tablas.items():
            cursor.execute(f"SELECT COUNT(*) FROM `{tabla}`")
            estadisticas[nombre] = cursor.fetchone()[0]

        # ANALÍTICAS DEL CATÁLOGO

        # 1. Los 10 libros más vistos
        cursor.execute("""
            SELECT
                l.titulo,
                COUNT(h.id_consulta) AS total
            FROM historial_consulta AS h
            INNER JOIN libro AS l
                ON h.id_libro = l.id_libro
            GROUP BY l.id_libro, l.titulo
            ORDER BY total DESC, l.titulo ASC
            LIMIT 10
        """)
        libros_mas_vistos = cursor.fetchall()

        # 2. Los 10 libros más agregados a favoritos
        cursor.execute("""
            SELECT
                l.titulo,
                COUNT(f.id_favorito) AS total
            FROM favorito AS f
            INNER JOIN libro AS l
                ON f.id_libro = l.id_libro
            GROUP BY l.id_libro, l.titulo
            ORDER BY total DESC, l.titulo ASC
            LIMIT 10
        """)
        libros_mas_favoritos = cursor.fetchall()

        # 3. Las 10 películas más vistas
        cursor.execute("""
            SELECT
                p.titulo,
                COUNT(h.id_consulta) AS total
            FROM historial_consulta AS h
            INNER JOIN pelicula AS p
                ON h.id_pelicula = p.id_pelicula
            GROUP BY p.id_pelicula, p.titulo
            ORDER BY total DESC, p.titulo ASC
            LIMIT 10
        """)
        peliculas_mas_vistas = cursor.fetchall()

        # 4. Las 10 películas más agregadas a favoritos
        cursor.execute("""
            SELECT
                p.titulo,
                COUNT(f.id_favorito) AS total
            FROM favorito AS f
            INNER JOIN pelicula AS p
                ON f.id_pelicula = p.id_pelicula
            GROUP BY p.id_pelicula, p.titulo
            ORDER BY total DESC, p.titulo ASC
            LIMIT 10
        """)
        peliculas_mas_favoritas = cursor.fetchall()

        return render_template(
            "index.html",
            estadisticas=estadisticas,
            libros_mas_vistos=libros_mas_vistos,
            libros_mas_favoritos=libros_mas_favoritos,
            peliculas_mas_vistas=peliculas_mas_vistas,
            peliculas_mas_favoritas=peliculas_mas_favoritas
        )

    except mysql.connector.Error:
        app.logger.exception("Error al consultar MySQL")
        return "No se pudieron cargar las estadísticas.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()

# MÓDULO DE REPORTES DE ENTRETENIMIENTO
from reportes.entretenimiento import crear_blueprint

app.register_blueprint(
    crear_blueprint(conectar_bd, requiere_rol)
)

# REPORTES DE SALUD Y PENSIÓN
from reportes.salud_pension import crear_blueprint as crear_salud_pension

app.register_blueprint(
    crear_salud_pension(conectar_bd, requiere_rol)
)

# REPORTES DE NOVEDADES DE NÓMINA
from reportes.novedades import crear_blueprint as crear_novedades

app.register_blueprint(
    crear_novedades(conectar_bd, requiere_rol)
)

# FICHA INDIVIDUAL DE EMPLEADOS
from reportes.ficha_empleado import crear_blueprint as crear_ficha_empleado

app.register_blueprint(
    crear_ficha_empleado(conectar_bd, requiere_rol)
)

# VISTA PREVIA Y EXPORTACIÓN PDF DE NÓMINA
from reportes.pdf_nomina import crear_blueprint as crear_pdf_nomina

app.register_blueprint(
    crear_pdf_nomina(conectar_bd, requiere_rol)
)

# PDF DE REPORTES DE ENTRETENIMIENTO
from reportes.pdf_entretenimiento import crear_blueprint as crear_pdf_entretenimiento

app.register_blueprint(
    crear_pdf_entretenimiento(conectar_bd, requiere_rol)
)

# PDF DE REPORTES DE SALUD Y PENSIÓN
from reportes.pdf_salud_pension import crear_blueprint as crear_pdf_salud_pension

app.register_blueprint(
    crear_pdf_salud_pension(conectar_bd, requiere_rol)
)

# PDF DE REPORTES DE NOVEDADES
from reportes.pdf_novedades import crear_blueprint as crear_pdf_novedades

app.register_blueprint(
    crear_pdf_novedades(conectar_bd, requiere_rol)
)

# INICIAR EL SERVIDOR
if __name__ == "__main__":
    app.run(
    host="localhost",
    port=5000,
    debug=True,
    use_reloader=False
)
