import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
import socket
import threading
import json
import time
import queue
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('chat_client.log', mode='w'),
        logging.StreamHandler()
    ]
)

class ChatClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Chat UABJ - Desconectado")
        self.root.geometry("800x600")
        self.root.minsize(600, 400)
        
        self.host = 'localhost'
        self.port = 54321
        self.socket = None
        self.connected = False
        self.username = None
        
        self.ui_queue = queue.Queue()
        
        self.chat_notebook = None
        self.chat_tabs = {}
        
        self.last_ping_time = 0
        self.ping_interval = 30
        self.typing_timer = None
        
        self.setup_ui()
        self.process_ui_queue()
        
    def setup_ui(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.login_frame = ttk.Frame(self.root)
        self.chat_frame = ttk.Frame(self.root)

        self.setup_login_widgets()
        self.setup_chat_widgets()
        self.setup_status_bar()

        self.login_frame.pack(pady=50, padx=20, fill="both", expand=True)

    def setup_login_widgets(self):
        f = self.login_frame
        ttk.Label(f, text="Bem-vindo!", font=('Arial', 16, 'bold')).pack(pady=20)
        form_frame = ttk.Frame(f)
        form_frame.pack(pady=10)
        ttk.Label(form_frame, text="Username:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.username_entry = ttk.Entry(form_frame, width=30)
        self.username_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(form_frame, text="Password:").grid(row=1, column=0, sticky='w', padx=5, pady=5)
        self.password_entry = ttk.Entry(form_frame, show="*", width=30)
        self.password_entry.grid(row=1, column=1, padx=5, pady=5)
        button_frame = ttk.Frame(f)
        button_frame.pack(pady=20)
        self.login_button = ttk.Button(button_frame, text="Login", command=self.handle_login)
        self.login_button.pack(side=tk.LEFT, padx=10)
        self.register_button = ttk.Button(button_frame, text="Registrar", command=self.handle_register)
        self.register_button.pack(side=tk.LEFT, padx=10)
        self.password_entry.bind('<Return>', lambda e: self.handle_login())
        self.username_entry.focus()
        
    def setup_chat_widgets(self):
        self.chat_frame.columnconfigure(0, weight=3)
        self.chat_frame.columnconfigure(1, weight=1)
        self.chat_frame.rowconfigure(0, weight=1)

        left_panel = ttk.Frame(self.chat_frame)
        left_panel.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
        left_panel.rowconfigure(0, weight=1)
        left_panel.columnconfigure(0, weight=1)

        self.chat_notebook = ttk.Notebook(left_panel)
        self.chat_notebook.grid(row=0, column=0, sticky='nsew')
        self.chat_notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self.chat_notebook.bind("<Button-2>", self.on_middle_click_close)

        self.typing_label = ttk.Label(left_panel, text="", foreground="gray")
        self.typing_label.grid(row=1, column=0, sticky='w', padx=5)
        
        input_frame = ttk.Frame(left_panel)
        input_frame.grid(row=2, column=0, sticky='ew', pady=5)
        input_frame.columnconfigure(0, weight=1)
        self.message_entry = ttk.Entry(input_frame, font=('Arial', 10))
        self.message_entry.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        self.message_entry.bind("<Return>", self.send_message)
        self.message_entry.bind("<KeyPress>", self.handle_typing_start)
        self.send_button = ttk.Button(input_frame, text="Enviar", command=self.send_message)
        self.send_button.grid(row=0, column=1)

        right_panel = ttk.Frame(self.chat_frame)
        right_panel.grid(row=0, column=1, sticky='nsew', padx=5, pady=5)
        right_panel.rowconfigure(0, weight=1)
        right_panel.columnconfigure(0, weight=1)
        
        notebook = ttk.Notebook(right_panel)
        notebook.pack(fill="both", expand=True)

        users_tab = ttk.Frame(notebook)
        notebook.add(users_tab, text='Usuários')
        users_tab.rowconfigure(1, weight=1)
        users_tab.columnconfigure(0, weight=1)
        
        top_users_frame = ttk.Frame(users_tab)
        top_users_frame.grid(row=0, column=0, sticky='ew')
        ttk.Label(top_users_frame, text="Usuários Online/Offline:", font=('Arial', 10, 'bold')).pack(side=tk.LEFT)

        self.users_listbox = tk.Listbox(users_tab, font=('Arial', 9))
        self.users_listbox.grid(row=1, column=0, sticky='nsew', pady=(5,0))
        self.users_listbox.bind('<Double-Button-1>', self.start_private_chat)
        
        logout_button = ttk.Button(users_tab, text="Logout", command=self.handle_logout)
        logout_button.grid(row=2, column=0, sticky='ew', pady=5)

    def setup_status_bar(self):
        status_frame = ttk.Frame(self.root, relief=tk.SUNKEN)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_label = ttk.Label(status_frame, text="v2.5.1", anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.room_label = ttk.Label(status_frame, text="Sala: N/A", anchor=tk.E)
        self.room_label.pack(side=tk.RIGHT, padx=5)
        
    def process_ui_queue(self):
        try:
            while not self.ui_queue.empty():
                action, data = self.ui_queue.get_nowait()
                if action == 'login_success': self._on_login_success(data['socket'])
                elif action == 'operation_failed':
                    messagebox.showerror("Erro", data['message'])
                    self.set_login_buttons_state('normal')
                elif action == 'registration_success':
                    messagebox.showinfo("Info", data['message'])
                    self.set_login_buttons_state('normal')
                elif action == 'display_message': self._display_message(data['target_tab'], data['text'])
                elif action == 'create_tab': self._create_chat_tab(data['name'])
                elif action == 'update_users': self._update_user_list(data['users'])
                elif action == 'update_typing': self.typing_label.config(text=data['text'])
                elif action == 'reset_to_login': self._reset_to_login_view(data.get("message"))
        finally:
            self.root.after(100, self.process_ui_queue)

    def _queue_ui_update(self, action, **kwargs):
        self.ui_queue.put((action, kwargs))

    def _auth_thread(self, request):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((self.host, self.port))
            
            sock.sendall((json.dumps(request) + '\n').encode('utf-8'))
            
            response_data = sock.recv(4096).decode('utf-8')
            if not response_data:
                raise ConnectionError("Servidor não enviou resposta.")
            response = json.loads(response_data.strip())

            if request['action'] == 'LOGIN' and response.get('status') == 'SUCCESS':
                self._queue_ui_update('login_success', socket=sock)
            else:
                sock.close()
                if response.get('status') == 'SUCCESS':
                    self._queue_ui_update('registration_success', message=response.get("message"))
                else:
                    self._queue_ui_update('operation_failed', message=response.get("message"))
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            self._queue_ui_update('operation_failed', message=f"Erro de conexão: {e}")
        except (json.JSONDecodeError, IndexError, ConnectionError) as e:
            self._queue_ui_update('operation_failed', message=f"Resposta inválida do servidor: {e}")

    def handle_login(self):
        self.username = self.username_entry.get().strip()
        password = self.password_entry.get()
        if not self.username or not password:
            messagebox.showerror("Erro", "Usuário e senha são obrigatórios.")
            return

        self.set_login_buttons_state('disabled')
        threading.Thread(target=self._auth_thread, args=({"action": "LOGIN", "username": self.username, "password": password},), daemon=True, name="AuthThread").start()

    def handle_register(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        if not username or not password:
            messagebox.showerror("Erro", "Usuário e senha são obrigatórios.")
            return
        self.set_login_buttons_state('disabled')
        threading.Thread(target=self._auth_thread, args=({"action": "REGISTER", "username": username, "password": password},), daemon=True, name="AuthThread").start()

    def handle_logout(self, message="Você foi desconectado."):
        if not self.connected: return
        self.connected = False
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
                self.socket.close()
            except OSError as e:
                logging.error(f"Erro ao fechar socket no logout: {e}")
        self._queue_ui_update('reset_to_login', message=message)
        
    def _on_login_success(self, sock):
        self.socket = sock
        self.socket.settimeout(None)
        self.connected = True
        
        self.login_frame.pack_forget()
        self.chat_frame.pack(fill=tk.BOTH, expand=True)
        self.root.title(f"Chat UABJ - {self.username}")
        self.set_login_buttons_state('normal')
        
        self.message_entry.focus()
        
        self._create_chat_tab("Geral")

        threading.Thread(target=self._receive_messages, daemon=True, name="ReceiverThread").start()
        threading.Thread(target=self._ping_handler, daemon=True, name="PingThread").start()
        
        self.send_json({"type": "USERLIST"})

    def _receive_messages(self):
        buffer = ""
        while self.connected:
            try:
                data = self.socket.recv(4096)
                if not data:
                    raise ConnectionError("Servidor desconectou.")
                
                buffer += data.decode('utf-8')
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if not line.strip(): continue
                    message = json.loads(line)
                    self.process_server_message(message)
            except (ConnectionError, json.JSONDecodeError, OSError) as e:
                logging.error(f"Erro recebendo mensagens: {e}")
                if self.connected: self.handle_logout("A conexão com o servidor foi perdida.")
                break

    def process_server_message(self, msg):
        msg_type = msg.get("type", "").lower()
        target_tab = "Geral"
        text = ""

        if msg_type in ["public", "room_message", "private", "system"]:
            if msg_type == "public" or (msg_type == "room_message" and msg.get('room') == 'Geral'):
                target_tab = "Geral"
                text = f"[{msg.get('timestamp')}] {msg.get('sender')}: {msg.get('message')}"
            elif msg_type == "private":
                sender = msg.get('sender')
                target_tab = sender
                if sender not in self.chat_tabs:
                    self._queue_ui_update('create_tab', name=sender)
                text = f"<{sender} para você>: {msg.get('message')}"
            elif msg_type == "system":
                 text = f"[SISTEMA] {msg.get('message')}"
            
            if text: self._queue_ui_update('display_message', target_tab=target_tab, text=text)

        elif msg_type == "userlist": self._queue_ui_update('update_users', users=msg.get("users", []))
        elif msg_type == "typing":
            active_chat = self._get_active_chat_name()
            if active_chat == msg.get('sender'):
                status = f"{msg.get('sender')} está digitando..." if msg.get("status") else ""
                self._queue_ui_update('update_typing', text=status)
        elif msg_type == "pong": self.last_ping_time = time.time()

    def _ping_handler(self):
        self.last_ping_time = time.time()
        while self.connected:
            time.sleep(self.ping_interval)
            if time.time() - self.last_ping_time > self.ping_interval * 1.5:
                logging.warning("Não recebeu PONG do servidor, desconectando.")
                self.handle_logout("Perda de conexão com o servidor (timeout).")
                break
            if not self.send_json({"type": "PING"}): break

    def send_json(self, data):
        if not self.connected or not self.socket: return False
        try:
            self.socket.sendall((json.dumps(data) + '\n').encode('utf-8'))
            return True
        except (OSError, ConnectionError):
            if self.connected: self.handle_logout("A conexão com o servidor foi perdida.")
            return False

    def send_message(self, event=None):
        message = self.message_entry.get().strip()
        if not message: return

        active_chat = self._get_active_chat_name()
        if not active_chat: return
        
        msg_data = {"message": message}
        if active_chat == "Geral":
            msg_data.update({"type": "PUBLIC", "message": message})
        else: # Chat Privado
            msg_data.update({"type": "PRIVATE", "recipient": active_chat})
            text = f"<Você para {active_chat}>: {message}"
            self._display_message(active_chat, text)
        
        if self.send_json(msg_data):
            self.message_entry.delete(0, tk.END)
        self.handle_typing_stop()

    def start_private_chat(self, event=None):
        selection = self.users_listbox.curselection()
        if not selection: return
        
        selected_user_str = self.users_listbox.get(selection[0])
        target_user, status = selected_user_str.split(':', 1)
        
        if target_user == self.username:
            messagebox.showinfo("Aviso", "Você não pode iniciar um chat consigo mesmo.")
            return
        
        self._create_chat_tab(target_user)
        self._display_message(target_user, f"[SISTEMA] Chat privado com {target_user} iniciado.")
        if "offline" in status:
            self._display_message(target_user, f"[SISTEMA] {target_user} está offline. Sua mensagem será entregue quando ele(a) se conectar.")

    def handle_typing_start(self, event=None):
        active_chat = self._get_active_chat_name()
        if not active_chat or active_chat == "Geral": return

        if self.typing_timer:
            self.root.after_cancel(self.typing_timer)
        else:
            self.send_json({"type": "TYPING_START", "recipient": active_chat})
        self.typing_timer = self.root.after(2000, self.handle_typing_stop)

    def handle_typing_stop(self):
        active_chat = self._get_active_chat_name()
        if not active_chat or active_chat == "Geral": return

        if self.typing_timer:
            self.root.after_cancel(self.typing_timer)
            self.typing_timer = None
            if self.connected:
                self.send_json({"type": "TYPING_STOP", "recipient": active_chat})

    def on_tab_changed(self, event):
        self._update_room_status()
        self.handle_typing_stop()

    def on_middle_click_close(self, event):
        try:
            
            tab_index = self.chat_notebook.index(f"@{event.x},{event.y}")
            
            tab_name = self.chat_notebook.tab(tab_index, "text")
            
            if tab_name != "Geral":
                self._close_tab(tab_name)
        except tk.TclError:
            pass 
            
    def _create_chat_tab(self, name):
        if name in self.chat_tabs:
            self.chat_notebook.select(self.chat_tabs[name]["frame"])
            return

        
        content_frame = ttk.Frame(self.chat_notebook)
        content_frame.pack(fill="both", expand=True)

        
        self.chat_notebook.add(content_frame, text=name)
        
        
        if name != "Geral":
            top_bar = ttk.Frame(content_frame)
            top_bar.pack(fill='x', padx=2, pady=2)
            
            
            ttk.Label(top_bar, text="").pack(side='left', expand=True) 

            close_button = ttk.Button(top_bar, text="Encerrar",
                                      command=lambda n=name: self._close_tab(n))
            close_button.pack(side="right")

        
        chat_display = scrolledtext.ScrolledText(content_frame, state='disabled', wrap=tk.WORD, font=('Consolas', 10))
        chat_display.pack(fill="both", expand=True, padx=2, pady=(0, 2))

        
        self.chat_tabs[name] = {"frame": content_frame, "display": chat_display}
        self.chat_notebook.select(content_frame)
        self._update_room_status()

    def _close_tab(self, name):
        if name == "Geral" or name not in self.chat_tabs:
            return
        
        frame_to_close = self.chat_tabs[name]["frame"]
        self.chat_notebook.forget(frame_to_close)
        
        del self.chat_tabs[name]
        
        if "Geral" in self.chat_tabs:
            geral_frame = self.chat_tabs["Geral"]["frame"]
            self.chat_notebook.select(geral_frame)
        
        logging.info(f"Aba '{name}' fechada.")

    def _get_active_chat_name(self):
        if not self.chat_notebook or not self.chat_notebook.tabs():
            return None
        try:
            
            selected_frame = self.chat_notebook.select()
            return self.chat_notebook.tab(selected_frame, "text")
        except tk.TclError:
            return None
        return None

    def _display_message(self, target_tab, message):
        if target_tab in self.chat_tabs:
            display_widget = self.chat_tabs[target_tab]["display"]
            display_widget.config(state='normal')
            display_widget.insert(tk.END, message + "\n")
            display_widget.config(state='disabled')
            display_widget.see(tk.END)
        else:
            logging.warning(f"Tentativa de exibir mensagem em uma aba inexistente: {target_tab}")
        
    def _update_user_list(self, users):
        self.users_listbox.delete(0, tk.END)
        online_users, offline_users = [], []
        for user_str in users:
            (online_users if ":online" in user_str else offline_users).append(user_str)

        for user in sorted(online_users):
            self.users_listbox.insert(tk.END, user)
            self.users_listbox.itemconfig(tk.END, {'fg': 'green'})
        for user in sorted(offline_users):
            self.users_listbox.insert(tk.END, user)
            self.users_listbox.itemconfig(tk.END, {'fg': 'gray'})

    def _update_room_status(self):
        active_chat = self._get_active_chat_name()
        if active_chat:
            self.room_label.config(text=f"Chat: {active_chat}")
        else:
            self.room_label.config(text="Sala: N/A")

    def set_login_buttons_state(self, state):
        self.login_button.config(state=state)
        self.register_button.config(state=state)

    def _reset_to_login_view(self, message):
        self.chat_frame.pack_forget()
        if self.chat_notebook:
            for tab in self.chat_notebook.tabs():
                self.chat_notebook.forget(tab)
        self.chat_tabs.clear()
        
        self.login_frame.pack(pady=50, padx=20, fill="both", expand=True)
        self.root.title("Chat Client - Desconectado")
        self.set_login_buttons_state('normal')
        self.password_entry.delete(0, tk.END)
        self.room_label.config(text="Sala: N/A")
        if message: messagebox.showinfo("Info", message)

    def on_closing(self):
        self.handle_logout(message=None)
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    client = ChatClient(root)
    root.mainloop()