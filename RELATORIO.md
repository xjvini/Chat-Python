# Relatório Técnico
---

### **Aluno:** José Vinícius  
### **Disciplina:** Redes de Computadores  
### **Curso:** Engenharia da Computação - UABJ
### **Professor:** Ygor Amaral

---

# Relatório Técnico do Projeto: Chat Cliente-Servidor

### **Curso:** Bacharelado em Engenharia da Computação
### **Disciplina:** Redes de Computadores
### **Professor:** Ygor Amaral

---

## 1. Arquitetura do Sistema

O sistema foi projetado seguindo o modelo cliente-servidor, onde um servidor central gerencia a comunicação e o estado, e múltiplos clientes desktop se conectam a ele para interagir.

### 1.1. Arquitetura do Servidor

O servidor foi construído em Python como uma aplicação multithread, projetado para ser robusto e escalável no gerenciamento de múltiplas conexões simultâneas. Sua arquitetura é modular, dividida da seguinte forma:

* **Módulo Principal (`ChatServer`)**: Classe que orquestra toda a operação do servidor. É responsável por iniciar o socket, gerenciar o ciclo de vida do servidor e coordenar os demais módulos.
* **Núcleo de Rede (`socket`, `ThreadPoolExecutor`)**: Utiliza a biblioteca `socket` para comunicação TCP/IP. Ao receber uma nova conexão, a tarefa de gerenciá-la é delegada a um pool de threads (`ThreadPoolExecutor`), o que permite ao servidor aceitar novos clientes sem bloquear.
* **Módulo de Processamento de Mensagens (`queue.Queue`)**: Para evitar gargalos e condições de corrida, todas as mensagens recebidas dos clientes são colocadas em uma fila central. Uma única thread trabalhadora (`MessageQueueThread`) processa essas mensagens de forma sequencial, garantindo que a lógica de negócios seja executada de maneira ordenada e separada das operações de rede (I/O).
* **Módulo de Autenticação**: Composto pelas funções `register_user` e `authenticate_user`. Este módulo interage com o banco de dados para validar credenciais ou registrar novos usuários. A segurança é reforçada pelo uso da biblioteca `bcrypt` para o hashing de senhas.
* **Módulo de Persistência (`sqlite3`)**: Responsável por toda a interação com o banco de dados `chat1.db`. Ele gerencia três tabelas principais:
    1.  `users`: Armazena os dados de login dos usuários.
    2.  `chat_history`: Guarda o histórico de mensagens das salas públicas.
    3.  `offline_messages`: Armazena mensagens privadas destinadas a usuários que não estão online.
* **Módulo de Gerenciamento de Conexões**: Inclui uma thread de limpeza (`CleanupThread`) que implementa um mecanismo de "ping-pong" para verificar a atividade dos clientes. Conexões inativas por um determinado período são finalizadas para liberar recursos e tratar falhas.

### 1.2. Arquitetura do Cliente

O cliente é uma aplicação desktop com interface gráfica (GUI) desenvolvida em Python com `tkinter`. Sua arquitetura também é multithread para garantir que a interface do usuário permaneça sempre responsiva, mesmo durante operações de rede que podem demorar.

* **Módulo Principal (`ChatClient`)**: Classe que gerencia toda a lógica do cliente, o estado da conexão e a interação entre a GUI e os módulos de rede.
* **Módulo de Interface Gráfica (GUI com `tkinter`)**: Responsável por construir e gerenciar todos os elementos visuais da aplicação, como a tela de login, a lista de contatos e a janela de chat.
* **Módulos de Rede (`threading`)**: Para evitar o congelamento da GUI, as operações de rede são executadas em threads separadas:
    * `AuthThread`: Gerencia as requisições de login e registro.
    * `ReceiverThread`: Fica em um loop contínuo, escutando por mensagens recebidas do servidor.
    * `PingThread`: Envia pings periódicos ao servidor para manter a conexão ativa.
* **Ponte de Comunicação GUI-Rede (`ui_queue`)**: Para atualizar a interface gráfica a partir das threads de rede de forma segura, o cliente utiliza uma fila (`ui_queue`). A thread de rede adiciona uma "tarefa" à fila (ex: "exibir nova mensagem"), e o loop principal da GUI a executa, evitando erros de concorrência.

---

## 2. Protocolo de Comunicação

Para a comunicação entre cliente e servidor, foi desenvolvido um protocolo de aplicação simples sobre TCP. [cite_start]As mensagens são objetos JSON, codificados em UTF-8 e delimitados por um caractere de nova linha (`\n`) para indicar o fim de um pacote.

A seguir, a estrutura detalhada de cada tipo de mensagem:

| Tipo da Mensagem          | Direção | Descrição                                                          | Campos Principais                               |
| :------------------------ | :------ | :----------------------------------------------------------------- | :---------------------------------------------- |
| `LOGIN` / `REGISTER`      | C -> S  | Autentica ou registra um novo usuário.                             | `action`, `username`, `password`                |
| `AUTH_RESPONSE`           | S -> C  | Resposta do servidor à tentativa de login/registro.                | `status` ("SUCCESS" ou "ERROR"), `message`      |
| `ROOM_MESSAGE`            | C -> S  | Envia uma mensagem para uma sala pública.                          | `type`, `room`, `message`                       |
| `PRIVATE`                 | C -> S  | Envia uma mensagem privada para um destinatário.                   | `type`, `recipient`, `message`                  |
| `PUBLIC`/`PRIVATE` (Broadcast) | S -> C  | Mensagem do servidor para o cliente, com dados adicionais.         | `type`, `sender`, `message`, `timestamp`        |
| `USERLIST`                | C -> S  | Solicita a lista de todos os usuários.                             | `type`                                          |
| `USERLIST` (Broadcast)    | S -> C  | Envio da lista de usuários com seu status.                         | `type`, `users` (lista de "user:status")        |
| `TYPING_START`/`TYPING_STOP` | C -> S  | Cliente informa que começou/parou de digitar para um destinatário. | `type`, `recipient`                             |
| `typing` (Broadcast)      | S -> C  | Servidor retransmite o status de "digitando" para o destino.       | `type`, `sender`, `status` (booleano)           |
| `PING`                    | C -> S  | Verificação de atividade enviada pelo cliente.                     | `type`                                          |
| `PONG`                    | S -> C  | Resposta do servidor à verificação de atividade.                   | `type`                                          |
| `SYSTEM`                  | S -> C  | Mensagem global do servidor (ex: "usuário entrou").                | `type`, `message`                               |

---

## 3. Implementação dos Requisitos Funcionais

Todos os requisitos funcionais foram atendidos conforme a especificação do projeto.

* **Registro e Autenticação**: O fluxo começa na GUI do cliente, que envia as credenciais para o servidor. O servidor valida os dados contra o banco de dados SQLite, usando `bcrypt` para segurança de senhas, e retorna uma resposta de sucesso ou falha.
* **Lista de Contatos**: Após o login, o cliente solicita e recebe a lista de todos os usuários cadastrados. A lista é exibida graficamente, e o status (online/offline) é diferenciado por cores para melhor usabilidade.
* **Troca de Mensagens**: O cliente envia mensagens privadas ou públicas em formato JSON. O servidor atua como um roteador: ele identifica o tipo de mensagem, adiciona informações relevantes (remetente, timestamp) e a encaminha para o(s) destinatário(s) correto(s) se estiverem online.
* **Mensagens Offline**: Se uma mensagem privada é enviada a um usuário offline, o servidor a armazena na tabela `offline_messages`. Assim que o usuário se conecta, o servidor envia todas as mensagens pendentes e as marca como entregues.
* **Indicadores**: O status "online/offline" é derivado da lista de contatos. O indicador "digitando..." é implementado com eventos `TYPING_START` e `TYPING_STOP` trocados entre os clientes, com o servidor atuando como intermediário. Um temporizador de 2 segundos no cliente encerra o status de digitação automaticamente, conforme sugerido.

---

## 4. Gerenciamento de Conexões e Concorrência

O gerenciamento de múltiplas conexões e a prevenção de conflitos de concorrência foram pontos centrais no desenvolvimento.

* **Atendimento a Múltiplos Clientes**: O servidor utiliza um `ThreadPoolExecutor` para gerenciar a concorrência. A thread principal do servidor fica em um loop, aceitando novas conexões TCP. Cada nova conexão é entregue a uma thread do pool, que executa a lógica de comunicação para aquele cliente. Isso isola os clientes uns dos outros e permite que o servidor atenda a um grande número de usuários simultaneamente.
* **Tratamento de Falhas de Conexão**: A robustez do sistema é garantida por dois mecanismos:
    1.  **Mecanismo Reativo**: Blocos `try...except` em torno de todas as operações de `socket.send()` e `socket.recv()` capturam exceções (`ConnectionError`, `OSError`), permitindo que o sistema remova o cliente desconectado de forma limpa.
    2.  **Mecanismo Proativo**: Um sistema de "Ping/Pong" e um timeout no servidor detectam clientes que ficaram silenciosos (ex: por perda de rede) e os removem da lista de clientes ativos.
* **Comunicação Cliente-Servidor**: O cliente estabelece uma conexão TCP persistente. [cite_start]Para permitir o envio e recebimento simultâneo de mensagens sem travar a interface, o cliente é multithread: uma thread escuta o servidor enquanto a thread principal da GUI lida com as entradas do usuário e envia mensagens.

---

## 5. Desafios e Aprendizados

O desenvolvimento do projeto proporcionou uma experiência prática valiosa sobre os conceitos teóricos da disciplina.

### Principais Desafios

1.  **Concorrência na GUI**: O desafio mais significativo foi integrar as operações de rede (que são bloqueantes) com a interface gráfica `tkinter` (que opera em uma única thread). A solução foi a implementação do padrão de "fila de mensagens" (`ui_queue`), que permitiu a comunicação segura entre as threads de rede e a thread da GUI.
2.  **Framing de Mensagens**: Garantir que o receptor lesse mensagens JSON completas, já que o TCP é um protocolo de stream, foi um desafio inicial. A solução foi adotar um delimitador (`\n`) e um buffer de recebimento para montar os pacotes antes de processá-los.
3.  **Inclusão do sistema multiconexão: Houve o surgimento de bugs que ocasionaram a desconexão de usuários sempre que 2+ tentavam conexão com o servidor. A solução foi otimizar a forma que o servidor compreenderia a solicitação dos clientes e como o cliente se comportaria durante o atraso de resposta do servidor.

### Principais Aprendizados

1.  **Redes de Computadores**: O projeto solidificou o entendimento prático sobre o ciclo de vida dos sockets TCP, a importância de um protocolo de aplicação bem definido e a diferença entre o design de cliente e de servidor.
2.  **Concorrência**: Ficou clara a necessidade de mecanismos de sincronização (como filas e locks) em aplicações multithread para evitar condições de corrida e garantir a integridade dos dados.
3.  **Persistência e Segurança**: A implementação reforçou a importância de usar bancos de dados para persistência e a necessidade crítica de nunca armazenar senhas em texto plano, aplicando técnicas de hashing como o `bcrypt`.

---

## 6. Limitações e Bugs Conhecidos

Apesar de funcional, o sistema atual possui limitações que poderiam ser endereçadas em versões futuras.

* **Comunicação Não Criptografada**: A maior limitação de segurança é que toda a comunicação, incluindo senhas durante o login, ocorre em texto plano. Em um ambiente real, seria indispensável implementar criptografia TLS/SSL para proteger os dados em trânsito.
* **Falta de Salas de Chat Múltiplas**: O sistema suporta apenas uma sala pública ("Geral") e chats privados. Não há funcionalidade para que os usuários criem, descubram ou participem de outras salas temáticas.
* **Histórico de Chat Não Carregado**: Ao iniciar uma conversa, o cliente não carrega o histórico de mensagens anteriores do banco de dados do servidor; ele apenas exibe as novas mensagens trocadas na sessão atual.
* **Escalabilidade do Servidor**: Embora o `ThreadPoolExecutor` e a fila de mensagens funcionem bem, um servidor com um número massivo de usuários poderia encontrar gargalos. A centralização do processamento de mensagens em uma única thread e o uso de `SQLite` (que tem limitações de escrita concorrente) poderiam ser pontos de estrangulamento.
