import socket
import threading
import sqlite3
import logging
from datetime import datetime
import bcrypt
import json
import time
import queue
from concurrent.futures import ThreadPoolExecutor

DB_FILE = 'chat1.db'
SERVER_HOST = 'localhost'
SERVER_PORT = 54321
MAX_CONNECTIONS = 100
BUFFER_SIZE = 8192
PING_INTERVAL = 30
PING_TIMEOUT = 1800  # 30 minutos

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('chat_server.log', mode='w'),
        logging.StreamHandler()
    ]
)

class ChatServer:
    def __init__(self):
        self.rooms = {"Geral": set()}
        self.clients = {}
        self.clients_lock = threading.RLock()
        self.message_queue = queue.Queue()
        self.executor = ThreadPoolExecutor(max_workers=20, thread_name_prefix='ClientThread')
        self.running = False

        self.ping_interval = PING_INTERVAL
        self.ping_timeout = PING_TIMEOUT

        self.init_db()
        
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        self.message_worker = threading.Thread(target=self.process_message_queue, name="MessageQueueThread", daemon=True)
        self.cleanup_thread = threading.Thread(target=self.cleanup_connections, name="CleanupThread", daemon=True)

    def init_db(self):
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_login TIMESTAMP)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS offline_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT NOT NULL, recipient TEXT NOT NULL, 
                message TEXT NOT NULL, timestamp TEXT NOT NULL, delivered BOOLEAN DEFAULT FALSE)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT, sender TEXT NOT NULL,
                message TEXT NOT NULL, timestamp TEXT NOT NULL)''')
        logging.info("Banco de dados inicializado.")

    def start_server(self):
        try:
            self.server_socket.bind((SERVER_HOST, SERVER_PORT))
            self.server_socket.listen(MAX_CONNECTIONS)
            self.running = True
            self.message_worker.start()
            self.cleanup_thread.start()
            logging.info(f"Servidor iniciado em {SERVER_HOST}:{SERVER_PORT}")
            while self.running:
                client_socket, address = self.server_socket.accept()
                logging.info(f"Nova conexão de {address}")
                self.executor.submit(self.handle_client, client_socket, address)
        except OSError as e:
            if self.running: logging.error(f"Erro de Socket: {e}")
        finally:
            self.stop_server()

    def handle_client(self, client_socket, address):
        username = None
        try:
            username = self._authentication_loop(client_socket)
            if username:
                self._message_loop(client_socket, username)
        except (ConnectionResetError, ConnectionAbortedError):
            logging.warning(f"Conexão com {address} (usuário: {username}) foi fechada abruptamente.")
        except Exception as e:
            logging.error(f"Erro inesperado com {address} (usuário: {username}): {e}", exc_info=True)
        finally:
            if username: self.remove_client(client_socket, username)

    def _authentication_loop(self, client_socket):
        client_socket.settimeout(60.0)
        buffer = ""
        while self.running:
            try:
                data = client_socket.recv(BUFFER_SIZE)
                if not data: return None
                buffer += data.decode('utf-8')
                if '\n' not in buffer: continue
                
                line, buffer = buffer.split('\n', 1)
                message = json.loads(line.strip())
                
                action = message.get('action')
                username = message.get('username', '').strip()
                password = message.get('password', '')

                if action == 'REGISTER':
                    success, msg = self.register_user(username, password)
                    self.send_response(client_socket, {"status": "SUCCESS" if success else "ERROR", "message": msg})
                
                elif action == 'LOGIN':
                    with self.clients_lock:
                        if any(info['username'] == username for info in self.clients.values()):
                            self.send_response(client_socket, {"status": "ERROR", "message": "Usuário já está online."})
                            continue
                    if self.authenticate_user(username, password):
                        self.send_response(client_socket, {"status": "SUCCESS", "message": "Login bem-sucedido."})
                        self.add_client(client_socket, username)
                        client_socket.settimeout(None) # Timeout desativado após login
                        return username
                    else:
                        self.send_response(client_socket, {"status": "ERROR", "message": "Credenciais inválidas."})
            except (json.JSONDecodeError, UnicodeDecodeError):
                logging.warning("Recebido dado malformado durante autenticação.")
                continue
            except socket.timeout:
                logging.warning("Timeout durante autenticação.")
                return None
        return None

    def _message_loop(self, client_socket, username):
        buffer = ""
        while self.running:
            data = client_socket.recv(BUFFER_SIZE)
            if not data: break
            buffer += data.decode('utf-8')
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                if not line.strip(): continue
                message = json.loads(line)
                self.add_to_queue({'type': 'process_message', 'message': message, 'username': username, 'client_socket': client_socket})

    def add_client(self, client_socket, username):
        with self.clients_lock:
            self.clients[client_socket] = {'username': username, 'last_ping': time.time(), 'rooms': {'Geral'}}
        self.rooms['Geral'].add(username)
        logging.info(f"Usuário {username} entrou no chat.")
        self.add_to_queue({'type': 'broadcast_system', 'message': f"{username} entrou no chat."})
        self.add_to_queue({'type': 'send_user_list_all'})
        self.add_to_queue({'type': 'send_offline_messages', 'username': username})

    def process_message_queue(self):
        while self.running:
            try:
                item = self.message_queue.get(timeout=1)
                if item is None: break
                msg_type = item.get('type')

                if msg_type == 'broadcast_system':
                    self.broadcast_system(item['message'])
                elif msg_type == 'send_user_list_all':
                    self.send_user_list_all()
                elif msg_type == 'send_offline_messages':
                    self.send_offline_messages(item['username'])
                elif msg_type == 'process_message':
                    self.process_client_message(item['message'], item['username'], item['client_socket'])
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"Erro fatal processando fila: {e}", exc_info=True)

    def process_client_message(self, message, username, client_socket):
        msg_type = message.get("type")
        
        with self.clients_lock:
            if client_socket in self.clients:
                self.clients[client_socket]['last_ping'] = time.time()
        
        if msg_type == "PING":
            self.send_response(client_socket, {"type": "PONG"})
        
        # --- CORREÇÃO CRÍTICA ---
        # Adiciona a lógica que faltava para responder ao pedido da lista.
        elif msg_type == "USERLIST":
            logging.info(f"Atendendo pedido de lista de usuários de '{username}'.")
            self.send_user_list_all()
            
        elif msg_type == "PUBLIC":
            msg_data = {"type": "PUBLIC", "sender": username, "message": message["message"], "timestamp": datetime.now().strftime('%H:%M:%S')}
            self.broadcast_to_room("Geral", msg_data)
            self.save_message_history("Geral", username, message["message"])
            
        elif msg_type == "PRIVATE":
            recipient = message.get("recipient")
            msg_data = {"type": "PRIVATE", "sender": username, "recipient": recipient, "message": message["message"], "timestamp": datetime.now().strftime('%H:%M:%S')}
            self.send_private(msg_data)

        elif msg_type == "ROOM_MESSAGE":
            room, msg = message.get("room"), message["message"]
            with self.clients_lock:
                is_member = room in self.clients.get(client_socket, {}).get('rooms', set())
            if is_member:
                msg_data = {"type": "ROOM_MESSAGE", "sender": username, "room": room, "message": msg, "timestamp": datetime.now().strftime('%H:%M:%S')}
                self.broadcast_to_room(room, msg_data)
                self.save_message_history(room, username, msg)
        
        elif msg_type in ["TYPING_START", "TYPING_STOP"]:
            recipient = message.get("recipient")
            if recipient:
                recipient_socket = self.get_client_socket(recipient)
                if recipient_socket:
                    status_msg = {"type": "typing", "sender": username, "status": msg_type == "TYPING_START"}
                    self.send_response(recipient_socket, status_msg)

    def remove_client(self, client_socket, username):
        with self.clients_lock:
            client_info = self.clients.pop(client_socket, None)
            if not client_info: return
            
            username = username or client_info.get('username')
            if not username: return
            
            for room_name in list(self.rooms.keys()):
                if username in self.rooms[room_name]:
                    self.rooms[room_name].discard(username)
        
        logging.info(f"Cliente {username} desconectado.")
        self.add_to_queue({'type': 'broadcast_system', 'message': f"{username} saiu do chat."})
        self.add_to_queue({'type': 'send_user_list_all'})
        try:
            client_socket.shutdown(socket.SHUT_RDWR)
            client_socket.close()
        except OSError:
            pass

    def add_to_queue(self, item): self.message_queue.put(item)
    
    def send_response(self, sock, data):
        try:
            sock.sendall((json.dumps(data) + '\n').encode('utf-8'))
        except (OSError, ConnectionError) as e:
            logging.warning(f"Falha ao enviar dados: {e}")

    def broadcast(self, message):
        with self.clients_lock:
            for sock in list(self.clients.keys()):
                self.send_response(sock, message)

    def broadcast_system(self, text): self.broadcast({"type": "SYSTEM", "message": text})

    def broadcast_to_room(self, room, message):
        with self.clients_lock:
            user_list = self.rooms.get(room, set())
            for sock, info in self.clients.items():
                if info.get('username') in user_list:
                    self.send_response(sock, message)

    def get_client_socket(self, username):
        with self.clients_lock:
            for sock, info in self.clients.items():
                if info['username'] == username:
                    return sock
        return None

    def send_private(self, message):
        recipient_socket = self.get_client_socket(message["recipient"])
        if recipient_socket:
            self.send_response(recipient_socket, message)
        else:
            self.save_offline_message(message)
    
    def send_user_list_all(self):
        with self.clients_lock:
            if not self.clients:
                online_users = set()
            else:
                online_users = {info['username'] for info in self.clients.values()}
        
        with sqlite3.connect(DB_FILE) as conn:
            all_users = [row[0] for row in conn.execute("SELECT username FROM users ORDER BY username")]
        
        user_list = [f"{u}:{'online' if u in online_users else 'offline'}" for u in all_users]
        self.broadcast({"type": "USERLIST", "users": user_list})
        
    def register_user(self, username, password):
        if not (3 <= len(username) <= 20 and 6 <= len(password) <= 50):
            return False, "Usuário (3-20) e senha (6-50) com tamanhos inválidos."
        try:
            hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed))
            return True, "Usuário registrado com sucesso!"
        except sqlite3.IntegrityError:
            return False, "Nome de usuário já existe."
        except Exception as e:
            logging.error(f"Erro no registro: {e}"); return False, "Erro interno do servidor."

    def authenticate_user(self, username, password):
        try:
            with sqlite3.connect(DB_FILE) as conn:
                res = conn.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()
                if res and bcrypt.checkpw(password.encode('utf-8'), res[0]):
                    conn.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE username = ?", (username,))
                    return True
            return False
        except Exception as e:
            logging.error(f"Erro na autenticação: {e}"); return False

    def save_message_history(self, room, sender, message):
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("INSERT INTO chat_history (room, sender, message, timestamp) VALUES (?, ?, ?, ?)",
                             (room or "Geral", sender, message, datetime.now().strftime('%H:%M:%S')))
        except Exception as e:
            logging.error(f"Erro salvando histórico: {e}")

    def save_offline_message(self, message):
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("INSERT INTO offline_messages (sender, recipient, message, timestamp) VALUES (?, ?, ?, ?)",
                             (message["sender"], message["recipient"], message["message"], message["timestamp"]))
        except Exception as e:
            logging.error(f"Erro ao salvar msg offline: {e}")

    def send_offline_messages(self, username):
        client_socket = self.get_client_socket(username)
        if not client_socket: return
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            messages = cursor.execute("SELECT id, sender, message, timestamp FROM offline_messages WHERE recipient=? AND delivered=FALSE", (username,)).fetchall()
            for msg_id, sender, message, timestamp in messages:
                self.send_response(client_socket, {"type": "PRIVATE", "sender": sender, "message": f"(Offline) {message}", "timestamp": timestamp})
                cursor.execute("UPDATE offline_messages SET delivered=TRUE WHERE id=?", (msg_id,))
            conn.commit()

    def cleanup_connections(self):
        while self.running:
            time.sleep(self.ping_interval)
            with self.clients_lock:
                if not self.clients: continue
                clients_to_remove = []
                for sock, info in self.clients.items():
                    if time.time() - info.get('last_ping', 0) > self.ping_timeout:
                        clients_to_remove.append((sock, info.get('username')))
            for sock, user in clients_to_remove:
                logging.warning(f"Timeout de ping para {user}. Desconectando.")
                self.remove_client(sock, user)
                
    def stop_server(self):
        self.running = False
        if self.message_worker.is_alive(): self.message_queue.put(None)
        with self.clients_lock:
            for sock in list(self.clients.keys()):
                try: sock.close()
                except: pass
        self.executor.shutdown(wait=False)
        self.server_socket.close()
        logging.info("Servidor parado.")

if __name__ == "__main__":
    server = ChatServer()
    try:
        server.start_server()
    except KeyboardInterrupt:
        logging.info("Servidor interrompido pelo usuário.")
    finally:
        server.stop_server()