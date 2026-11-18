EntreCOL+
Sistema web de gestión administrativa, laboral y de entretenimiento
Proyecto académico de Teoría de Bases de Datos — estado: desarrollo avanzado, pendiente de pruebas integrales y documentación final.
¿Qué es EntreCOL+?
EntreCOL+ es una aplicación web desarrollada con Python y Flask, MySQL y plantillas HTML/CSS/JavaScript. Integra gestión de empleados, información laboral, solicitudes, catálogo de libros y películas, y reportes administrativos con gráficos y exportación a PDF. La base de datos utiliza relaciones y claves primarias/foráneas para organizar la información.
Tecnologías
- Backend: Python, Flask.
- Base de datos: MySQL (entorno local con XAMPP y phpMyAdmin).
- Frontend: HTML, CSS, JavaScript y Chart.js.
- Reportes: ReportLab (PDF).
- Importación y procesamiento: pandas, openpyxl y scripts Python.
- Autenticación y formularios: sesiones Flask, Flask-WTF y Cloudflare Turnstile.
Funcionalidades existentes
- Registro, inicio de sesión y cierre de sesión.
- Diferentes vistas según el rol: administrador, empleado y usuario.
- Panel administrativo con accesos a empleados, solicitudes y reportes.
- Gestión y consulta de empleados, ficha individual e información laboral.
- Consultas de novedades laborales y solicitudes de empleados.
- Catálogo de libros y películas, reseñas, favoritos e historial.
- Reportes de nómina, entretenimiento, salud y pensión, y novedades.
- Gráficos y filtros en los reportes.
- Vista previa y descarga PDF de los cuatro reportes.
Verificación manual realizada por el equipo: funcionan los accesos de navegación del administrador y los botones de vista previa/descarga PDF; se comprobó que los filtros se conservan en las pruebas realizadas. Esto no sustituye las pruebas integrales de todos los módulos.
Estructura del proyecto
EntreCOL+/
├── app.py                  # Aplicación Flask y rutas principales
├── config.py               # Configuración auxiliar
├── database/               # Scripts SQL del proyecto
├── imports/                # Scripts de importación de datos
├── reportes/               # Módulos de reportes y exportación PDF
├── templates/              # Plantillas HTML
├── static/                 # CSS y JavaScript
├── data/                   # Archivos de datos de ejemplo
├── requirements.txt        # Dependencias Python
├── .env.example            # Plantilla de configuración (crear)
└── README.md
Instalación local (Windows)
1. Requisitos
Instalar Python, Git, VS Code y XAMPP (con MySQL y phpMyAdmin).
2. Clonar el repositorio
git clone https://github.com/TU_USUARIO/EntreCOL-Plus.git
cd EntreCOL-Plus
Sustituir la URL por la del repositorio real. Si el repositorio contiene una carpeta adicional EntreCOL+, entrar a esa carpeta antes de continuar.

3. Crear el entorno virtual
py -m venv .venv
.\.venv\Scripts\Activate.ps1
4. Instalar dependencias
Antes de instalar: corregir requirements.txt si contiene comentarios con // al final de cada paquete. Dejar un paquete por línea, por ejemplo:
Flask
mysql-connector-python
pandas
openpyxl
reportlab
python-dotenv
Flask-WTF
Luego ejecutar:
pip install -r requirements.txt
5. Importar la base de datos
1. Iniciar MySQL desde XAMPP.
2. Abrir http://localhost/phpmyadmin.
3. Crear la base entrecol_plus (si el SQL no la crea automáticamente).
4. Ir a Importar y seleccionar la exportación SQL actual de la base de datos.
5. Confirmar que se crearon las tablas y que están disponibles los datos de prueba.
Importante: database/entrecol_plus_fase2.sql es un script del proyecto, pero no se ha comprobado que reproduzca todos los datos y cambios actuales. El responsable del repositorio debe agregar una exportación SQL actualizada y depurada (por ejemplo database/entrecol_plus.sql) antes de dar la instalación por completa. No subir datos personales ni contraseñas reales.
6. Configurar variables de entorno
Crear un archivo .env en la raíz del proyecto, con valores propios del equipo:
SECRET_KEY=REEMPLAZAR_CON_UNA_CLAVE_ALEATORIA_SEGURA
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=entrecol_plus
TURNSTILE_SITE_KEY=REEMPLAZAR_CON_CLAVE_PUBLICA_DE_PRUEBA
TURNSTILE_SECRET_KEY=REEMPLAZAR_CON_CLAVE_PRIVADA_DE_PRUEBA
La configuración de MySQL puede variar según cada equipo. Para probar Cloudflare Turnstile en local, utilizar claves apropiadas para desarrollo y el dominio local configurado. No subir .env a GitHub.
7. Ejecutar
python app.py
Abrir http://localhost:5000/login. Para el CAPTCHA, usar localhost en lugar de 127.0.0.1 si así está configurado el sitio de Turnstile.
Rutas útiles
Módulo	Ruta
Página pública	/
Acceso	/login
Administrador	/admin
Empleados	/admin/empleados
Solicitudes	/admin/solicitudes
Reportes recibidos	/admin/reportes
Nómina	/admin/reportes/nomina
Entretenimiento	/admin/reportes/entretenimiento
Salud y pensión	/admin/reportes/salud-pension
Novedades	/admin/reportes/novedades


Las rutas administrativas requieren autenticación y permisos correspondientes.
Pendientes para el compañero de proyecto
Estas tareas son comprobaciones o mejoras propuestas, no afirmaciones de que los módulos estén rotos.
Prioridad alta
- [ ] Preparar la base compartida: exportar la versión actual de MySQL, depurar datos sensibles y probar la importación desde cero en otro equipo.
- [ ] Verificar permisos de los tres roles: comprobar acceso autorizado y denegado a rutas, acciones, fichas, nómina, reportes y datos personales; probar también peticiones directas por URL.
- [ ] Probar los flujos CRUD existentes: crear, editar, consultar y gestionar estados en los módulos aplicables. Identificar qué operaciones faltan respecto a los requisitos originales antes de desarrollarlas.
- [ ] Revisar seguridad y validaciones: entradas vacías, datos inválidos, duplicados, CSRF, mensajes de error, manejo de sesiones y protección de información privada.
Prioridad media
- [ ] Probar importaciones: revisar los scripts en imports/, los archivos de ejemplo, la importación por archivo y el registro manual; comprobar errores y duplicados.
- [ ] Pruebas de reportes: verificar filtros, cifras, gráficos y PDFs con distintos datos, incluido el caso sin resultados.
- [ ] Pruebas de navegación: comprobar los enlaces de todos los roles, no solo del administrador, y revisar visualización móvil.
- [ ] Documentación de entrega: capturas, instrucciones de instalación, diccionario de datos, MER/MR, explicación de módulos y evidencias de pruebas.
Mejoras técnicas de preparación del repositorio
- [ ] Corregir requirements.txt y probar instalación limpia.
- [ ] Crear .env.example sin secretos y verificar que .env esté excluido de Git.
- [ ] Excluir .venv/, __pycache__/, *.pyc, respaldos y archivos temporales.
- [ ] Revisar data/ y los SQL antes de publicarlos para evitar datos privados o archivos demasiado grandes.
- [ ] Verificar que las instrucciones del README funcionan en el computador del compañero.
Criterios para considerar finalizado el proyecto
1. Se puede clonar e instalar en otro computador siguiendo este README.
2. La base de datos se importa sin errores y contiene los datos de prueba necesarios.
3. Cada rol puede realizar sus funciones y no acceder a información restringida.
4. Los formularios y flujos principales funcionan y muestran errores comprensibles.
5. Los cuatro reportes funcionan con filtros, gráficos, vista previa y descarga PDF.
6. No se incluyen claves privadas ni datos sensibles en el repositorio.
7. Se entrega documentación y evidencia de pruebas.
Colaboración
Crear una rama para cada tarea, por ejemplo:
git checkout -b pruebas/roles-y-permisos
Registrar los cambios mediante commits descriptivos y abrir un pull request para revisarlos antes de fusionarlos a main. Documentar en cada PR qué se cambió, cómo se probó y qué queda pendiente.
Nota de estado: este README describe el código compartido y las pruebas confirmadas durante el desarrollo. La validación completa del sistema y la exportación final de la base de datos siguen pendientes.
