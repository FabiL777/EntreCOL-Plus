
-- Completar nombres de idiomas sin modificar sus códigos.

UPDATE idioma
SET nombre_idioma = CASE codigo_idioma
    WHEN 'eng' THEN 'Inglés'
    WHEN 'en-US' THEN 'Inglés (Estados Unidos)'
    WHEN 'en-GB' THEN 'Inglés (Reino Unido)'
    WHEN 'en-CA' THEN 'Inglés (Canadá)'
    WHEN 'spa' THEN 'Español'
    WHEN 'fre' THEN 'Francés'
    WHEN 'ger' THEN 'Alemán'
    WHEN 'jpn' THEN 'Japonés'
    WHEN 'mul' THEN 'Multilingüe'
    WHEN 'zho' THEN 'Chino'
    WHEN 'grc' THEN 'Griego antiguo'
    WHEN 'por' THEN 'Portugués'
    WHEN 'ita' THEN 'Italiano'
    WHEN 'enm' THEN 'Inglés medio'
    WHEN 'lat' THEN 'Latín'
    WHEN 'rus' THEN 'Ruso'
    WHEN 'swe' THEN 'Sueco'
    WHEN 'ara' THEN 'Árabe'
    WHEN 'gla' THEN 'Gaélico escocés'
    WHEN 'glg' THEN 'Gallego'
    WHEN 'msa' THEN 'Malayo'
    WHEN 'nl' THEN 'Neerlandés'
    WHEN 'nor' THEN 'Noruego'
    WHEN 'ale' THEN 'Aleutiano'
    ELSE nombre_idioma
END
WHERE nombre_idioma IS NULL;
