import sqlite3
from datetime import datetime

DB_NAME = "chat_distribuido.db"

def obtener_conexion():
    """Retorna una conexión a la base de datos SQLite."""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_bd():
    """Crea las tablas necesarias si no existen."""
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        # Tabla de usuarios registrados
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL COLLATE NOCASE,
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Tabla de mensajes persistentes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mensajes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL,
                destinatario TEXT DEFAULT NULL,
                texto TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Asegurar columna destinatario en bases de datos ya creadas
        try:
            cursor.execute("ALTER TABLE mensajes ADD COLUMN destinatario TEXT DEFAULT NULL")
        except sqlite3.OperationalError:
            pass

        conn.commit()

def obtener_o_crear_usuario(nombre: str) -> tuple[bool, str]:
    """
    Busca o crea un usuario por su nombre.
    Retorna (es_nuevo, nombre_estandarizado).
    """
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El nombre de usuario no puede estar vacío.")

    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nombre FROM usuarios WHERE nombre = ?", (nombre,))
        fila = cursor.fetchone()
        if fila:
            return False, fila["nombre"]
        else:
            cursor.execute("INSERT INTO usuarios (nombre) VALUES (?)", (nombre,))
            conn.commit()
            return True, nombre

def guardar_mensaje(usuario: str, texto: str, timestamp: str, destinatario: str = None):
    """Guarda un mensaje en la base de datos (público si destinatario es None, o privado)."""
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO mensajes (usuario, destinatario, texto, timestamp)
            VALUES (?, ?, ?, ?)
        """, (usuario, destinatario, texto, timestamp))
        conn.commit()

def obtener_ultimos_mensajes(limite: int = 5) -> list[dict]:
    """
    Recupera los últimos N mensajes públicos registrados en orden cronológico (más antiguos primero).
    Los mensajes privados no se revelan en el historial público del grupo.
    """
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT usuario, texto, timestamp
            FROM mensajes
            WHERE destinatario IS NULL
            ORDER BY id DESC
            LIMIT ?
        """, (limite,))
        filas = cursor.fetchall()
        # Invertir para que queden en orden cronológico ascendente
        mensajes = [
            {"usuario": f["usuario"], "texto": f["texto"], "timestamp": f["timestamp"]}
            for f in reversed(filas)
        ]
        return mensajes

# Inicializar al importar
inicializar_bd()

if __name__ == "__main__":
    print("Probando base de datos...")
    es_nuevo, u = obtener_o_crear_usuario("Admin")
    print(f"Usuario: {u}, Nuevo: {es_nuevo}")
    guardar_mensaje("Admin", "Mensaje de prueba", datetime.now().strftime("%H:%M:%S"))
    print("Últimos mensajes:", obtener_ultimos_mensajes(5))
