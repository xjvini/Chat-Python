# Chat-Servidor

Este projeto implementa um sistema de chat cliente-servidor desenvolvido em Python. A aplicação utiliza comunicação via sockets TCP/IP, interface gráfica desktop com Tkinter, e banco de dados SQLite com persistência de mensagens e usuários.

O servidor gerencia múltiplas conexões simultâneas por meio de threads, oferecendo autenticação segura com bcrypt, envio de mensagens públicas, privadas e em grupos (salas). Além de armazenamento e entrega de mensagens offline, recursos de presença (lista de usuários online/offline), indicador em tempo real de digitação e reconexão automática em caso de falhas de conexão.


## Arquitetura Geral

### 1. Servidor

- Python 3
- Sockets TCP
- Threads
- Banco SQLite
- Segurança com bcrypt

### 2. Cliente

- Python 3
- Interface Tkinter
- Threads
- Reconexão automática
---  

## Funcionalidades Implementadas

- Registro com verificação de usuário único.
- Login seguro com senhas criptografadas.
- Lista de contatos com status online/offline.
- Envio de mensagens públicas, privadas e por sala.
- Persistência de mensagens offline.
- Indicador de digitação em tempo real.
- Reconexão automática em caso de falha de rede.
- Controle de concorrência com threads.
- Persistência completa no banco SQLite.
---

## Tratamento de Conexões e Concorrência

- Cada cliente opera em thread dedicada.
- Acesso seguro ao dicionário de clientes com `threading.Lock()`.
- Reconexão automática após falha.
- Tratamento de exceções de desconexões.
---

## Requisitos

- Python 3.x
- Biblioteca `bcrypt`


1️⃣ Instale o pacote `bcrypt` com:
```bash
pip install bcrypt
```
---


## Execução

1️⃣ Inicie o servidor:

```bash
python servidor.py
```

2️⃣ Inicie o cliente:
```
python cliente.py
```



---

## 4️⃣ **Arquivo: `Relatorio_Tecnico.md`**

```markdown
# Relatório Técnico — Projeto Chat Cliente-Servidor

Aluno: José Vinícius Ferreira de Freitas Santos  
Disciplina: Redes de Computadores  
Curso: Engenharia da Computação
Professor: Ygor Amaral

---

## 1. Arquitetura Geral

Sistema cliente-servidor TCP/IP multithreaded com persistência em SQLite.

### Servidor

- Python 3
- Sockets TCP
- Threads
- Banco SQLite
- Segurança com bcrypt

### Cliente

- Python 3
- Interface Tkinter
- Threads
- Reconexão automática

---

## 2. Protocolo de Comunicação

- Formato: JSON
- Transporte: TCP com terminação `\\n`

### Tipos de mensagens

| Tipo | Descrição |
|------|-----------|
| REGISTER | Cadastro de usuários |
| LOGIN | Autenticação |
| PUBLIC | Mensagens públicas |
| PRIVATE | Mensagens privadas |
| ROOM_MESSAGE | Mensagens em salas |
| ROOM_ACTION | Entrar em salas |
| USERLIST | Lista de contatos |
| TYPING_START / TYPING_STOP | Indicador de digitação |
| PING / PONG | Manutenção de conexão |

---

## 3. Funcionalidades Implementadas

- Registro com verificação de usuário único.
- Login seguro com senhas criptografadas.
- Lista de contatos com status online/offline.
- Envio de mensagens públicas, privadas e por sala.
- Persistência de mensagens offline.
- Indicador de digitação em tempo real.
- Reconexão automática em caso de falha de rede.
- Controle de concorrência com threads.
- Persistência completa no banco SQLite.

---

## 4. Tratamento de Conexões e Concorrência

- Cada cliente opera em thread dedicada.
- Acesso seguro ao dicionário de clientes com `threading.Lock()`.
- Reconexão automática após falha.
- Tratamento de exceções de desconexões.

---

## 5. Limitações

- Reconexão automática não restaura a sala onde o cliente estava previamente.
- Interface gráfica simplificada para fins acadêmicos.

---

## 6. Conclusão

O projeto cumpre integralmente os requisitos propostos na disciplina, incluindo sockets TCP, threads, persistência, tratamento de offline, GUI e reconexão automática.


