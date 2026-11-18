-- ENTRECOL+ | Fase 2 | MySQL/MariaDB XAMPP\nCREATE DATABASE IF NOT EXISTS entrecol_plus CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE entrecol_plus;

CREATE TABLE dependencia (id_dependencia INT AUTO_INCREMENT PRIMARY KEY, nombre_dependencia VARCHAR(100) NOT NULL UNIQUE, descripcion VARCHAR(255)) ENGINE=InnoDB;
CREATE TABLE cargo (id_cargo INT AUTO_INCREMENT PRIMARY KEY, nombre_cargo VARCHAR(100) NOT NULL UNIQUE, descripcion VARCHAR(255)) ENGINE=InnoDB;
CREATE TABLE eps (id_eps INT AUTO_INCREMENT PRIMARY KEY, nombre_eps VARCHAR(120) NOT NULL UNIQUE) ENGINE=InnoDB;
CREATE TABLE arl (id_arl INT AUTO_INCREMENT PRIMARY KEY, nombre_arl VARCHAR(120) NOT NULL UNIQUE) ENGINE=InnoDB;
CREATE TABLE pension (id_pension INT AUTO_INCREMENT PRIMARY KEY, nombre_pension VARCHAR(120) NOT NULL UNIQUE) ENGINE=InnoDB;
CREATE TABLE tipo_novedad (id_tipo_novedad INT AUTO_INCREMENT PRIMARY KEY, nombre_tipo VARCHAR(80) NOT NULL UNIQUE, descripcion VARCHAR(255)) ENGINE=InnoDB;

CREATE TABLE empleado (
 codigo_empleado VARCHAR(30) PRIMARY KEY, nombre_empleado VARCHAR(150) NOT NULL,
 documento VARCHAR(30) UNIQUE, fecha_nacimiento DATE, direccion VARCHAR(180), telefono VARCHAR(30),
 correo VARCHAR(120), fecha_ingreso_empresa DATE, estado_empleado VARCHAR(20) NOT NULL DEFAULT 'ACTIVO'
) ENGINE=InnoDB;
CREATE TABLE empleado_historial_laboral (
 id_historial_laboral INT AUTO_INCREMENT PRIMARY KEY, codigo_empleado VARCHAR(30) NOT NULL,
 id_cargo INT NOT NULL, id_dependencia INT NOT NULL, fecha_inicio DATE NOT NULL, fecha_fin DATE,
 FOREIGN KEY (codigo_empleado) REFERENCES empleado(codigo_empleado),
 FOREIGN KEY (id_cargo) REFERENCES cargo(id_cargo), FOREIGN KEY (id_dependencia) REFERENCES dependencia(id_dependencia)
) ENGINE=InnoDB;
CREATE TABLE empleado_historial_salario (
 id_historial_salario INT AUTO_INCREMENT PRIMARY KEY, codigo_empleado VARCHAR(30) NOT NULL,
 salario DECIMAL(12,2) NOT NULL, fecha_inicio DATE NOT NULL, fecha_fin DATE,
 FOREIGN KEY (codigo_empleado) REFERENCES empleado(codigo_empleado)
) ENGINE=InnoDB;
CREATE TABLE empleado_historial_eps (
 id_historial_eps INT AUTO_INCREMENT PRIMARY KEY, codigo_empleado VARCHAR(30) NOT NULL, id_eps INT NOT NULL,
 fecha_inicio DATE NOT NULL, fecha_fin DATE, FOREIGN KEY (codigo_empleado) REFERENCES empleado(codigo_empleado),
 FOREIGN KEY (id_eps) REFERENCES eps(id_eps)
) ENGINE=InnoDB;
CREATE TABLE empleado_historial_arl (
 id_historial_arl INT AUTO_INCREMENT PRIMARY KEY, codigo_empleado VARCHAR(30) NOT NULL, id_arl INT NOT NULL,
 fecha_inicio DATE NOT NULL, fecha_fin DATE, FOREIGN KEY (codigo_empleado) REFERENCES empleado(codigo_empleado),
 FOREIGN KEY (id_arl) REFERENCES arl(id_arl)
) ENGINE=InnoDB;
CREATE TABLE empleado_historial_pension (
 id_historial_pension INT AUTO_INCREMENT PRIMARY KEY, codigo_empleado VARCHAR(30) NOT NULL, id_pension INT NOT NULL,
 fecha_inicio DATE NOT NULL, fecha_fin DATE, FOREIGN KEY (codigo_empleado) REFERENCES empleado(codigo_empleado),
 FOREIGN KEY (id_pension) REFERENCES pension(id_pension)
) ENGINE=InnoDB;

CREATE TABLE periodo_nomina (
 id_periodo INT AUTO_INCREMENT PRIMARY KEY, mes TINYINT NOT NULL, anio SMALLINT NOT NULL,
 fecha_inicio DATE NOT NULL, fecha_fin DATE NOT NULL, estado_periodo VARCHAR(20) NOT NULL DEFAULT 'ABIERTO',
 UNIQUE (mes, anio)
) ENGINE=InnoDB;
CREATE TABLE nomina (
 id_nomina INT AUTO_INCREMENT PRIMARY KEY, codigo_empleado VARCHAR(30) NOT NULL, id_periodo INT NOT NULL,
 salario_base DECIMAL(12,2) NOT NULL, dias_trabajados DECIMAL(5,2) NOT NULL DEFAULT 0,
 bonificacion DECIMAL(12,2) NOT NULL DEFAULT 0, auxilio_transporte DECIMAL(12,2) NOT NULL DEFAULT 0,
 UNIQUE (codigo_empleado, id_periodo), FOREIGN KEY (codigo_empleado) REFERENCES empleado(codigo_empleado),
 FOREIGN KEY (id_periodo) REFERENCES periodo_nomina(id_periodo)
) ENGINE=InnoDB;
CREATE TABLE novedad (
 id_novedad INT AUTO_INCREMENT PRIMARY KEY, id_nomina INT NOT NULL, id_tipo_novedad INT NOT NULL,
 fecha_inicio DATE, fecha_fin DATE, cantidad_dias DECIMAL(5,2) NOT NULL DEFAULT 0, observacion VARCHAR(255),
 FOREIGN KEY (id_nomina) REFERENCES nomina(id_nomina), FOREIGN KEY (id_tipo_novedad) REFERENCES tipo_novedad(id_tipo_novedad)
) ENGINE=InnoDB;

CREATE TABLE pelicula (id_pelicula INT PRIMARY KEY, titulo VARCHAR(255) NOT NULL, anio_lanzamiento SMALLINT) ENGINE=InnoDB;
CREATE TABLE genero (id_genero INT AUTO_INCREMENT PRIMARY KEY, nombre_genero VARCHAR(100) NOT NULL UNIQUE) ENGINE=InnoDB;
CREATE TABLE pelicula_genero (id_pelicula INT NOT NULL, id_genero INT NOT NULL, PRIMARY KEY (id_pelicula,id_genero),
 FOREIGN KEY (id_pelicula) REFERENCES pelicula(id_pelicula), FOREIGN KEY (id_genero) REFERENCES genero(id_genero)) ENGINE=InnoDB;

CREATE TABLE editorial (id_editorial INT AUTO_INCREMENT PRIMARY KEY, nombre_editorial VARCHAR(180) NOT NULL UNIQUE) ENGINE=InnoDB;
CREATE TABLE idioma (id_idioma INT AUTO_INCREMENT PRIMARY KEY, codigo_idioma VARCHAR(20) NOT NULL UNIQUE, nombre_idioma VARCHAR(100)) ENGINE=InnoDB;
CREATE TABLE libro (
 id_libro INT PRIMARY KEY, titulo VARCHAR(500) NOT NULL, rating_promedio DECIMAL(4,2), isbn VARCHAR(20), isbn13 VARCHAR(20),
 numero_paginas INT, cantidad_ratings INT, cantidad_resenas INT, fecha_publicacion DATE, campo_adicional VARCHAR(255),
 id_editorial INT, id_idioma INT, FOREIGN KEY (id_editorial) REFERENCES editorial(id_editorial),
 FOREIGN KEY (id_idioma) REFERENCES idioma(id_idioma)
) ENGINE=InnoDB;
CREATE TABLE autor (id_autor INT AUTO_INCREMENT PRIMARY KEY, nombre_autor VARCHAR(180) NOT NULL UNIQUE) ENGINE=InnoDB;
CREATE TABLE libro_autor (id_libro INT NOT NULL, id_autor INT NOT NULL, PRIMARY KEY (id_libro,id_autor),
 FOREIGN KEY (id_libro) REFERENCES libro(id_libro), FOREIGN KEY (id_autor) REFERENCES autor(id_autor)) ENGINE=InnoDB;

CREATE TABLE rol (id_rol INT AUTO_INCREMENT PRIMARY KEY, nombre_rol VARCHAR(40) NOT NULL UNIQUE, descripcion VARCHAR(255)) ENGINE=InnoDB;
CREATE TABLE usuario (
 id_usuario INT AUTO_INCREMENT PRIMARY KEY, nombre_usuario VARCHAR(60) NOT NULL UNIQUE, contrasena_hash VARCHAR(255) NOT NULL,
 id_rol INT NOT NULL, codigo_empleado VARCHAR(30) UNIQUE, estado_usuario VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
 fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, ultimo_acceso DATETIME,
 FOREIGN KEY (id_rol) REFERENCES rol(id_rol), FOREIGN KEY (codigo_empleado) REFERENCES empleado(codigo_empleado)
) ENGINE=InnoDB;
CREATE TABLE auditoria (
 id_auditoria INT AUTO_INCREMENT PRIMARY KEY, id_usuario INT, accion VARCHAR(80) NOT NULL, modulo VARCHAR(80) NOT NULL,
 fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, descripcion TEXT, FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
) ENGINE=InnoDB;
CREATE TABLE importacion (
 id_importacion INT AUTO_INCREMENT PRIMARY KEY, id_usuario INT, tipo_archivo VARCHAR(40) NOT NULL, nombre_archivo VARCHAR(255) NOT NULL,
 fecha_importacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, estado_importacion VARCHAR(30) NOT NULL,
 total_registros INT NOT NULL DEFAULT 0, registros_correctos INT NOT NULL DEFAULT 0, registros_error INT NOT NULL DEFAULT 0,
 FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)
) ENGINE=InnoDB;
CREATE TABLE detalle_importacion (
 id_detalle INT AUTO_INCREMENT PRIMARY KEY, id_importacion INT NOT NULL, numero_registro INT NOT NULL,
 dato_origen TEXT, mensaje_error TEXT, estado_registro VARCHAR(20) NOT NULL,
 FOREIGN KEY (id_importacion) REFERENCES importacion(id_importacion)
) ENGINE=InnoDB;

INSERT IGNORE INTO rol (nombre_rol,descripcion) VALUES
 ('ADMINISTRADOR','Acceso completo al sistema'),('EMPLEADO','Consulta de informacion propia'),('CONSULTA','Acceso de consulta limitado');
INSERT IGNORE INTO tipo_novedad (nombre_tipo,descripcion) VALUES
 ('INCAPACIDAD','Dias de incapacidad reportados en nomina'),('VACACIONES','Dias de vacaciones reportados en nomina'),
 ('BONIFICACION','Bonificacion registrada en el periodo'),('AUXILIO_TRANSPORTE','Auxilio de transporte del periodo');

SHOW TABLES;
