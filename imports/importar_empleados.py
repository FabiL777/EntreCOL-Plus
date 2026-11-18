"""EntreCOL+ fase 3: importa el maestro de empleados de 'Table 1'.
Uso: python imports/importar_empleados.py [--aplicar]
Sin --aplicar solo valida y muestra resumen; no escribe en MySQL.
"""
import argparse
import os
from collections import Counter
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
ARCHIVO = ROOT / 'data' / 'Nomina.xlsx'
CAMPOS = ['CÓDIGO', 'NOMBRE DEL EMPLEADO', 'DEPENDENCIA', 'CARGO',
          'FECHA INGRESO', 'EPS', 'ARL', 'PENSIÓN', 'SUELDO']


def fecha(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return datetime.strptime(str(int(valor)), '%Y%m%d').date()


def leer():
    if not ARCHIVO.exists():
        raise FileNotFoundError(f'No existe {ARCHIVO}. Copia el Excel a data/.')
    libro = load_workbook(ARCHIVO, read_only=True, data_only=True)
    try:
        hoja = libro['Table 1']
        filas = hoja.iter_rows(values_only=True)
        cabeceras = [str(x).strip() if x is not None else '' for x in next(filas)]
        if cabeceras[:9] != CAMPOS:
            raise ValueError(f'Las columnas del Excel cambiaron: {cabeceras[:9]}')
        registros = []
        for numero, valores in enumerate(filas, start=2):
            if all(v is None for v in valores):
                continue
            try:
                codigo, nombre, dep, cargo, ingreso, eps, arl, pension, sueldo = valores[:9]
                if any(v is None or str(v).strip() == '' for v in (codigo, nombre, dep, cargo, ingreso, eps, arl, pension, sueldo)):
                    raise ValueError('Falta un dato obligatorio')
                registros.append((str(codigo).strip(), str(nombre).strip(), str(dep).strip(),
                                  str(cargo).strip(), fecha(ingreso), str(eps).strip(),
                                  str(arl).strip(), str(pension).strip(), Decimal(str(sueldo))))
            except Exception as e:
                raise ValueError(f'Fila {numero}: {e}') from e
        repetidos = [c for c, n in Counter(r[0] for r in registros).items() if n > 1]
        if repetidos:
            raise ValueError(f'Códigos duplicados: {repetidos}')
        return registros
    finally:
        libro.close()


def catalogo(cursor, tabla, campo, valor, clave):
    cursor.execute(f'SELECT {clave} FROM {tabla} WHERE {campo}=%s', (valor,))
    fila = cursor.fetchone()
    if fila:
        return fila[0]
    cursor.execute(f'INSERT INTO {tabla} ({campo}) VALUES (%s)', (valor,))
    return cursor.lastrowid


def historial_si_falta(cursor, tabla, codigo, campos, valores):
    cursor.execute(f'SELECT 1 FROM {tabla} WHERE codigo_empleado=%s LIMIT 1', (codigo,))
    if cursor.fetchone():
        return
    columnas = ', '.join(['codigo_empleado', *campos, 'fecha_inicio'])
    placeholders = ', '.join(['%s'] * (len(campos) + 2))
    cursor.execute(f'INSERT INTO {tabla} ({columnas}) VALUES ({placeholders})',
                   (codigo, *valores))


def importar(registros):
    conexion = mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '3306')),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'entrecol_plus'),
    )
    cursor = conexion.cursor()
    nuevos = 0
    existentes = 0
    try:
        for codigo, nombre, dep, cargo, ingreso, eps, arl, pension, sueldo in registros:
            cursor.execute('SELECT 1 FROM empleado WHERE codigo_empleado=%s', (codigo,))
            if cursor.fetchone():
                existentes += 1
                # No sobrescribimos empleados ni historiales existentes.
                continue
            id_dep = catalogo(cursor, 'dependencia', 'nombre_dependencia', dep, 'id_dependencia')
            id_cargo = catalogo(cursor, 'cargo', 'nombre_cargo', cargo, 'id_cargo')
            id_eps = catalogo(cursor, 'eps', 'nombre_eps', eps, 'id_eps')
            id_arl = catalogo(cursor, 'arl', 'nombre_arl', arl, 'id_arl')
            id_pension = catalogo(cursor, 'pension', 'nombre_pension', pension, 'id_pension')
            cursor.execute('INSERT INTO empleado (codigo_empleado,nombre_empleado,fecha_ingreso_empresa) VALUES (%s,%s,%s)',
                           (codigo, nombre, ingreso))
            # El Excel solo ofrece un estado por persona, no fechas reales de cambios.
            # Usamos fecha de ingreso como fecha inicial provisional del historial.
            historial_si_falta(cursor, 'empleado_historial_laboral', codigo,
                              ['id_cargo', 'id_dependencia'], [id_cargo, id_dep, ingreso])
            historial_si_falta(cursor, 'empleado_historial_salario', codigo,
                              ['salario'], [sueldo, ingreso])
            for tabla, campo, valor in (
                ('empleado_historial_eps', 'id_eps', id_eps),
                ('empleado_historial_arl', 'id_arl', id_arl),
                ('empleado_historial_pension', 'id_pension', id_pension),
            ):
                historial_si_falta(cursor, tabla, codigo, [campo], [valor, ingreso])
            nuevos += 1
        conexion.commit()
        print(f'Importación correcta. Nuevos: {nuevos}; ya existentes (sin modificar): {existentes}.')
    except Exception:
        conexion.rollback()
        raise
    finally:
        cursor.close()
        conexion.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--aplicar', action='store_true', help='Inserta datos en MySQL')
    args = parser.parse_args()
    registros = leer()
    print(f'Archivo: {ARCHIVO.name}; empleados válidos: {len(registros)}')
    print('Códigos:', ', '.join(r[0] for r in registros))
    if not args.aplicar:
        print('MODO PRUEBA: no se modificó la base de datos.')
        print('Para importar: python imports/importar_empleados.py --aplicar')
        return
    importar(registros)


if __name__ == '__main__':
    main()
