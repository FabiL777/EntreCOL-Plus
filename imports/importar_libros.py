"""EntreCOL+ | Books.json. Prueba sin cambios: python imports/importar_libros.py
Importación: python imports/importar_libros.py --aplicar
"""
import argparse
import json
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVO = ROOT / 'data' / 'Books.json'
DESPLAZADOS = {12224, 16914, 22128, 34889}


def reparar(original):
    r = original.copy()
    if int(r['bookID']) not in DESPLAZADOS:
        return r
    # El texto que terminó en average_rating es continuación del autor.
    r['authors'] = str(r['authors']) + (',' if int(r['bookID']) == 16914 else '') + str(r['average_rating'])
    anteriores = original
    for destino, origen in [
        ('average_rating', 'isbn'), ('isbn', 'isbn13'),
        ('isbn13', 'language_code'), ('language_code', 'num_pages'),
        ('num_pages', 'ratings_count'), ('ratings_count', 'text_reviews_count'),
        ('text_reviews_count', 'publication_date'),
        ('publication_date', 'publisher'), ('publisher', 'FIELD13')
    ]:
        r[destino] = anteriores.get(origen)
    return r


def texto(valor, maximo, campo, identificador, obligatorio=False):
    s = '' if valor is None else str(valor).strip()
    if obligatorio and not s:
        raise ValueError(f'Libro {identificador}: {campo} está vacío')
    if len(s) > maximo:
        raise ValueError(f'Libro {identificador}: {campo} supera {maximo} caracteres')
    return s or None


def entero(valor, campo, identificador):
    if valor is None or str(valor).strip() == '':
        return None
    try:
        n = int(str(valor).strip())
    except ValueError as e:
        raise ValueError(f'Libro {identificador}: {campo} inválido: {valor!r}') from e
    if n < 0 or n > 2147483647:
        raise ValueError(f'Libro {identificador}: {campo} fuera de rango')
    return n


def preparar():
    with ARCHIVO.open('r', encoding='utf-8-sig') as f:
        datos = json.load(f)
    if not isinstance(datos, list):
        raise ValueError('Books.json debe contener una lista')
    libros, vistos = [], set()
    for pos, original in enumerate(datos, 1):
        if not isinstance(original, dict):
            raise ValueError(f'Registro {pos} no es un objeto')
        r = reparar(original)
        identificador = entero(r.get('bookID'), 'bookID', pos)
        if identificador is None or identificador == 0 or identificador in vistos:
            raise ValueError(f'ID inválido o duplicado: {identificador}')
        vistos.add(identificador)
        titulo = texto(r.get('title'), 500, 'title', identificador, True)
        autores = [a.strip() for a in str(r.get('authors') or '').split('/') if a.strip()]
        autores = list(dict.fromkeys(autores))
        if not autores:
            raise ValueError(f'Libro {identificador}: sin autores')
        for autor in autores:
            texto(autor, 180, 'autor', identificador, True)
        editorial = texto(r.get('publisher'), 180, 'publisher', identificador)
        idioma = texto(r.get('language_code'), 20, 'language_code', identificador)
        isbn = texto(r.get('isbn'), 20, 'isbn', identificador)
        isbn13 = texto(r.get('isbn13'), 20, 'isbn13', identificador)
        campo = texto(r.get('FIELD13'), 255, 'FIELD13', identificador)
        try:
            rating = Decimal(str(r.get('average_rating')).strip()) if str(r.get('average_rating') or '').strip() else None
        except InvalidOperation as e:
            raise ValueError(f'Libro {identificador}: rating inválido') from e
        if rating is not None and not (Decimal('0') <= rating <= Decimal('5')):
            raise ValueError(f'Libro {identificador}: rating fuera de rango')
        fecha = None
        if str(r.get('publication_date') or '').strip():
            try:
                fecha = datetime.strptime(str(r['publication_date']).strip(), '%m/%d/%Y').date()
            except ValueError as e:
                print(f'AVISO: libro {identificador}, fecha inválida {r["publication_date"]!r}; se guardará NULL')
        libros.append((identificador, titulo, rating, isbn, isbn13,
                       entero(r.get('num_pages'), 'num_pages', identificador),
                       entero(r.get('ratings_count'), 'ratings_count', identificador),
                       entero(r.get('text_reviews_count'), 'text_reviews_count', identificador),
                       fecha, campo, editorial, idioma, autores))
    return libros


def aplicar(libros):
    import mysql.connector
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
    conexion = mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '3306')),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'entrecol_plus')
    )
    cursor = conexion.cursor()
    nuevos = 0
    existentes = 0
    relaciones = 0
    try:
        conexion.start_transaction()
        cursor.execute('SELECT id_libro FROM libro')
        ids_existentes = {x[0] for x in cursor.fetchall()}
        cursor.execute('SELECT nombre_editorial, id_editorial FROM editorial')
        editoriales = dict(cursor.fetchall())
        cursor.execute('SELECT codigo_idioma, id_idioma FROM idioma')
        idiomas = dict(cursor.fetchall())
        cursor.execute('SELECT nombre_autor, id_autor FROM autor')
        autores_bd = dict(cursor.fetchall())
        for (identificador, titulo, rating, isbn, isbn13, paginas, ratings,
             resenas, fecha, campo, editorial, idioma, autores) in libros:
            if identificador in ids_existentes:
                existentes += 1
                continue
            id_editorial = None
            if editorial:
                if editorial not in editoriales:
                    cursor.execute('''INSERT INTO editorial (nombre_editorial) VALUES (%s)
                        ON DUPLICATE KEY UPDATE id_editorial = LAST_INSERT_ID(id_editorial)''', (editorial,))
                    editoriales[editorial] = cursor.lastrowid
                id_editorial = editoriales[editorial]
            id_idioma = None
            if idioma:
                if idioma not in idiomas:
                    cursor.execute('''INSERT INTO idioma (codigo_idioma) VALUES (%s)
                        ON DUPLICATE KEY UPDATE id_idioma = LAST_INSERT_ID(id_idioma)''', (idioma,))
                    idiomas[idioma] = cursor.lastrowid
                id_idioma = idiomas[idioma]
            cursor.execute('''INSERT INTO libro
                (id_libro, titulo, rating_promedio, isbn, isbn13, numero_paginas,
                 cantidad_ratings, cantidad_resenas, fecha_publicacion,
                 campo_adicional, id_editorial, id_idioma)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (identificador, titulo, rating, isbn, isbn13, paginas,
                 ratings, resenas, fecha, campo, id_editorial, id_idioma))
            nuevos += 1
            for autor in autores:
                if autor not in autores_bd:
                    cursor.execute('''INSERT INTO autor (nombre_autor) VALUES (%s)
                        ON DUPLICATE KEY UPDATE id_autor = LAST_INSERT_ID(id_autor)''', (autor,))
                    autores_bd[autor] = cursor.lastrowid
                cursor.execute('INSERT INTO libro_autor (id_libro,id_autor) VALUES (%s,%s)',
                               (identificador, autores_bd[autor]))
                relaciones += 1
        conexion.commit()
        print(f'Importación correcta. Libros nuevos: {nuevos}; existentes: {existentes}.')
        print(f'Editoriales disponibles: {len(editoriales)}; idiomas: {len(idiomas)}; autores: {len(autores_bd)}.')
        print(f'Relaciones libro-autor nuevas: {relaciones}.')
    except Exception:
        conexion.rollback()
        print('ERROR: se revirtieron los cambios de esta ejecución.')
        raise
    finally:
        cursor.close()
        conexion.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--aplicar', action='store_true')
    args = parser.parse_args()
    libros = preparar()
    print(f'Archivo: {ARCHIVO.name}; libros válidos: {len(libros)}')
    print('Registros reparados:', ', '.join(map(str, sorted(DESPLAZADOS))))
    print(f'Autores distintos: {len(set(a for l in libros for a in l[-1]))}')
    print(f'Editoriales distintas: {len(set(l[-3] for l in libros if l[-3]))}')
    print(f'Idiomas distintos: {len(set(l[-2] for l in libros if l[-2]))}')
    if args.aplicar:
        aplicar(libros)
    else:
        print('MODO PRUEBA: no se modificó MySQL.')
        print('Para importar: python imports/importar_libros.py --aplicar')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('ERROR:', exc)
        raise SystemExit(1)
