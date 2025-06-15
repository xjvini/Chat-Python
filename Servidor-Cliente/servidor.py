import socket
import threading
import sqlite3
import logging
from datetime import datetime
import bcrypt
import json

DB_FILE = 'chat1.db'
SERVER_HOST = 'localhost'
SERVER_PORT = 15000
MAX_CONNECTIONS = 50
BUFFER_SIZE = 4096

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ChatServer:
    def __init__(self):
        self.rooms = {"Geral": set()}
        self.clients = {}
        self.clients_lock = threading.Lock()
        self.db_conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.init_db()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.running = False

    def init_db(self):
        with self.db_conn:
            self.db_conn.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL)''')
            self.db_conn.execute('''CREATE TABLE IF NOT EXISTS offline_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT NOT NULL, recipient TEXT NOT NULL, message TEXT NOT NULL, timestamp TEXT NOT NULL)''')
        logging.info("Banco de dados inicializado")

    def register_user(self, username, password):
        try:
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            with self.db_conn:
                self.db_conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed_password))
            return True
        except sqlite3.IntegrityError:
            return False

    def authenticate_user(self, username, password):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()
        if result:
            return bcrypt.checkpw(password.encode('utf-8'), result[0])
        return False

    def start_server(self):
        try:
            self.server_socket.bind((SERVER_HOST, SERVER_PORT))
            self.server_socket.listen(MAX_CONNECTIONS)
            self.running = True
            logging.info(f"Servidor iniciado em {SERVER_HOST}:{SERVER_PORT}")
            while self.running:
                client_socket, address = self.server_socket.accept()
                threading.Thread(target=self.handle_client, args=(client_socket,), daemon=True).start()
        except Exception as e:
            logging.error(f"Erro ao iniciar servidor: {e}")
        finally:
            self.stop_server()

    def handle_client(self, client_socket):
        username = None
        try:
            client_socket.settimeout(60.0)
            buffer = ""
            while True:
                data = client_socket.recv(BUFFER_SIZE).decode('utf-8')
                if not data:
                    break
                buffer += data
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if not line.strip():
                        continue
                    try:
                        message = json.loads(line)
                        if 'action' in message:
                            if message['action'] == 'LOGIN':
                                if self.authenticate_user(message['username'], message['password']):
                                    username = message['username']
                                    with self.clients_lock:
                                        self.clients[client_socket] = {'username': username, 'writer': client_socket}
                                    client_socket.send(json.dumps({"status": "SUCCESS"}).encode('utf-8') + b'\n')
                                    self.broadcast_system(f"{username} entrou no chat")
                                    self.send_user_list_all()
                                    self.send_offline_messages(username)
                                else:
                                    client_socket.send(json.dumps({"status": "ERROR", "message": "Credenciais inválidas"}).encode('utf-8') + b'\n')
                                    return
                            elif message['action'] == 'REGISTER':
                                if self.register_user(message['username'], message['password']):
                                    client_socket.send(json.dumps({"status": "SUCCESS"}).encode('utf-8') + b'\n')
                                else:
                                    client_socket.send(json.dumps({"status": "ERROR", "message": "Usuário já existe"}).encode('utf-8') + b'\n')
                                return
                        elif username:
                            self.process_message(message, username, client_socket)
                    except json.JSONDecodeError:
                        continue
        except (socket.timeout, ConnectionResetError):
            pass
        finally:
            self.remove_client(client_socket, username)

    def process_message(self, message, username, client_socket):
        msg_type = message.get("type")
        if msg_type == "PING":
            client_socket.send(json.dumps({"type": "PONG"}).encode('utf-8') + b'\n')
        elif msg_type == "PUBLIC":
            self.broadcast({"type": "PUBLIC", "sender": username, "message": message["message"], "timestamp": datetime.now().strftime('%H:%M:%S')})
        elif msg_type == "PRIVATE":
            self.send_private({"type": "PRIVATE", "sender": username, "recipient": message["recipient"], "message": message["message"], "timestamp": datetime.now().strftime('%H:%M:%S')})
        elif msg_type == "USERLIST":
            self.send_user_list(client_socket)
        elif msg_type == "ROOM_ACTION":
            self.handle_room_actions(message.get("action"), username, message.get("room"))
        elif msg_type == "ROOM_MESSAGE":
            room = message.get("room")
            if room in self.rooms and username in self.rooms[room]:
                self.broadcast_to_room(room, {"type": "ROOM_MESSAGE", "sender": username, "room": room, "message": message["message"], "timestamp": datetime.now().strftime('%H:%M:%S')})

    def handle_room_actions(self, action, username, room_name):
        if action == "JOIN":
            if room_name not in self.rooms:
                self.rooms[room_name] = set()
            self.rooms[room_name].add(username)
            self.broadcast_to_room(room_name, {"type": "SYSTEM", "message": f"{username} entrou na sala {room_name}"})

    def send_offline_messages(self, username):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT sender, message, timestamp FROM offline_messages WHERE recipient=?", (username,))
        rows = cursor.fetchall()
        for sender, message, timestamp in rows:
            writer = self.get_writer(username)
            if writer:
                writer.send(json.dumps({"type": "PRIVATE", "sender": sender, "recipient": username, "message": message, "timestamp": timestamp}).encode('utf-8') + b'\n')
        with self.db_conn:
            self.db_conn.execute("DELETE FROM offline_messages WHERE recipient=?", (username,))

    def broadcast(self, message):
        with self.clients_lock:
            for client in list(self.clients):
                try:
                    client.send(json.dumps(message).encode('utf-8') + b'\n')
                except:
                    self.remove_client(client, self.clients[client]['username'])

    def broadcast_to_room(self, room, message):
        with self.clients_lock:
            for client, info in self.clients.items():
                if info['username'] in self.rooms.get(room, set()):
                    try:
                        client.send(json.dumps(message).encode('utf-8') + b'\n')
                    except:
                        self.remove_client(client, info['username'])

    def broadcast_system(self, text):
        self.broadcast({"type": "SYSTEM", "message": text})

    def send_private(self, message):
        recipient = message["recipient"]
        writer = self.get_writer(recipient)
        if writer:
            try:
                writer.send(json.dumps(message).encode('utf-8') + b'\n')
            except:
                pass
        else:
            with self.db_conn:
                self.db_conn.execute("INSERT INTO offline_messages (sender, recipient, message, timestamp) VALUES (?, ?, ?, ?)", (message["sender"], recipient, message["message"], message["timestamp"]))

    def get_writer(self, username):
        with self.clients_lock:
            for client, info in self.clients.items():
                if info['username'] == username:
                    return client
        return None

    def send_user_list(self, client_socket):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT username FROM users")
        all_users = [row[0] for row in cursor.fetchall()]
        with self.clients_lock:
            online_users = {info['username'] for info in self.clients.values()}
        user_list = [f"{u}:{'online' if u in online_users else 'offline'}" for u in all_users]
        client_socket.send(json.dumps({"type": "USERLIST", "users": user_list}).encode('utf-8') + b'\n')

    def send_user_list_all(self):
        with self.clients_lock:
            for client in self.clients:
                self.send_user_list(client)

    def remove_client(self, client_socket, username=None):
        with self.clients_lock:
            if client_socket in self.clients:
                if not username:
                    username = self.clients[client_socket]['username']
                del self.clients[client_socket]
                self.broadcast_system(f"{username} saiu do chat")
                self.send_user_list_all()
            try:
                client_socket.close()
            except:
                pass

    def stop_server(self):
        self.running = False
        self.server_socket.close()

if __name__ == "__main__":
    server = ChatServer()
    try:
        server.start_server()
    except KeyboardInterrupt:
        server.stop_server()
