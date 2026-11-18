
-- =====================================================
-- ENTRECOL+ - FASE 4
-- CONSULTAS SQL Y REPORTES
-- =====================================================


USE entrecol_plus;

-- CONSULTA 1
-- Mostrar los empleados registrados en el sistema.

SELECT
    e.codigo_empleado,
    e.nombre_empleado,
    e.documento,
    e.fecha_ingreso_empresa,
    e.estado_empleado
FROM empleado e
ORDER BY e.codigo_empleado;

-- CONSULTA 2
-- Mostrar empleados con su cargo y dependencia.
-- Se utiliza el historial laboral vigente.

SELECT
    e.codigo_empleado,
    e.nombre_empleado,
    c.nombre_cargo,
    d.nombre_dependencia,
    hl.fecha_inicio,
    hl.fecha_fin
FROM empleado e
LEFT JOIN empleado_historial_laboral hl
    ON e.codigo_empleado = hl.codigo_empleado
    AND hl.fecha_fin IS NULL
LEFT JOIN cargo c
    ON hl.id_cargo = c.id_cargo
LEFT JOIN dependencia d
    ON hl.id_dependencia = d.id_dependencia
ORDER BY e.codigo_empleado;

-- CONSULTA 3
-- Mostrar empleados con su salario vigente.

SELECT
    e.codigo_empleado,
    e.nombre_empleado,
    hs.salario,
    hs.fecha_inicio AS fecha_inicio_salario,
    hs.fecha_fin AS fecha_fin_salario
FROM empleado e
LEFT JOIN empleado_historial_salario hs
    ON e.codigo_empleado = hs.codigo_empleado
    AND hs.fecha_fin IS NULL
ORDER BY e.codigo_empleado;

-- CONSULTA 4
-- Estadísticas de los salarios vigentes.

SELECT
    COUNT(DISTINCT hs.codigo_empleado) AS empleados_con_salario,
    ROUND(AVG(hs.salario), 2) AS salario_promedio,
    MAX(hs.salario) AS salario_maximo,
    MIN(hs.salario) AS salario_minimo
FROM empleado_historial_salario hs
WHERE hs.fecha_fin IS NULL;

-- CONSULTA 5
-- Salario promedio, máximo y mínimo por dependencia.

SELECT
    d.nombre_dependencia,
    COUNT(DISTINCT e.codigo_empleado) AS total_empleados,
    ROUND(AVG(hs.salario), 2) AS salario_promedio,
    MAX(hs.salario) AS salario_maximo,
    MIN(hs.salario) AS salario_minimo
FROM empleado e
INNER JOIN empleado_historial_laboral hl
    ON e.codigo_empleado = hl.codigo_empleado
    AND hl.fecha_fin IS NULL
INNER JOIN dependencia d
    ON hl.id_dependencia = d.id_dependencia
INNER JOIN empleado_historial_salario hs
    ON e.codigo_empleado = hs.codigo_empleado
    AND hs.fecha_fin IS NULL
GROUP BY d.id_dependencia, d.nombre_dependencia
ORDER BY salario_promedio DESC;

-- CONSULTA 6
-- Empleados con novedades de incapacidad y vacaciones.

SELECT
    e.codigo_empleado,
    e.nombre_empleado,
    tn.nombre_tipo AS tipo_novedad,
    n.fecha_inicio,
    n.fecha_fin,
    n.cantidad_dias,
    n.observacion
FROM novedad n
INNER JOIN nomina no
    ON n.id_nomina = no.id_nomina
INNER JOIN empleado e
    ON no.codigo_empleado = e.codigo_empleado
INNER JOIN tipo_novedad tn
    ON n.id_tipo_novedad = tn.id_tipo_novedad
WHERE tn.nombre_tipo IN ('INCAPACIDAD', 'VACACIONES')
ORDER BY n.fecha_inicio, e.codigo_empleado;

-- CONSULTA 7
-- Resumen de incapacidades y vacaciones.

SELECT
    tn.nombre_tipo AS tipo_novedad,
    COUNT(n.id_novedad) AS cantidad_novedades,
    COUNT(DISTINCT no.codigo_empleado) AS empleados_afectados,
    SUM(n.cantidad_dias) AS total_dias,
    ROUND(AVG(n.cantidad_dias), 2) AS promedio_dias
FROM novedad n
INNER JOIN tipo_novedad tn
    ON n.id_tipo_novedad = tn.id_tipo_novedad
INNER JOIN nomina no
    ON n.id_nomina = no.id_nomina
WHERE tn.nombre_tipo IN ('INCAPACIDAD', 'VACACIONES')
GROUP BY tn.id_tipo_novedad, tn.nombre_tipo
ORDER BY tn.nombre_tipo;

-- CONSULTA 8
-- Historial salarial completo de los empleados.

SELECT
    e.codigo_empleado,
    e.nombre_empleado,
    hs.salario,
    hs.fecha_inicio,
    hs.fecha_fin,
    CASE
        WHEN hs.fecha_fin IS NULL THEN 'VIGENTE'
        ELSE 'FINALIZADO'
    END AS estado_salario
FROM empleado e
INNER JOIN empleado_historial_salario hs
    ON e.codigo_empleado = hs.codigo_empleado
ORDER BY e.codigo_empleado, hs.fecha_inicio DESC;

-- CONSULTA 9
-- Mostrar cada película una sola vez con todos sus géneros.

SELECT
    p.id_pelicula,
    p.titulo,
    p.anio_lanzamiento,
    GROUP_CONCAT(
        DISTINCT g.nombre_genero
        ORDER BY g.nombre_genero
        SEPARATOR ', '
    ) AS generos
FROM pelicula p
LEFT JOIN pelicula_genero pg
    ON p.id_pelicula = pg.id_pelicula
LEFT JOIN genero g
    ON pg.id_genero = g.id_genero
GROUP BY
    p.id_pelicula,
    p.titulo,
    p.anio_lanzamiento
ORDER BY p.id_pelicula
LIMIT 50;

-- CONSULTA 10
-- Cantidad de películas registradas por género.

SELECT
    g.nombre_genero,
    COUNT(pg.id_pelicula) AS cantidad_peliculas
FROM genero g
LEFT JOIN pelicula_genero pg
    ON g.id_genero = pg.id_genero
GROUP BY g.id_genero, g.nombre_genero
ORDER BY cantidad_peliculas DESC;

-- CONSULTA 11
-- Cantidad de películas por año de lanzamiento.

SELECT
    p.anio_lanzamiento,
    COUNT(p.id_pelicula) AS cantidad_peliculas
FROM pelicula p
WHERE p.anio_lanzamiento IS NOT NULL
GROUP BY p.anio_lanzamiento
ORDER BY cantidad_peliculas DESC, p.anio_lanzamiento DESC
LIMIT 20;

-- CONSULTA 12
-- Mostrar cada libro una sola vez con todos sus autores.

SELECT
    l.id_libro,
    l.titulo,
    GROUP_CONCAT(
        DISTINCT a.nombre_autor
        ORDER BY a.nombre_autor
        SEPARATOR ', '
    ) AS autores,
    l.rating_promedio,
    l.numero_paginas,
    l.fecha_publicacion
FROM libro l
LEFT JOIN libro_autor la
    ON l.id_libro = la.id_libro
LEFT JOIN autor a
    ON la.id_autor = a.id_autor
GROUP BY
    l.id_libro,
    l.titulo,
    l.rating_promedio,
    l.numero_paginas,
    l.fecha_publicacion
ORDER BY l.id_libro
LIMIT 50;

-- CONSULTA 13
-- Cantidad de libros registrados por editorial.

SELECT
    ed.nombre_editorial,
    COUNT(l.id_libro) AS cantidad_libros
FROM editorial ed
LEFT JOIN libro l
    ON ed.id_editorial = l.id_editorial
GROUP BY
    ed.id_editorial,
    ed.nombre_editorial
ORDER BY cantidad_libros DESC, ed.nombre_editorial ASC
LIMIT 20;

-- CONSULTA 14
-- Cantidad de libros registrados por idioma.

SELECT
    i.codigo_idioma,
    COALESCE(i.nombre_idioma, 'Sin nombre') AS idioma,
    COUNT(l.id_libro) AS cantidad_libros
FROM idioma i
LEFT JOIN libro l
    ON i.id_idioma = l.id_idioma
GROUP BY
    i.id_idioma,
    i.codigo_idioma,
    i.nombre_idioma
ORDER BY cantidad_libros DESC, i.codigo_idioma ASC;

-- CONSULTA 15
-- Estadísticas generales de EntreCOL+.

SELECT
    (SELECT COUNT(*) FROM empleado) AS total_empleados,
    (SELECT COUNT(*) FROM pelicula) AS total_peliculas,
    (SELECT COUNT(*) FROM libro) AS total_libros,
    (SELECT COUNT(*) FROM autor) AS total_autores,
    (SELECT COUNT(*) FROM genero) AS total_generos,
    (SELECT COUNT(*) FROM editorial) AS total_editoriales,
    (SELECT COUNT(*) FROM idioma) AS total_idiomas,
    (SELECT COUNT(*) FROM novedad) AS total_novedades;
