import tkinter as tk
from tkinter import scrolledtext, messagebox
import socket
import threading
import json
import time

class ChatClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Chat Client")
        self.root.geometry("600x400")
        
        self.host = 'localhost'
        self.port = 15000
        self.socket = None
        self.connected = False
        self.username = None
        self.password = None
        self.buffer = ""
        
        self.current_room = None
        self.private_chat_target = None
        self.last_ping = time.time()
        self.typing = False
        self.typing_timer = None
        self.reconnecting = False
        
        self.setup_ui()
        
    def setup_ui(self):
        self.login_frame = tk.Frame(self.root)
        self.login_frame.pack(pady=20)
        
        tk.Label(self.login_frame, text="Username:").grid(row=0, column=0, padx=5, pady=5)
        self.username_entry = tk.Entry(self.login_frame)
        self.username_entry.grid(row=0, column=1, padx=5, pady=5)
        
        tk.Label(self.login_frame, text="Password:").grid(row=1, column=0, padx=5, pady=5)
        self.password_entry = tk.Entry(self.login_frame, show="*")
        self.password_entry.grid(row=1, column=1, padx=5, pady=5)
        
        self.login_button = tk.Button(self.login_frame, text="Login", command=self.handle_login)
        self.login_button.grid(row=2, column=0, padx=5, pady=5)
        
        self.register_button = tk.Button(self.login_frame, text="Register", command=self.handle_register)
        self.register_button.grid(row=2, column=1, padx=5, pady=5)
        
        self.status_label = tk.Label(self.root, text="", fg="red")
        self.status_label.pack()
        
        self.chat_frame = tk.Frame(self.root)
        
        self.chat_display = scrolledtext.ScrolledText(self.chat_frame, state='disabled')
        self.chat_display.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        self.input_frame = tk.Frame(self.chat_frame)
        self.input_frame.pack(padx=10, pady=10, fill=tk.X)
        
        self.message_entry = tk.Entry(self.input_frame)
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.message_entry.bind("<Return>", lambda e: self.send_message())
        self.message_entry.bind("<KeyPress>", self.handle_typing_start)
        
        self.send_button = tk.Button(self.input_frame, text="Send", command=self.send_message)
        self.send_button.pack(side=tk.RIGHT)
        
        self.users_frame = tk.Frame(self.chat_frame)
        self.users_frame.pack(padx=10, pady=10, fill=tk.X)
        
        self.users_label = tk.Label(self.users_frame, text="Online Users:")
        self.users_label.pack(anchor=tk.W)
        
        self.users_listbox = tk.Listbox(self.users_frame, height=5)
        self.users_listbox.pack(fill=tk.X)
        
        self.private_chat_button = tk.Button(self.users_frame, text="Start Private Chat", command=self.start_private_chat)
        self.private_chat_button.pack(fill=tk.X)

        self.typing_label = tk.Label(self.users_frame, text="")
        self.typing_label.pack(anchor=tk.W)

        self.rooms_frame = tk.Frame(self.chat_frame)
        self.rooms_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        tk.Label(self.rooms_frame, text="Salas:").pack()
        self.rooms_listbox = tk.Listbox(self.rooms_frame, height=10)
        self.rooms_listbox.pack(fill=tk.Y)
        
        self.room_entry = tk.Entry(self.rooms_frame)
        self.room_entry.pack(pady=5)
        
        self.join_room_button = tk.Button(self.rooms_frame, text="Entrar/Criar", command=self.join_room)
        self.join_room_button.pack()

    def join_room(self):
        room_name = self.room_entry.get().strip()
        if room_name and self.connected:
            msg = {"type": "ROOM_ACTION", "action": "JOIN", "room": room_name}
            self.send_json(msg)
            self.current_room = room_name
            self.display_message(f"[SISTEMA] Entrou na sala: {room_name}")

    def handle_register(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        if not username or not password:
            self.show_error("Nome de usuário e senha obrigatórios")
            return
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.host, self.port))
            request = {"action": "REGISTER", "username": username, "password": password}
            s.send(json.dumps(request).encode('utf-8') + b'\n')
            response = self.receive_response(s)
            s.close()
            if response['status'] == 'SUCCESS':
                messagebox.showinfo("Sucesso", "Registrado com sucesso!")
            else:
                self.show_error(response.get("message", "Erro no registro"))
        except Exception as e:
            self.show_error(str(e))

    def handle_login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        if not username or not password:
            self.show_error("Nome de usuário e senha obrigatórios")
            return
        self.username = username
        self.password = password
        self.connect_and_authenticate()

    def connect_and_authenticate(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            request = {"action": "LOGIN", "username": self.username, "password": self.password}
            self.socket.send(json.dumps(request).encode('utf-8') + b'\n')
            response = self.receive_response(self.socket)
            if response['status'] == 'SUCCESS':
                self.connected = True
                self.show_chat_interface()
                self.status_label.config(text=f"Conectado como {self.username}", fg="green")
                threading.Thread(target=self.receive_messages, daemon=True).start()
                self.send_ping()
            else:
                self.show_error(response.get("message", "Falha no login"))
                self.socket.close()
        except Exception as e:
            self.show_error(str(e))

    def receive_response(self, sock):
        buffer = ""
        while True:
            data = sock.recv(1024).decode('utf-8')
            if not data:
                break
            buffer += data
            if '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                return json.loads(line)

    def receive_messages(self):
        while self.connected:
            try:
                data = self.socket.recv(4096).decode('utf-8')
                if not data:
                    raise Exception("Desconectado")
                self.buffer += data
                while '\n' in self.buffer:
                    line, self.buffer = self.buffer.split('\n', 1)
                    if not line.strip():
                        continue
                    message = json.loads(line.strip())
                    self.process_message(message)
            except Exception as e:
                self.connected = False
                self.display_message("[SISTEMA] Conexão perdida. Tentando reconectar...")
                if not self.reconnecting:
                    self.reconnecting = True
                    threading.Thread(target=self.auto_reconnect, daemon=True).start()
                break

    def auto_reconnect(self):
        while not self.connected:
            time.sleep(5)
            try:
                self.display_message("[SISTEMA] Tentando reconectar...")
                self.connect_and_authenticate()
                if self.connected:
                    self.reconnecting = False
                    break
            except:
                continue

    def send_ping(self):
        if self.connected:
            try:
                self.send_json({"type": "PING"})
                self.root.after(30000, self.send_ping)
            except:
                self.connected = False

    def send_json(self, message):
        self.socket.send(json.dumps(message).encode('utf-8') + b'\n')

    def process_message(self, message):
        msg_type = message.get("type")
        if msg_type == "PUBLIC":
            self.display_message(f"[{message.get('timestamp')}] {message.get('sender')}: {message.get('message')}")
        elif msg_type == "PRIVATE":
            self.display_message(f"[PV {message.get('timestamp')}] {message.get('sender')}: {message.get('message')}")
        elif msg_type == "ROOM_MESSAGE":
            self.display_message(f"[{message.get('room')}] {message.get('sender')}: {message.get('message')}")
        elif msg_type == "SYSTEM":
            self.display_message(f"[SISTEMA] {message.get('message')}")
        elif msg_type == "USERLIST":
            self.update_user_list(message.get("users", []))
        elif msg_type == "TYPING":
            sender = message.get("sender")
            status = message.get("status")
            if status:
                self.typing_label.config(text=f"{sender} está digitando...")
            else:
                self.typing_label.config(text="")

    def handle_typing_start(self, event=None):
        if not self.typing:
            if self.private_chat_target:
                self.send_json({"type": "TYPING_START", "recipient": self.private_chat_target})
            self.typing = True
        if self.typing_timer:
            self.root.after_cancel(self.typing_timer)
        self.typing_timer = self.root.after(2000, self.handle_typing_stop)

    def handle_typing_stop(self):
        if self.typing and self.private_chat_target:
            self.send_json({"type": "TYPING_STOP", "recipient": self.private_chat_target})
        self.typing = False

    def show_chat_interface(self):
        self.login_frame.pack_forget()
        self.chat_frame.pack(fill=tk.BOTH, expand=True)
        self.request_user_list()

    def request_user_list(self):
        if self.connected:
            self.send_json({"type": "USERLIST"})

    def send_message(self, event=None):
        message = self.message_entry.get().strip()
        if message and self.connected:
            if self.current_room:
                msg = {"type": "ROOM_MESSAGE", "room": self.current_room, "message": message}
            elif self.private_chat_target:
                msg = {"type": "PRIVATE", "recipient": self.private_chat_target, "message": message}
            else:
                msg = {"type": "PUBLIC", "message": message}
            self.send_json(msg)
            self.message_entry.delete(0, tk.END)
            self.handle_typing_stop()

    def start_private_chat(self):
        selection = self.users_listbox.curselection()
        if not selection:
            self.show_error("Selecione um usuário")
            return
        selected = self.users_listbox.get(selection[0])
        if selected.startswith("●"):
            self.private_chat_target = selected[2:].strip()
            self.display_message(f"[SISTEMA] Chat privado com {self.private_chat_target}")
        else:
            self.show_error("Usuário offline")

    def update_user_list(self, users):
        self.users_listbox.delete(0, tk.END)
        for user in users:
            parts = user.split(":")
            username, status = parts[0], parts[1]
            status_symbol = "●" if status == "online" else "○"
            self.users_listbox.insert(tk.END, f"{status_symbol} {username}")

    def display_message(self, message):
        self.chat_display.config(state='normal')
        self.chat_display.insert(tk.END, message + "\n")
        self.chat_display.config(state='disabled')
        self.chat_display.see(tk.END)

    def show_error(self, message):
        self.status_label.config(text=message, fg="red")

    def on_closing(self):
        self.connected = False
        if self.socket:
            self.socket.close()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    client = ChatClient(root)
    root.protocol("WM_DELETE_WINDOW", client.on_closing)
    root.mainloop()
