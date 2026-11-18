
import getpass
from app import conectar_bd
from werkzeug.security import check_password_hash

conexion = None
cursor = None

try:
    conexion = conectar_bd()
    cursor = conexion.cursor()

    cursor.execute(
        """
        SELECT contrasena_hash
        FROM usuario
        WHERE nombre_usuario = %s
        """,
        ("carlos_test",)
    )

    resultado = cursor.fetchone()

    if resultado is None:
        print("No se encontró el usuario.")
    else:
        contrasena = getpass.getpass(
            "Introduce la contraseña de carlos_test: "
        )

        if check_password_hash(resultado[0], contrasena):
            print("CONTRASEÑA CORRECTA")
        else:
            print("CONTRASEÑA INCORRECTA")

except Exception as error:
    print("Error durante la comprobación:", type(error).__name__)

finally:
    if cursor is not None:
        cursor.close()

    if conexion is not None and conexion.is_connected():
        conexion.close()
