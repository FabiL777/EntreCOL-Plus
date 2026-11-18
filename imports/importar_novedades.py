"""EntreCOL+ Fase 3 - Paso 2: importa SOLO novedades fechadas de Table 3.
Uso: python imports/importar_novedades.py [--aplicar]
Sin --aplicar no escribe en MySQL.
Los datos generales de nómina (días trabajados, bonificaciones, transporte)
NO se importan porque el Excel no identifica su periodo mensual.
"""
import argparse
import calendar
import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel

ROOT = Path(__file__).resolve().parents[1]
ARCHIVO = ROOT / 'data' / 'Nomina.xlsx'
load_dotenv(ROOT / '.env')
CABECERAS = [
    'CÓDIGO', 'NOVEDAD INCAPACIDAD', 'NOVEDAD VACACIONES',
    'NUMERO DIAS TRABAJADOS EN EL MES', 'NUMERO DIAS INCAPACIDADES EN EL MES',
    'NUMERO DE DIAS VACACIONES', 'FECHA DE INICIO DE VACACIONES',
    'FECHA TERMINACION DE VACACIONES', 'FECHA INICIO INCAPACIDAD',
    'FECHA TERMINACIÓN INCAPACIDAD', 'BONIFICACIÓN', 'TRANSPORTE'
]


def convertir_fecha(valor, epoca):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, (int, float)):
        return from_excel(valor, epoch=epoca).date()
    if isinstance(valor, str):
        return datetime.strptime(valor.strip(), '%Y-%m-%d').date()
    raise ValueError(f'Fecha inválida: {valor!r}')


def leer_novedades():
    if not ARCHIVO.exists():
        raise FileNotFoundError(f'No encuentro {ARCHIVO}')
    libro = load_workbook(ARCHIVO, read_only=True, data_only=True)
    try:
        hoja = libro['Table 3']
        filas = hoja.iter_rows(values_only=True)
        encabezados = [str(v).strip() if v is not None else '' for v in next(filas)[:12]]
        if encabezados != CABECERAS:
            raise ValueError('Las 12 columnas de Table 3 no coinciden con el Excel revisado.')
        novedades = []
        vistos = set()
        for num_fila, fila in enumerate(filas, start=2):
            if not fila or fila[0] is None:
                continue
            codigo = str(fila[0]).strip()
            for tipo, marca_idx, dias_idx, inicio_idx, fin_idx in (
                ('INCAPACIDAD', 1, 4, 8, 9),
                ('VACACIONES', 2, 5, 6, 7),
            ):
                marca = str(fila[marca_idx] or '').strip().upper()
                dias = Decimal(str(fila[dias_idx] or 0))
                inicio_bruto, fin_bruto = fila[inicio_idx], fila[fin_idx]
                existe = bool(marca or dias or inicio_bruto is not None or fin_bruto is not None)
                if not existe:
                    continue
                if marca != 'X' or dias <= 0 or inicio_bruto is None or fin_bruto is None:
                    raise ValueError(f'Fila {num_fila}, {tipo}: marca, días o fechas incompletos.')
                inicio = convertir_fecha(inicio_bruto, libro.epoch)
                fin = convertir_fecha(fin_bruto, libro.epoch)
                if fin < inicio:
                    raise ValueError(f'Fila {num_fila}: fecha final anterior a la inicial.')
                if (inicio.year, inicio.month) != (fin.year, fin.month):
                    raise ValueError(f'Fila {num_fila}: novedad cruza meses; requiere reparto manual.')
                clave = (codigo, tipo, inicio, fin)
                if clave in vistos:
                    raise ValueError(f'Novedad duplicada en Excel: {clave}')
                vistos.add(clave)
                novedades.append((codigo, tipo, inicio, fin, dias))
        return novedades
    finally:
        libro.close()


def importar(novedades):
    conexion = mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '3306')),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'entrecol_plus'),
    )
    cursor = conexion.cursor()
    nuevos, existentes = 0, 0
    try:
        for codigo, tipo, inicio, fin, dias in novedades:
            cursor.execute('SELECT 1 FROM empleado WHERE codigo_empleado=%s', (codigo,))
            if cursor.fetchone() is None:
                raise ValueError(f'No existe empleado {codigo}; importa primero empleados.')
            cursor.execute('SELECT id_tipo_novedad FROM tipo_novedad WHERE nombre_tipo=%s', (tipo,))
            fila = cursor.fetchone()
            if fila:
                id_tipo = fila[0]
            else:
                cursor.execute('INSERT INTO tipo_novedad (nombre_tipo, descripcion) VALUES (%s,%s)',
                               (tipo, 'Importado desde Nomina.xlsx / Table 3'))
                id_tipo = cursor.lastrowid
            cursor.execute('SELECT id_periodo FROM periodo_nomina WHERE mes=%s AND anio=%s',
                           (inicio.month, inicio.year))
            fila = cursor.fetchone()
            if fila:
                id_periodo = fila[0]
            else:
                primer_dia = date(inicio.year, inicio.month, 1)
                ultimo_dia = date(inicio.year, inicio.month, calendar.monthrange(inicio.year, inicio.month)[1])
                cursor.execute('''INSERT INTO periodo_nomina
                    (mes, anio, fecha_inicio, fecha_fin) VALUES (%s,%s,%s,%s)''',
                    (inicio.month, inicio.year, primer_dia, ultimo_dia))
                id_periodo = cursor.lastrowid
            cursor.execute('''SELECT id_nomina FROM nomina
                WHERE codigo_empleado=%s AND id_periodo=%s''', (codigo, id_periodo))
            fila = cursor.fetchone()
            if fila:
                id_nomina = fila[0]
            else:
                cursor.execute('''SELECT salario FROM empleado_historial_salario
                    WHERE codigo_empleado=%s ORDER BY fecha_inicio DESC, id_historial_salario DESC LIMIT 1''',
                    (codigo,))
                salario = cursor.fetchone()
                if salario is None:
                    raise ValueError(f'No hay salario registrado para empleado {codigo}')
                # Registro de enlace: datos mensuales sin identificar se mantienen en 0,
                # NO representan nómina liquidada ni días realmente trabajados.
                cursor.execute('''INSERT INTO nomina
                    (codigo_empleado,id_periodo,salario_base,dias_trabajados,bonificacion,auxilio_transporte)
                    VALUES (%s,%s,%s,0,0,0)''', (codigo, id_periodo, salario[0]))
                id_nomina = cursor.lastrowid
            cursor.execute('''SELECT id_novedad FROM novedad
                WHERE id_nomina=%s AND id_tipo_novedad=%s
                AND fecha_inicio=%s AND fecha_fin=%s''',
                (id_nomina, id_tipo, inicio, fin))
            if cursor.fetchone():
                existentes += 1
                continue
            cursor.execute('''INSERT INTO novedad
                (id_nomina,id_tipo_novedad,fecha_inicio,fecha_fin,cantidad_dias,observacion)
                VALUES (%s,%s,%s,%s,%s,%s)''',
                (id_nomina, id_tipo, inicio, fin, dias,
                 'Fuente: Nomina.xlsx, Table 3. Días tomados del Excel; sin recálculo.'))
            nuevos += 1
        conexion.commit()
        print(f'Importación correcta. Novedades nuevas: {nuevos}; existentes: {existentes}.')
        print('AVISO: los registros de nomina creados solo enlazan novedades; NO son liquidaciones completas.')
    except Exception:
        conexion.rollback()
        raise
    finally:
        cursor.close()
        conexion.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--aplicar', action='store_true', help='Guarda las novedades en MySQL')
    args = parser.parse_args()
    novedades = leer_novedades()
    print(f'Archivo: {ARCHIVO.name}; novedades fechadas: {len(novedades)}')
    for codigo, tipo, inicio, fin, dias in novedades:
        print(f'Empleado {codigo}: {tipo}; {inicio} a {fin}; {dias} días reportados')
    if not args.aplicar:
        print('MODO PRUEBA: no se modificó MySQL.')
        print('Para importar: python imports/importar_novedades.py --aplicar')
        return
    importar(novedades)

if __name__ == '__main__':
    main()
