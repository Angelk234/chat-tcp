import socket
import threading
import json
import tkinter as tk
from tkinter import ttk, messagebox

# Colores inspirados en WhatsApp Light Mode
COLOR_HEADER = "#075E54"        # Verde oscuro WhatsApp
COLOR_HEADER_LIGHT = "#128C7E"  # Verde secundario WhatsApp
COLOR_BG_CHAT = "#EFEAE2"       # Color clásico fondo WhatsApp
COLOR_BURBUJA_PROPIA = "#D9FDD3"# Verde suave para mensajes enviados
COLOR_BURBUJA_OTRO = "#FFFFFF"  # Blanco para mensajes recibidos
COLOR_TEXTO = "#111B21"         # Texto principal oscuro
COLOR_HORA = "#667781"          # Gris para marcas de tiempo
COLOR_CHECK = "#53BDEB"         # Azul para doble check
COLOR_SISTEMA_BG = "#FFFFFF"    # Fondo para avisos de sistema
COLOR_SISTEMA_TEXTO = "#54656F" # Texto avisos sistema
COLOR_INPUT_BG = "#F0F2F5"      # Barra inferior

class ClienteWhatsAppApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Grupo Practica")
        self.root.geometry("480x680")
        self.root.minsize(400, 550)
        self.root.configure(bg="#F0F2F5")

        self.socket_cliente = None
        self.hilo_receptor = None
        self.conectado = False
        self.nombre_usuario = ""

        # Mostrar pantalla inicial de Login
        self.mostrar_pantalla_login()

        # Manejo de cierre de ventana
        self.root.protocol("WM_DELETE_WINDOW", self.cerrar_aplicacion)

    # -------------------------------------------------------------
    # 1. PANTALLA DE LOGIN / REGISTRO
    # -------------------------------------------------------------
    def mostrar_pantalla_login(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        self.frame_login = tk.Frame(self.root, bg="#F0F2F5")
        self.frame_login.pack(expand=True, fill="both")

        # Banner superior
        banner = tk.Frame(self.frame_login, bg=COLOR_HEADER, height=140)
        banner.pack(fill="x")
        banner.pack_propagate(False)

        lbl_icono = tk.Label(banner, text="💬", font=("Segoe UI Emoji", 36), bg=COLOR_HEADER, fg="white")
        lbl_icono.pack(pady=(15, 0))

        lbl_titulo = tk.Label(
            banner,
            text="Chat TCP",
            font=("Segoe UI", 16, "bold"),
            bg=COLOR_HEADER,
            fg="white"
        )
        lbl_titulo.pack()

        # Tarjeta central
        card = tk.Frame(self.frame_login, bg="white", padx=30, pady=30, relief="groove", bd=1)
        card.pack(pady=40, padx=40, fill="x")

        lbl_sub = tk.Label(
            card,
            text="Inicia sesión o regístrate",
            font=("Segoe UI", 12, "bold"),
            bg="white",
            fg=COLOR_TEXTO
        )
        lbl_sub.pack(anchor="w", pady=(0, 15))

        # Campo Usuario
        lbl_user = tk.Label(card, text="Nombre de usuario:", font=("Segoe UI", 10), bg="white", fg=COLOR_HORA)
        lbl_user.pack(anchor="w")

        self.entry_usuario = tk.Entry(card, font=("Segoe UI", 11), relief="solid", bd=1)
        self.entry_usuario.pack(fill="x", pady=(4, 15), ipady=4)
        self.entry_usuario.focus()
        self.entry_usuario.bind("<Return>", lambda e: self.iniciar_conexion())

        # Configuración de Servidor (Host y Puerto)
        frame_red = tk.Frame(card, bg="white")
        frame_red.pack(fill="x", pady=(0, 15))

        lbl_host = tk.Label(frame_red, text="Servidor:", font=("Segoe UI", 9), bg="white", fg=COLOR_HORA)
        lbl_host.grid(row=0, column=0, sticky="w")
        self.entry_host = tk.Entry(frame_red, font=("Segoe UI", 9), width=18, relief="solid", bd=1)
        self.entry_host.insert(0, "localhost")
        self.entry_host.grid(row=1, column=0, padx=(0, 10), ipady=2)

        lbl_puerto = tk.Label(frame_red, text="Puerto:", font=("Segoe UI", 9), bg="white", fg=COLOR_HORA)
        lbl_puerto.grid(row=0, column=1, sticky="w")
        self.entry_puerto = tk.Entry(frame_red, font=("Segoe UI", 9), width=8, relief="solid", bd=1)
        self.entry_puerto.insert(0, "5000")
        self.entry_puerto.grid(row=1, column=1, ipady=2)

        # Botón entrar
        self.btn_entrar = tk.Button(
            card,
            text="INGRESAR AL CHAT",
            font=("Segoe UI", 11, "bold"),
            bg=COLOR_HEADER_LIGHT,
            fg="white",
            activebackground=COLOR_HEADER,
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            command=self.iniciar_conexion
        )
        self.btn_entrar.pack(fill="x", pady=(10, 10), ipady=6)

        # Mensaje de estado
        self.lbl_estado_login = tk.Label(
            card,
            text="",
            font=("Segoe UI", 9),
            bg="white",
            fg="#D93025",
            wraplength=300
        )
        self.lbl_estado_login.pack(pady=(5, 0))

    def set_estado_login(self, texto: str, es_error: bool = True):
        color = "#D93025" if es_error else "#0A7B3E"
        self.lbl_estado_login.config(text=texto, fg=color)

    # -------------------------------------------------------------
    # 2. CONEXIÓN TCP
    # -------------------------------------------------------------
    def iniciar_conexion(self):
        usuario = self.entry_usuario.get().strip()
        host = self.entry_host.get().strip()
        puerto_str = self.entry_puerto.get().strip()

        if not usuario:
            self.set_estado_login("Por favor ingresa un nombre de usuario.")
            return

        try:
            puerto = int(puerto_str)
        except ValueError:
            self.set_estado_login("El puerto debe ser numérico.")
            return

        self.btn_entrar.config(state="disabled")
        self.set_estado_login("Conectando al servidor...", es_error=False)

        hilo_con = threading.Thread(
            target=self._conectar_en_segundo_plano,
            args=(host, puerto, usuario),
            daemon=True
        )
        hilo_con.start()

    def _conectar_en_segundo_plano(self, host: str, puerto: int, usuario: str):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((host, puerto))
            sock.settimeout(None)

            self.socket_cliente = sock
            # Enviar solicitud de login
            paquete = {"accion": "login", "usuario": usuario}
            sock.sendall((json.dumps(paquete) + "\n").encode("utf-8"))

            # Iniciar hilo de escucha
            self.hilo_receptor = threading.Thread(target=self._bucle_recepcion, daemon=True)
            self.hilo_receptor.start()

        except ConnectionRefusedError:
            self.root.after(0, self.set_estado_login, "No se pudo conectar: Servidor apagado o inalcanzable.")
            self.root.after(0, lambda: self.btn_entrar.config(state="normal"))
        except Exception as e:
            self.root.after(0, self.set_estado_login, f"Error de conexión: {str(e)}")
            self.root.after(0, lambda: self.btn_entrar.config(state="normal"))

    # -------------------------------------------------------------
    # 3. INTERFAZ DE CHAT (ESTILO WHATSAPP)
    # -------------------------------------------------------------
    def inicializar_pantalla_chat(self, nombre_confirmado: str, es_nuevo: bool):
        self.nombre_usuario = nombre_confirmado
        self.conectado = True

        for widget in self.root.winfo_children():
            widget.destroy()

        # Contenedor Principal
        self.frame_principal = tk.Frame(self.root, bg=COLOR_BG_CHAT)
        self.frame_principal.pack(fill="both", expand=True)

        # ENCABEZADO WHATSAPP
        header = tk.Frame(self.frame_principal, bg=COLOR_HEADER, height=65)
        header.pack(fill="x")
        header.pack_propagate(False)

        # Avatar circular simulado con iniciales
        frame_avatar = tk.Frame(header, bg=COLOR_HEADER_LIGHT, width=42, height=42)
        frame_avatar.pack(side="left", padx=(12, 10), pady=11)
        frame_avatar.pack_propagate(False)

        lbl_avatar = tk.Label(frame_avatar, text="67", font=("Segoe UI", 12, "bold"), bg=COLOR_HEADER_LIGHT, fg="white")
        lbl_avatar.pack(expand=True)

        # Info del grupo
        frame_info = tk.Frame(header, bg=COLOR_HEADER)
        frame_info.pack(side="left", fill="y", pady=10)

        lbl_nombre_chat = tk.Label(
            frame_info,
            text="Grupo Practica",
            font=("Segoe UI", 12, "bold"),
            bg=COLOR_HEADER,
            fg="white"
        )
        lbl_nombre_chat.pack(anchor="w")

        self.lbl_participantes = tk.Label(
            frame_info,
            text=f"Tú: {self.nombre_usuario} | Conectando...",
            font=("Segoe UI", 8),
            bg=COLOR_HEADER,
            fg="#E0F2F1"
        )
        self.lbl_participantes.pack(anchor="w")

        # Botones del header (/quienes y /salir)
        frame_botones_header = tk.Frame(header, bg=COLOR_HEADER)
        frame_botones_header.pack(side="right", padx=10)

        btn_quienes = tk.Button(
            frame_botones_header,
            text="👥 Quiénes",
            font=("Segoe UI", 9, "bold"),
            bg=COLOR_HEADER_LIGHT,
            fg="white",
            activebackground=COLOR_HEADER,
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            padx=8,
            pady=3,
            command=self.solicitar_quienes
        )
        btn_quienes.pack(side="left", padx=5)

        btn_salir = tk.Button(
            frame_botones_header,
            text="🚪 Salir",
            font=("Segoe UI", 9, "bold"),
            bg="#C62828",
            fg="white",
            activebackground="#8E0000",
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            padx=8,
            pady=3,
            command=self.enviar_salir
        )
        btn_salir.pack(side="left", padx=5)

        # ÁREA DE MENSAJES (CANVAS SCROLLABLE)
        frame_chat_container = tk.Frame(self.frame_principal, bg=COLOR_BG_CHAT)
        frame_chat_container.pack(fill="both", expand=True)

        self.canvas_chat = tk.Canvas(frame_chat_container, bg=COLOR_BG_CHAT, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(frame_chat_container, orient="vertical", command=self.canvas_chat.yview)

        self.frame_mensajes = tk.Frame(self.canvas_chat, bg=COLOR_BG_CHAT)
        self.frame_mensajes.bind(
            "<Configure>",
            lambda e: self.canvas_chat.configure(scrollregion=self.canvas_chat.bbox("all"))
        )

        self.canvas_window = self.canvas_chat.create_window((0, 0), window=self.frame_mensajes, anchor="nw")
        self.canvas_chat.configure(yscrollcommand=self.scrollbar.set)

        self.canvas_chat.bind("<Configure>", self._ajustar_ancho_canvas)
        self.canvas_chat.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Permitir scroll con la rueda del ratón
        self.canvas_chat.bind_all("<MouseWheel>", self._on_mousewheel)

        # Barra de ayuda con atajos
        lbl_hint = tk.Label(
            self.frame_principal,
            text="💡 Privado: /msg 'usuario' 'mensaje'  •  /quienes  •  /salir",
            font=("Segoe UI", 8),
            bg="#EAEBED",
            fg=COLOR_HORA,
            pady=3
        )
        lbl_hint.pack(fill="x", side="bottom")

        # BARRA INFERIOR DE ENTRADA DE MENSAJES
        frame_input = tk.Frame(self.frame_principal, bg=COLOR_INPUT_BG, height=60, padx=10, pady=8)
        frame_input.pack(fill="x", side="bottom")

        self.entry_mensaje = tk.Entry(
            frame_input,
            font=("Segoe UI", 11),
            bg="white",
            fg=COLOR_TEXTO,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#D1D7DB",
            highlightcolor=COLOR_HEADER_LIGHT
        )
        self.entry_mensaje.pack(side="left", fill="both", expand=True, ipady=6, padx=(0, 8))
        self.entry_mensaje.bind("<Return>", lambda e: self.enviar_mensaje())
        self.entry_mensaje.focus()

        # Botón Enviar estilo WhatsApp
        btn_enviar = tk.Button(
            frame_input,
            text="➤",
            font=("Segoe UI", 14, "bold"),
            bg=COLOR_HEADER_LIGHT,
            fg="white",
            activebackground=COLOR_HEADER,
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            width=3,
            command=self.enviar_mensaje
        )
        btn_enviar.pack(side="right")

        # Mensaje de bienvenida inicial
        if es_nuevo:
            self.agregar_burbuja_sistema("¡Bienvenido! Tu usuario ha sido registrado en la base de datos.")
        else:
            self.agregar_burbuja_sistema(f"Bienvenido de nuevo, {self.nombre_usuario}.")

    def _ajustar_ancho_canvas(self, event):
        self.canvas_chat.itemconfig(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas_chat.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _scroll_al_final(self):
        self.root.update_idletasks()
        self.canvas_chat.yview_moveto(1.0)

    # -------------------------------------------------------------
    # 4. RENDERIZADO DE BURBUJAS ESTILO WHATSAPP
    # -------------------------------------------------------------
    def agregar_burbuja_mensaje(self, remitente: str, texto: str, hora: str):
        es_mio = (remitente.lower() == self.nombre_usuario.lower())

        fila_msg = tk.Frame(self.frame_mensajes, bg=COLOR_BG_CHAT, padx=10, pady=4)
        fila_msg.pack(fill="x", anchor="e" if es_mio else "w")

        color_bg = COLOR_BURBUJA_PROPIA if es_mio else COLOR_BURBUJA_OTRO

        # Marco de la burbuja con borde y fondo tipo WhatsApp
        burbuja = tk.Frame(
            fila_msg,
            bg=color_bg,
            padx=10,
            pady=6,
            relief="solid",
            bd=1
        )
        # Configurar borde sutil
        burbuja.config(highlightbackground="#D1D7DB", highlightthickness=1)

        if es_mio:
            burbuja.pack(anchor="e", padx=(40, 5))
            # Indicador de mensaje al grupo
            lbl_tipo = tk.Label(
                burbuja,
                text="👥 Mensaje al grupo",
                font=("Segoe UI", 7, "italic"),
                fg="#5E7480",
                bg=color_bg
            )
            lbl_tipo.pack(anchor="w", pady=(0, 2))
        else:
            burbuja.pack(anchor="w", padx=(5, 40))
            # Encabezado con nombre del remitente e indicador de grupo
            frame_cabecera = tk.Frame(burbuja, bg=color_bg)
            frame_cabecera.pack(anchor="w", fill="x", pady=(0, 2))

            lbl_autor = tk.Label(
                frame_cabecera,
                text=remitente,
                font=("Segoe UI", 9, "bold"),
                fg=COLOR_HEADER_LIGHT,
                bg=color_bg
            )
            lbl_autor.pack(side="left")

            lbl_tipo = tk.Label(
                frame_cabecera,
                text=" • 👥 Grupo",
                font=("Segoe UI", 7, "italic"),
                fg="#5E7480",
                bg=color_bg
            )
            lbl_tipo.pack(side="left", padx=(3, 0))

        # Texto del mensaje
        lbl_texto = tk.Label(
            burbuja,
            text=texto,
            font=("Segoe UI", 10),
            fg=COLOR_TEXTO,
            bg=color_bg,
            justify="left",
            wraplength=280
        )
        lbl_texto.pack(anchor="w")

        # Pie con Hora y Checkmarks
        frame_meta = tk.Frame(burbuja, bg=color_bg)
        frame_meta.pack(anchor="e", pady=(2, 0))

        lbl_hora = tk.Label(
            frame_meta,
            text=hora,
            font=("Segoe UI", 8),
            fg=COLOR_HORA,
            bg=color_bg
        )
        lbl_hora.pack(side="left")

        if es_mio:
            lbl_check = tk.Label(
                frame_meta,
                text=" ✓✓",
                font=("Segoe UI", 8, "bold"),
                fg=COLOR_CHECK,
                bg=color_bg
            )
            lbl_check.pack(side="left")

        self._scroll_al_final()

    def agregar_burbuja_privada(self, de: str, para: str, texto: str, hora: str, es_mio: bool):
        """Muestra un mensaje privado con diseño distintivo (candado y aviso de privacidad)."""
        fila_msg = tk.Frame(self.frame_mensajes, bg=COLOR_BG_CHAT, padx=10, pady=4)
        fila_msg.pack(fill="x", anchor="e" if es_mio else "w")

        # Colores específicos para mensajes privados
        color_bg = "#E8F5E9" if es_mio else "#F3E5F5"
        color_borde = "#81C784" if es_mio else "#BA68C8"
        color_tag = "#2E7D32" if es_mio else "#7B1FA2"

        burbuja = tk.Frame(
            fila_msg,
            bg=color_bg,
            padx=10,
            pady=6,
            relief="solid",
            bd=1
        )
        burbuja.config(highlightbackground=color_borde, highlightthickness=1)

        if es_mio:
            burbuja.pack(anchor="e", padx=(40, 5))
            etiqueta = f"🔒 [PRIVADO] para @{para}"
        else:
            burbuja.pack(anchor="w", padx=(5, 40))
            etiqueta = f"🔒 [PRIVADO] de @{de} (solo para ti)"

        # Encabezado privado
        lbl_encabezado = tk.Label(
            burbuja,
            text=etiqueta,
            font=("Segoe UI", 8, "bold"),
            fg=color_tag,
            bg=color_bg
        )
        lbl_encabezado.pack(anchor="w", pady=(0, 2))

        # Texto del mensaje
        lbl_texto = tk.Label(
            burbuja,
            text=texto,
            font=("Segoe UI", 10),
            fg=COLOR_TEXTO,
            bg=color_bg,
            justify="left",
            wraplength=280
        )
        lbl_texto.pack(anchor="w")

        # Pie con Hora y Checkmarks
        frame_meta = tk.Frame(burbuja, bg=color_bg)
        frame_meta.pack(anchor="e", pady=(2, 0))

        lbl_hora = tk.Label(
            frame_meta,
            text=hora,
            font=("Segoe UI", 8),
            fg=COLOR_HORA,
            bg=color_bg
        )
        lbl_hora.pack(side="left")

        if es_mio:
            lbl_check = tk.Label(
                frame_meta,
                text=" ✓✓",
                font=("Segoe UI", 8, "bold"),
                fg=COLOR_CHECK,
                bg=color_bg
            )
            lbl_check.pack(side="left")

        self._scroll_al_final()

    def agregar_burbuja_sistema(self, texto: str, hora: str = ""):
        """Muestra un aviso centrado del sistema (ej. entrada/salida o info)."""
        fila_sis = tk.Frame(self.frame_mensajes, bg=COLOR_BG_CHAT, pady=5)
        fila_sis.pack(fill="x")

        contenido = f" {texto} " + (f"• {hora} " if hora else "")

        burbuja_sis = tk.Label(
            fila_sis,
            text=contenido,
            font=("Segoe UI", 8, "italic"),
            fg=COLOR_SISTEMA_TEXTO,
            bg=COLOR_SISTEMA_BG,
            padx=12,
            pady=4,
            relief="solid",
            bd=1
        )
        burbuja_sis.config(highlightbackground="#E0E0E0", highlightthickness=1)
        burbuja_sis.pack(anchor="center")

        self._scroll_al_final()

    # -------------------------------------------------------------
    # 5. ENVÍO DE ACCIONES Y COMANDOS
    # -------------------------------------------------------------
    def enviar_mensaje(self):
        if not self.conectado or not self.socket_cliente:
            return

        texto = self.entry_mensaje.get().strip()
        if not texto:
            return

        self.entry_mensaje.delete(0, tk.END)

        # Atajos de comandos por texto
        if texto.lower() == "/salir":
            self.enviar_salir()
            return
        elif texto.lower() == "/quienes":
            self.solicitar_quienes()
            return

        # Envío de mensaje normal
        paquete = {"accion": "mensaje", "texto": texto}
        self._enviar_paquete(paquete)

    def solicitar_quienes(self):
        """Envía la solicitud /quienes al servidor."""
        if self.conectado:
            self._enviar_paquete({"accion": "quienes"})

    def enviar_salir(self):
        """Envía el comando /salir y cierra la conexión."""
        if self.conectado:
            self._enviar_paquete({"accion": "salir"})
        self.cerrar_aplicacion()

    def _enviar_paquete(self, data: dict):
        try:
            linea = json.dumps(data) + "\n"
            self.socket_cliente.sendall(linea.encode("utf-8"))
        except OSError:
            self.agregar_burbuja_sistema("Error al enviar mensaje. Conexión perdida.")

    # -------------------------------------------------------------
    # 6. HILO DE RECEPCIÓN DE DATOS DEL SERVIDOR
    # -------------------------------------------------------------
    def _bucle_recepcion(self):
        buffer = ""
        try:
            while True:
                datos = self.socket_cliente.recv(2048)
                if not datos:
                    break

                buffer += datos.decode("utf-8", errors="replace")

                while "\n" in buffer:
                    linea, buffer = buffer.split("\n", 1)
                    linea = linea.strip()
                    if not linea:
                        continue

                    try:
                        paquete = json.loads(linea)
                    except json.JSONDecodeError:
                        continue

                    self.root.after(0, self._procesar_paquete_servidor, paquete)

        except (ConnectionResetError, OSError):
            pass
        finally:
            if self.conectado:
                self.root.after(0, self._manejar_desconexion)

    def _procesar_paquete_servidor(self, paquete: dict):
        tipo = paquete.get("tipo")

        # 1. Error del servidor (ej. Sala llena, nombre ocupado)
        if tipo == "error":
            mensaje = paquete.get("mensaje", "Ocurrió un error en el servidor.")
            if not self.conectado:
                self.set_estado_login(mensaje, es_error=True)
                self.btn_entrar.config(state="normal")
            else:
                messagebox.showerror("Aviso del Servidor", mensaje)

        # 2. Login aceptado
        elif tipo == "login_ok":
            usuario = paquete.get("usuario")
            es_nuevo = paquete.get("es_nuevo", False)
            self.inicializar_pantalla_chat(usuario, es_nuevo)

        # 3. Historial de últimos 5 mensajes
        elif tipo == "historial":
            mensajes = paquete.get("mensajes", [])
            if mensajes:
                self.agregar_burbuja_sistema("─── Historial: Últimos mensajes ───")
                for m in mensajes:
                    self.agregar_burbuja_mensaje(m["usuario"], m["texto"], m["timestamp"])
                self.agregar_burbuja_sistema("──────────────────────────────────")

        # 4. Mensaje regular del chat
        elif tipo == "mensaje":
            remitente = paquete.get("usuario", "Anónimo")
            texto = paquete.get("texto", "")
            hora = paquete.get("hora", "")
            self.agregar_burbuja_mensaje(remitente, texto, hora)

        # 5. Notificación del sistema
        elif tipo == "sistema":
            texto = paquete.get("texto", "")
            hora = paquete.get("hora", "")
            self.agregar_burbuja_sistema(texto, hora)

        # 6. Respuesta del comando /quienes
        elif tipo == "quienes":
            usuarios = paquete.get("usuarios", [])
            total = len(usuarios)
            texto_lista = f"👥 Conectados ({total}/5): " + ", ".join(usuarios)
            self.agregar_burbuja_sistema(texto_lista)

        # 7. Actualización silenciosa de miembros conectados en el header
        elif tipo == "actualizacion_conectados":
            usuarios = paquete.get("usuarios", [])
            if hasattr(self, "lbl_participantes"):
                total = len(usuarios)
                self.lbl_participantes.config(
                    text=f"Tú: {self.nombre_usuario} | {total}/5 en línea ({', '.join(usuarios)})"
                )

        # 8. Mensaje privado recibido o enviado
        elif tipo == "mensaje_privado":
            de = paquete.get("de", "Anónimo")
            para = paquete.get("para", "")
            texto = paquete.get("texto", "")
            hora = paquete.get("hora", "")
            es_mio = paquete.get("es_mio", False)
            self.agregar_burbuja_privada(de, para, texto, hora, es_mio)

    def _manejar_desconexion(self):
        self.conectado = False
        if hasattr(self, "frame_mensajes"):
            self.agregar_burbuja_sistema("Te has desconectado del servidor.")
        else:
            self.set_estado_login("Conexión finalizada por el servidor.")
            self.btn_entrar.config(state="normal")

    def cerrar_aplicacion(self):
        """Cierre ordenado de la aplicación."""
        if self.conectado and self.socket_cliente:
            try:
                self.socket_cliente.sendall((json.dumps({"accion": "salir"}) + "\n").encode("utf-8"))
                self.socket_cliente.close()
            except OSError:
                pass
        self.root.destroy()

if __name__ == "__main__":
    ventana = tk.Tk()
    app = ClienteWhatsAppApp(ventana)
    ventana.mainloop()
