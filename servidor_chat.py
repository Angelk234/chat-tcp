"""
========================================================================================
SERVIDOR DE CHAT DISTRIBUIDO MULTIUSUARIO BASADO EN SOCKETS TCP
========================================================================================
¿QUÉ HACE ESTE SCRIPT?
Actúa como el nodo central (Servidor) de la topología estrella del chat. Escucha conexiones
entrantes de clientes, valida nombres de usuarios contra SQLite, gestiona la concurrencia
usando un hilo (Thread) por cada cliente, y enruta mensajes tanto públicos (Broadcast)
como privados punto a punto (Unicast) mediante sockets TCP.

¿POR QUÉ TCP (Transmission Control Protocol)?
TCP es un protocolo orientado a conexión, confiable y ordenado. Garantiza que ningún mensaje
o paquete se pierda por el camino, que lleguen en el orden exacto en que fueron enviados,
y maneja automáticamente el control de flujo y congestión. Esto es crítico para una
aplicación de chat donde el orden cronológico y la integridad de las conversaciones son fundamentales.
========================================================================================
"""

# Módulo 'socket': Proporciona la interfaz de bajo nivel para comunicación de red (Berkeley Sockets API).
# ¿Por qué? Permite crear endpoints de comunicación de red entre máquinas sobre la pila TCP/IP.
import socket

# Módulo 'threading': Permite ejecutar múltiples tareas concurrentemente en diferentes hilos de ejecución.
# ¿Por qué? Un servidor de chat debe escuchar y atender a varios usuarios al mismo tiempo. Sin hilos,
# el servidor se bloquearía atendiendo a un solo cliente y nadie más podría interactuar ni conectarse.
import threading

# Módulo 'json': Serialización y deserialización de estructuras de datos (diccionarios a texto y viceversa).
# ¿Por qué? TCP solo envía flujos de bytes crudos. Necesitamos un protocolo de capa de aplicación estructurado
# para que cliente y servidor intercambien datos enriquecidos (tipo de mensaje, remitente, texto, hora, etc.).
import json

# Módulo 're': Expresiones regulares para procesamiento de texto avanzado.
# ¿Por qué? Permite analizar sintácticamente (parsear) comandos complejos como /msg 'usuario con espacios' "mensaje".
import re

# Módulo 'datetime': Manejo de marcas de tiempo del sistema.
# ¿Por qué? Permite estampar la hora oficial del servidor en cada mensaje para evitar desfases con los relojes de los clientes.
from datetime import datetime

# Módulo 'db': Controlador de la base de datos SQLite local (db.py).
# ¿Por qué? Separa la lógica de red de la lógica de persistencia de datos (principio de responsabilidad única).
import db

def parsear_comando_privado(texto: str):
    """
    Analiza y extrae el destinatario y el mensaje de un comando privado.
    
    Formatos soportados:
      /msg 'usuario' 'mensaje'
      /msg "usuario" "mensaje"
      /msg usuario mensaje
      /msg 'usuario' mensaje
      
    ¿QUÉ HACE?
    Aplica una expresión regular con grupos de captura alternativos para identificar al usuario
    (con o sin comillas simples/dobles) y separa el cuerpo del mensaje.
    
    ¿POR QUÉ?
    Permite a los usuarios enviar mensajes a destinatarios cuyos nombres contengan espacios
    o caracteres especiales si los encierran entre comillas, además de tolerar comillas en el mensaje.
    Retorna una tupla: (destinatario, mensaje) o (None, None) si la sintaxis no coincide.
    """
    # Explicación del patrón regex:
    # ^/msg\s+           -> Inicia con '/msg' seguido de uno o más espacios.
    # (?:'([^']+)'|      -> Opción 1: nombre entre comillas simples 'nombre'
    #  \"([^\"]+)\"|     -> Opción 2: nombre entre comillas dobles "nombre"
    #  (\S+))            -> Opción 3: nombre como palabra simple sin espacios
    # \s+(.+)$           -> Espacio(s) separador(es) y todo el resto es el mensaje (con re.DOTALL incluye saltos).
    patron = r"^/msg\s+(?:'([^']+)'|\"([^\"]+)\"|(\S+))\s+(.+)$"
    match = re.match(patron, texto.strip(), re.DOTALL)
    if not match:
        return None, None

    # Obtenemos el grupo que haya coincidido (grupo 1, 2 o 3)
    destinatario = match.group(1) or match.group(2) or match.group(3)
    contenido = match.group(4).strip()

    # Si el mensaje completo venía entre comillas externas, se las retiramos limpiamente
    if (contenido.startswith("'") and contenido.endswith("'") and len(contenido) >= 2) or \
       (contenido.startswith('"') and contenido.endswith('"') and len(contenido) >= 2):
        contenido = contenido[1:-1]

    return destinatario.strip(), contenido.strip()

# -------------------------------------------------------------
# PARÁMETROS DE CONFIGURACIÓN DE RED
# -------------------------------------------------------------
# HOST "0.0.0.0":
# ¿Por qué? Hace que el socket escuche en TODAS las interfaces de red disponibles de la máquina
# (localhost 127.0.0.1, interfaz Wi-Fi, Ethernet, etc.). Así otros dispositivos en la red LAN pueden conectarse.
HOST = "0.0.0.0"

# PUERTO 5000:
# ¿Por qué? Un puerto por encima de 1024 (puertos no privilegiados) que identifica unívocamente este servicio
# de chat en el sistema operativo sin requerir privilegios de superusuario/administrador.
PUERTO = 5000

# MAX_CLIENTES 5:
# ¿Por qué? Requisito de la práctica para limitar la sala a un máximo de 5 clientes simultáneos.
MAX_CLIENTES = 5

# DICCIONARIO DE CONEXIONES ACTIVAS:
# Estructura: { socket_conexion: "NombreUsuario" }
# ¿Por qué? Mantiene la tabla de enrutamiento en memoria RAM: asocia directamente el socket TCP abierto
# de un cliente con su nombre de usuario registrado. Permite buscar el socket de un destinatario rápidamente.
clientes_conectados = {}

# CANDADO DE SINCRONIZACIÓN (Lock):
# ¿Por qué? En Python, múltiples hilos ejecutándose a la vez pueden intentar leer y escribir en el diccionario
# 'clientes_conectados' al mismo tiempo (ej: un cliente se desconecta mientras otro entra o difunde un mensaje).
# Si no usamos un Lock, se producirían condiciones de carrera (race conditions) o errores como
# 'RuntimeError: dictionary changed size during iteration'.
lock_clientes = threading.Lock()

def enviar_json(conexion: socket.socket, datos: dict) -> bool:
    """
    Serializa un diccionario a JSON y lo transmite por el socket TCP con delimitador '\\n'.
    
    ¿QUÉ HACE?
    Convierte el diccionario a un string JSON en UTF-8, le añade un salto de línea '\\n' al final
    y lo envía usando conexion.sendall(). Captura excepciones de red si el cliente se desconectó.
    
    ¿POR QUÉ EL DELIMITADOR '\\n' (Framing en TCP)?
    ¡Concepto crucial de redes!: TCP es un protocolo de 'stream' continuo de bytes, NO un protocolo
    de paquetes con límites definidos. Dos mensajes enviados rápidamente pueden llegar pegados en una sola
    lectura recv() (Packet Agglutination) o un mensaje largo puede llegar cortado en dos fragmentos
    (Packet Fragmentation).
    Al delimitar cada mensaje JSON con '\\n', el receptor sabe con absoluta certeza dónde termina un mensaje
    y dónde empieza el siguiente.
    
    ¿POR QUÉ 'sendall' EN LUGAR DE 'send'?
    conexion.send() no garantiza enviar todos los bytes pasados si el buffer del socket del sistema está lleno;
    sendall() continúa transmitiendo automáticamente en un bucle interno hasta que todos los bytes hayan salido.
    """
    try:
        # ensure_ascii=False permite tildes y caracteres especiales en español sin escaparlos como \\uXXXX
        mensaje_serializado = json.dumps(datos, ensure_ascii=False) + "\n"
        conexion.sendall(mensaje_serializado.encode("utf-8"))
        return True
    except (ConnectionResetError, BrokenPipeError, OSError):
        # Si el socket está cerrado o la red falló, devolvemos False para que el llamador gestione la baja
        return False

def difundir(datos: dict, remitente: socket.socket = None):
    """
    Envía un mensaje a todos los clientes actualmente conectados (Técnica de BROADCAST).
    
    ¿QUÉ HACE?
    Obtiene una copia segura de todos los sockets activos bajo el Lock, y envía el paquete JSON a cada uno.
    Si remitente está presente y se desea excluir, se puede hacer; por defecto remitente=None envía a todos.
    
    ¿POR QUÉ HACER UNA COPIA list(clientes_conectados.keys())?
    Al convertir las llaves a una lista dentro del bloque 'with lock_clientes', liberamos el candado
    rápidamente y evitamos iterar directamente sobre el diccionario mientras otros hilos añaden o quitan clientes.
    
    ¿POR QUÉ 'desconectar_cliente' SI FALLA EL ENVÍO?
    Si un socket genera un error al intentar enviarle datos (BrokenPipeError), significa que el cliente murió
    silenciosamente (ej: corte de luz, apagado de app forzado). Esto limpia inmediatamente los clientes 'zombies'.
    """
    with lock_clientes:
        conexiones = list(clientes_conectados.keys())

    for cliente in conexiones:
        if cliente != remitente or remitente is None:
            exito = enviar_json(cliente, datos)
            if not exito:
                # Si falló el envío a este cliente, lo removemos de la sala
                desconectar_cliente(cliente, notificar=False)

def desconectar_cliente(conexion: socket.socket, notificar: bool = True):
    """
    Cierra la conexión TCP de un cliente de forma segura y limpia su estado en el servidor.
    
    ¿QUÉ HACE?
    1. Remueve el socket del diccionario 'clientes_conectados' protegiéndolo con el Lock.
    2. Cierra físicamente el socket con conexion.close().
    3. Si el usuario estaba autenticado y notificar=True, avisa al resto de participantes que abandonó la sala
       y difunde la nueva lista de usuarios en línea.
       
    ¿POR QUÉ?
    Liberar los recursos de red del sistema operativo (descriptores de archivos del socket) y mantener
    sincronizada la lista de conectados en tiempo real para todos los clientes visuales.
    """
    nombre_usuario = None
    with lock_clientes:
        # Extraemos y eliminamos al cliente del mapa atómicamente
        if conexion in clientes_conectados:
            nombre_usuario = clientes_conectados.pop(conexion)

    try:
        # Cierre del socket físico TCP
        conexion.close()
    except OSError:
        pass  # Si ya estaba cerrado por el sistema operativo, ignoramos el error

    # Notificar a los demás usuarios si el cliente que salió tenía un nombre registrado
    if nombre_usuario and notificar:
        hora_salida = datetime.now().strftime("%H:%M:%S")
        print(f"[-] {nombre_usuario} se ha desconectado.")
        
        # Enviar aviso global al chat
        difundir({
            "tipo": "sistema",
            "texto": f"{nombre_usuario} salió del grupo",
            "hora": hora_salida
        })
        
        # Actualizar la lista en tiempo real en los clientes
        difundir_lista_usuarios()

def difundir_lista_usuarios():
    """
    Difunde a todos los clientes la lista completa de nombres de usuarios conectados en este momento.
    
    ¿QUÉ HACE?
    Extrae la lista de valores de 'clientes_conectados' y envía un mensaje tipo 'actualizacion_conectados'.
    
    ¿POR QUÉ?
    Permite que la interfaz gráfica (la barra superior de WhatsApp de cada usuario) se actualice
    automáticamente mostrando exactamente quiénes están en línea en cada instante (ej: '3/5 en línea: Juan, Ana, Pedro').
    """
    with lock_clientes:
        lista = list(clientes_conectados.values())
    difundir({
        "tipo": "actualizacion_conectados",
        "usuarios": lista
    })

def atender_cliente(conexion: socket.socket, direccion: tuple):
    """
    Función de trabajo (Worker Thread) que atiende a un cliente específico de principio a fin.
    
    ¿QUÉ HACE?
    Se ejecuta en un hilo separado para CADA conexión aceptada.
    1. Comprueba si la sala excedió el límite MAX_CLIENTES.
    2. Recibe bytes del socket en un bucle continuo.
    3. Reconstruye los paquetes JSON delimitados por '\\n' mediante un buffer de recepción.
    4. Procesa el Login: comprueba que el nombre no esté duplicado en caliente y lo registra en SQLite.
    5. Envía el historial de los últimos 5 mensajes públicos almacenados en la BD.
    6. Procesa comandos (/salir, /quienes, /msg destinatario mensaje) o difunde mensajes normales al grupo.
    7. Al terminar el bucle o detectar error, limpia la conexión en el bloque 'finally'.
    
    ¿POR QUÉ ES NECESARIO EL BUFFER?
    Debido a la naturaleza de streaming de TCP, una sola llamada a conexion.recv(2048) puede devolver
    medio mensaje, un mensaje completo, o tres mensajes juntos.
    El acumulador 'buffer' almacena texto hasta que encuentra '\\n', garantizando que cada json.loads()
    reciba exactamente un objeto JSON completo y válido.
    """
    print(f"[+] Nueva conexión entrante desde {direccion}")
    nombre_registrado = None

    try:
        # PASO 1: Validar límite de capacidad de la sala
        with lock_clientes:
            total_actual = len(clientes_conectados)

        if total_actual >= MAX_CLIENTES:
            print(f"[!] Conexión rechazada para {direccion}: Sala llena ({total_actual}/{MAX_CLIENTES})")
            enviar_json(conexion, {
                "tipo": "error",
                "motivo": "SALA_LLENA",
                "mensaje": f"La sala está llena (máximo {MAX_CLIENTES} personas conectadas)."
            })
            conexion.close()
            return

        # Acumulador de texto para el framing de TCP
        buffer = ""
        autenticado = False

        # BUCLE PRINCIPAL DE LECTURA DEL SOCKET
        while True:
            # recv(2048) se bloquea en el hilo hasta que llegan datos de la red o el cliente cierra el socket
            datos_raw = conexion.recv(2048)
            if not datos_raw:
                # En sockets TCP, cuando recv() devuelve 0 bytes (bytes vacíos), significa
                # formalmente que el otro extremo cerró la conexión (FIN packet recibido)
                break

            # Decodificamos los bytes recibidos a texto UTF-8
            buffer += datos_raw.decode("utf-8", errors="replace")

            # Desempaquetamos todos los mensajes completos separados por salto de línea (\n)
            while "\n" in buffer:
                linea, buffer = buffer.split("\n", 1)
                linea = linea.strip()
                if not linea:
                    continue

                try:
                    payload = json.loads(linea)
                except json.JSONDecodeError:
                    # Ignorar paquetes malformados si ocurriera algún fallo de serialización
                    continue

                accion = payload.get("accion")

                # -------------------------------------------------------------
                # PASO 2: FASE DE LOGIN / AUTENTICACIÓN
                # -------------------------------------------------------------
                if not autenticado:
                    if accion == "login":
                        nombre_solicitado = payload.get("usuario", "").strip()
                        
                        # Validación: Nombre en blanco
                        if not nombre_solicitado:
                            enviar_json(conexion, {
                                "tipo": "error",
                                "mensaje": "El nombre de usuario no puede estar en blanco."
                            })
                            continue

                        # Validación: Nombre duplicado entre usuarios activos conectados
                        with lock_clientes:
                            nombres_activos = [n.lower() for n in clientes_conectados.values()]
                            if nombre_solicitado.lower() in nombres_activos:
                                enviar_json(conexion, {
                                    "tipo": "error",
                                    "motivo": "USUARIO_EN_USO",
                                    "mensaje": f"Ya hay una persona conectada con el nombre '{nombre_solicitado}'."
                                })
                                continue

                            # Validación de concurrencia: que la sala no se haya llenado mientras esperaba
                            if len(clientes_conectados) >= MAX_CLIENTES:
                                enviar_json(conexion, {
                                    "tipo": "error",
                                    "motivo": "SALA_LLENA",
                                    "mensaje": f"La sala se llenó mientras intentabas ingresar."
                                })
                                conexion.close()
                                return

                            # Consultar o registrar usuario en la base de datos SQLite
                            es_nuevo, nombre_final = db.obtener_o_crear_usuario(nombre_solicitado)
                            
                            # Asociamos este socket con el nombre del usuario
                            clientes_conectados[conexion] = nombre_final
                            nombre_registrado = nombre_final
                            autenticado = True

                        hora_ingreso = datetime.now().strftime("%H:%M:%S")
                        print(f"[OK] Usuario autenticado: '{nombre_final}' ({'Nuevo' if es_nuevo else 'Existente'})")

                        # Confirmar al cliente que su login fue aceptado
                        enviar_json(conexion, {
                            "tipo": "login_ok",
                            "usuario": nombre_final,
                            "es_nuevo": es_nuevo,
                            "mensaje": f"Bienvenido {'(Usuario creado)' if es_nuevo else ''}"
                        })

                        # PASO 3: ENVIAR HISTORIAL DE ÚLTIMOS 5 MENSAJES
                        # ¿Por qué? Requisito del chat grupal: dar contexto al usuario de la conversación reciente.
                        ultimos = db.obtener_ultimos_mensajes(5)
                        enviar_json(conexion, {
                            "tipo": "historial",
                            "mensajes": ultimos
                        })

                        # Avisar al resto de miembros que alguien nuevo ingresó
                        difundir({
                            "tipo": "sistema",
                            "texto": f"{nombre_final} se unió al grupo",
                            "hora": hora_ingreso
                        }, remitente=conexion)

                        # Enviar la lista de usuarios actualizada a todos
                        difundir_lista_usuarios()
                    continue

                # -------------------------------------------------------------
                # PASO 4: PROCESAMIENTO DE MENSAJES Y COMANDOS DE CLIENTES CONECTADOS
                # -------------------------------------------------------------
                if accion == "mensaje":
                    texto = payload.get("texto", "").strip()
                    if not texto:
                        continue

                    # COMANDO 1: /salir
                    # ¿Qué hace? Cierra la sesión del cliente voluntariamente.
                    if texto.lower() == "/salir":
                        print(f"[*] {nombre_registrado} ejecutó /salir")
                        return  # Al salir de la función, 'finally' se encarga de cerrar y notificar

                    # COMANDO 2: /quienes
                    # ¿Qué hace? Devuelve la lista de usuarios conectados solo a quien lo solicitó.
                    elif texto.lower() == "/quienes":
                        with lock_clientes:
                            usuarios_activos = list(clientes_conectados.values())
                        enviar_json(conexion, {
                            "tipo": "quienes",
                            "usuarios": usuarios_activos
                        })

                    # COMANDO 3: /msg (MENSAJERÍA PRIVADA / UNICAST)
                    # Sintaxis: /msg 'destinatario' 'mensaje'
                    elif texto.lower().startswith("/msg"):
                        hora_actual = datetime.now().strftime("%H:%M:%S")
                        destinatario, contenido = parsear_comando_privado(texto)

                        # Validación: formato incorrecto
                        if not destinatario or not contenido:
                            enviar_json(conexion, {
                                "tipo": "sistema",
                                "texto": "Uso: /msg 'usuario' 'mensaje' o /msg usuario mensaje",
                                "hora": hora_actual
                            })
                            continue

                        # Buscar el socket TCP correspondiente al destinatario deseado
                        target_sock = None
                        target_nombre = None
                        with lock_clientes:
                            for s, n in clientes_conectados.items():
                                if n.lower() == destinatario.lower():
                                    target_sock = s
                                    target_nombre = n
                                    break

                        # Validación: ¿Destinatario no encontrado en la sala?
                        if not target_sock:
                            enviar_json(conexion, {
                                "tipo": "sistema",
                                "texto": f"Error: El usuario '{destinatario}' no está conectado.",
                                "hora": hora_actual
                            })
                        # Validación: ¿Intentar enviarse mensaje a uno mismo?
                        elif target_sock == conexion:
                            enviar_json(conexion, {
                                "tipo": "sistema",
                                "texto": "No puedes enviarte un mensaje privado a ti mismo.",
                                "hora": hora_actual
                            })
                        else:
                            # Guardar en SQLite como mensaje privado (destinatario poblado)
                            db.guardar_mensaje(nombre_registrado, contenido, hora_actual, destinatario=target_nombre)
                            print(f"[{hora_actual}] [PRIVADO] {nombre_registrado} -> {target_nombre}: {contenido}")

                            # Sub-paso 1: Entregar mensaje al destinatario (Unicast)
                            enviar_json(target_sock, {
                                "tipo": "mensaje_privado",
                                "de": nombre_registrado,
                                "para": target_nombre,
                                "texto": contenido,
                                "hora": hora_actual,
                                "es_mio": False
                            })

                            # Sub-paso 2: Confirmar al remitente que se envió para pintarlo en su pantalla
                            enviar_json(conexion, {
                                "tipo": "mensaje_privado",
                                "de": nombre_registrado,
                                "para": target_nombre,
                                "texto": contenido,
                                "hora": hora_actual,
                                "es_mio": True
                            })

                    # MENSAJE PÚBLICO / BROADCAST
                    else:
                        hora_actual = datetime.now().strftime("%H:%M:%S")
                        
                        # 1. Guardar en SQLite para persistencia en el historial general
                        db.guardar_mensaje(nombre_registrado, texto, hora_actual)
                        print(f"[{hora_actual}] {nombre_registrado}: {texto}")

                        # 2. Difundir a todos los clientes (incluyendo remitente para confirmar entrega)
                        difundir({
                            "tipo": "mensaje",
                            "usuario": nombre_registrado,
                            "texto": texto,
                            "hora": hora_actual
                        })

                # Solicitud directa de /quienes por botón de la interfaz gráfica
                elif accion == "quienes":
                    with lock_clientes:
                        usuarios_activos = list(clientes_conectados.values())
                    enviar_json(conexion, {
                        "tipo": "quienes",
                        "usuarios": usuarios_activos
                    })

                # Solicitud de salida directa por botón "Salir" de la interfaz
                elif accion == "salir":
                    return

    except (ConnectionResetError, ConnectionAbortedError):
        # Ocurre cuando el cliente cierra bruscamente la app o pierde conexión
        print(f"[!] Conexión perdida inesperadamente con {direccion} ({nombre_registrado or 'No autenticado'})")
    finally:
        # El bloque finally se ejecuta SIEMPRE, garantizando la limpieza del cliente aunque haya excepciones
        desconectar_cliente(conexion, notificar=True)

def iniciar_servidor():
    """
    Función principal de arranque del servidor TCP.
    
    ¿QUÉ HACE?
    1. Inicializa la base de datos SQLite.
    2. Crea el socket pasivo de escucha TCP (AF_INET, SOCK_STREAM).
    3. Configura opciones para reutilizar la dirección IP/Puerto inmediatamente.
    4. Enlaza (bind) el socket a la IP y puerto configurados.
    5. Pone el socket a escuchar (listen) conexiones entrantes.
    6. Entra en un bucle infinito aceptando clientes (accept()) y lanzando un hilo por cada uno.
    
    ¿POR QUÉ 'socket.AF_INET' Y 'socket.SOCK_STREAM'?
    AF_INET: Especifica la familia de direcciones IPv4.
    SOCK_STREAM: Especifica el tipo de socket para el protocolo TCP orientado a flujos de conexión.
    
    ¿POR QUÉ 'setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)'?
    Cuando un servidor TCP se cierra, el sistema operativo mantiene el puerto en estado TIME_WAIT
    durante 1-2 minutos para asegurar que paquetes rezagados no interfieran. Esta opción le indica
    al kernel que permita volver a usar el puerto de inmediato sin lanzar el error "Address already in use".
    
    ¿POR QUÉ 'daemon=True' EN LOS HILOS?
    Los hilos demonio terminan automáticamente cuando el hilo principal finaliza (por ejemplo al presionar Ctrl+C).
    Esto evita que hilos secundarios de clientes queden colgados impidiendo que el proceso de Python termine.
    """
    # 1. Aseguramos que las tablas de base de datos existan
    db.inicializar_bd()

    # 2. Creación del socket TCP
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # 3. Configuración para reutilizar puerto de inmediato
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        # 4. Enlazar la dirección IP y puerto al socket
        servidor.bind((HOST, PUERTO))
        
        # 5. Poner el socket en modo de escucha pasiva
        servidor.listen()
        
        print("=" * 60)
        print("  [+] SERVIDOR DE MENSAJERIA TCP (GRUPO WHATSAPP) INICIADO")
        print(f"  Direccion: {HOST}:{PUERTO}")
        print(f"  Limite de sala: {MAX_CLIENTES} usuarios simultaneos")
        print(f"  Base de datos SQLite: {db.DB_NAME}")
        print("=" * 60)

        # 6. Bucle de aceptación de clientes
        while True:
            # accept() bloquea la ejecución hasta que un nuevo cliente solicita conectarse (Handshake TCP).
            # Retorna una tupla: (conexion, direccion) donde 'conexion' es un NUEVO socket dedicado
            # exclusivamente para hablar con ese cliente, dejando el socket 'servidor' libre para seguir escuchando.
            conexion, direccion = servidor.accept()
            
            # Lanzamos un nuevo hilo de ejecución para atender al cliente en paralelo
            hilo = threading.Thread(
                target=atender_cliente,
                args=(conexion, direccion),
                daemon=True
            )
            hilo.start()

    except KeyboardInterrupt:
        # Captura Ctrl + C en consola para apagar limpiamente el servidor
        print("\n[!] Servidor detenido manualmente.")
    finally:
        # Cierra el socket maestro de escucha
        servidor.close()

if __name__ == "__main__":
    # Punto de entrada cuando se ejecuta directamente el archivo (python servidor_chat.py)
    iniciar_servidor()

