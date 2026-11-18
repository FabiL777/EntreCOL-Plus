
"""EntreCOL+ - Fase 3: importar películas desde movies.dat."""

import argparse
import os
import re
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
ARCHIVO = ROOT / "data" / "movies.dat"

load_dotenv(ROOT / ".env")

PATRON = re.compile(r"^(.*?)\s*\((\d{4})\)$")


def leer_peliculas():
    if not ARCHIVO.is_file():
        raise FileNotFoundError(f"No encuentro: {ARCHIVO}")

    peliculas = []
    ids = set()

    with ARCHIVO.open("r", encoding="utf-8-sig") as archivo:
        for numero_linea, linea in enumerate(archivo, 1):
            linea = linea.strip()

            if not linea:
                continue

            partes = linea.split("::")

            if len(partes) != 3:
                raise ValueError(
                    f"Línea {numero_linea}: formato incorrecto"
                )

            id_texto, titulo_con_anio, generos_texto = partes

            id_pelicula = int(id_texto)

            if id_pelicula <= 0 or id_pelicula in ids:
                raise ValueError(
                    f"Línea {numero_linea}: ID duplicado o inválido"
                )

            ids.add(id_pelicula)

            coincidencia = PATRON.fullmatch(
                titulo_con_anio.strip()
            )

            if not coincidencia:
                raise ValueError(
                    f"Línea {numero_linea}: título o año inválido"
                )

            titulo = coincidencia.group(1).strip()
            anio = int(coincidencia.group(2))

            if not titulo or len(titulo) > 255:
                raise ValueError(
                    f"Línea {numero_linea}: título inválido"
                )

            generos = list(dict.fromkeys(
                g.strip() for g in generos_texto.split("|")
            ))

            if not generos or any(
                not g or len(g) > 100 for g in generos
            ):
                raise ValueError(
                    f"Línea {numero_linea}: géneros inválidos"
                )

            peliculas.append(
                (id_pelicula, titulo, anio, generos)
            )

    return peliculas


def aplicar(peliculas):
    conexion = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "entrecol_plus")
    )

    cursor = conexion.cursor()

    nuevas = 0
    existentes = 0
    relaciones_nuevas = 0

    try:
        conexion.start_transaction()

        cursor.execute(
            "SELECT id_genero, nombre_genero FROM genero"
        )

        generos_db = {
            nombre: id_genero
            for id_genero, nombre in cursor.fetchall()
        }

        for id_pelicula, titulo, anio, generos in peliculas:

            cursor.execute(
                """
                SELECT titulo, anio_lanzamiento
                FROM pelicula
                WHERE id_pelicula = %s
                """,
                (id_pelicula,)
            )

            fila = cursor.fetchone()

            if fila is None:
                cursor.execute(
                    """
                    INSERT INTO pelicula
                    (id_pelicula, titulo, anio_lanzamiento)
                    VALUES (%s, %s, %s)
                    """,
                    (id_pelicula, titulo, anio)
                )
                nuevas += 1

            else:
                if fila != (titulo, anio):
                    raise ValueError(
                        f"Conflicto con la película {id_pelicula}"
                    )

                existentes += 1

            for genero in generos:

                if genero not in generos_db:
                    cursor.execute(
                        """
                        INSERT INTO genero (nombre_genero)
                        VALUES (%s)
                        """,
                        (genero,)
                    )

                    generos_db[genero] = cursor.lastrowid

                cursor.execute(
                    """
                    INSERT IGNORE INTO pelicula_genero
                    (id_pelicula, id_genero)
                    VALUES (%s, %s)
                    """,
                    (id_pelicula, generos_db[genero])
                )

                relaciones_nuevas += cursor.rowcount

        conexion.commit()

        print(
            f"Importación correcta. "
            f"Películas nuevas: {nuevas}; "
            f"existentes: {existentes}."
        )

        print(
            f"Géneros disponibles: {len(generos_db)}; "
            f"relaciones nuevas: {relaciones_nuevas}."
        )

    except Exception:
        conexion.rollback()
        print("ERROR: se revirtieron los cambios.")
        raise

    finally:
        cursor.close()
        conexion.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="Insertar películas en MySQL"
    )

    args = parser.parse_args()
    peliculas = leer_peliculas()

    print(
        f"Archivo: {ARCHIVO.name}; "
        f"películas válidas: {len(peliculas)}"
    )

    cantidad_generos = len({
        genero
        for _, _, _, generos in peliculas
        for genero in generos
    })

    print(
        f"Géneros distintos en archivo: {cantidad_generos}"
    )

    primera = peliculas[0]

    print(
        f"Primera película: {primera[0]} - "
        f"{primera[1]} ({primera[2]})"
    )

    if args.aplicar:
        aplicar(peliculas)
    else:
        print("MODO PRUEBA: no se modificó MySQL.")
        print(
            "Para importar: "
            "python imports/importar_peliculas.py --aplicar"
        )


if __name__ == "__main__":
    main()
