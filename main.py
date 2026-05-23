from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, join_room
import os
import hashlib
import sqlite3
from datetime import datetime, timedelta
import secrets

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_urlsafe(32))
socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=60, ping_interval=25)

DB_PATH = '/app/data/shadow_chat.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room TEXT NOT NULL,
        username TEXT NOT NULL,
        text TEXT NOT NULL,
        timestamp TIMESTAMP,
        read_status TEXT DEFAULT 'sent'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        expires_at TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_rooms (
        username TEXT NOT NULL,
        room TEXT NOT NULL,
        last_read TIMESTAMP,
        PRIMARY KEY (username, room)
    )''')
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes, viewport-fit=cover">
    <title>Shadow Chat — защищенный чат</title>
    <script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            background: #0f0f14;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .container {
            background: #1e1f2c;
            border-radius: 40px;
            width: 100%;
            max-width: 600px;
            height: 90%;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
        }
        
        .header {
            background: #1e1f2c;
            padding: 20px 16px;
            border-bottom: 1px solid #2d2f3e;
            text-align: center;
        }
        
        .header h1 {
            color: #f1f5f9;
            font-size: 1.5rem;
            font-weight: 600;
        }
        
        .auth-panel {
            display: flex;
            flex-direction: column;
            gap: 12px;
            padding: 24px 20px;
            background: #0f0f14;
            border-bottom: 1px solid #2d2f3e;
        }
        
        .auth-panel input {
            background: #1e1f2c;
            border: 1px solid #2d2f3e;
            border-radius: 40px;
            padding: 12px 16px;
            color: white;
            outline: none;
            width: 100%;
            font-size: 16px;
            transition: border-color 0.2s;
        }
        
        .auth-panel input:focus {
            border-color: #6366f1;
        }
        
        .buttons {
            display: flex;
            gap: 12px;
            margin-top: 8px;
        }
        
        .buttons button {
            flex: 1;
            background: #6366f1;
            border: none;
            border-radius: 40px;
            padding: 12px;
            color: white;
            font-weight: bold;
            cursor: pointer;
            font-size: 16px;
            transition: transform 0.1s, background 0.2s;
        }
        
        .buttons button:hover {
            background: #4f52e0;
        }
        
        .buttons button:active {
            transform: scale(0.98);
        }
        
        .room-panel {
            display: flex;
            flex-direction: column;
            gap: 8px;
            padding: 16px;
            background: #0f0f14;
            border-bottom: 1px solid #2d2f3e;
            display: none;
        }
        
        .room-panel .row {
            display: flex;
            gap: 8px;
        }
        
        .room-panel input {
            flex: 1;
            background: #1e1f2c;
            border: 1px solid #2d2f3e;
            border-radius: 40px;
            padding: 10px 16px;
            color: white;
            outline: none;
            font-size: 14px;
        }
        
        .room-panel input:focus {
            border-color: #6366f1;
        }
        
        .room-panel button {
            background: #6366f1;
            border: none;
            border-radius: 40px;
            padding: 0 20px;
            color: white;
            font-weight: bold;
            cursor: pointer;
            transition: background 0.2s;
        }
        
        .room-panel button:hover {
            background: #4f52e0;
        }
        
        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        .messages::-webkit-scrollbar {
            width: 6px;
        }
        
        .messages::-webkit-scrollbar-track {
            background: #2d2f3e;
            border-radius: 10px;
        }
        
        .messages::-webkit-scrollbar-thumb {
            background: #6366f1;
            border-radius: 10px;
        }
        
        .message {
            display: flex;
            gap: 10px;
            width: 100%;
            animation: fadeIn 0.3s ease-in;
        }
        
        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .my-message {
            justify-content: flex-end;
        }
        
        .avatar {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            background: #2d2f3e;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            color: #e2e8f0;
            flex-shrink: 0;
        }
        
        .my-message .avatar {
            display: none;
        }
        
        .bubble {
            max-width: 70%;
            padding: 10px 14px;
            border-radius: 20px;
            font-size: 14px;
            line-height: 1.4;
            word-break: break-word;
        }
        
        .my-message .bubble {
            background: #6366f1;
            color: white;
            border-bottom-right-radius: 4px;
        }
        
        .other-message .bubble {
            background: #2d2f3e;
            color: #e2e8f0;
            border-bottom-left-radius: 4px;
        }
        
        .message-info {
            font-size: 10px;
            color: #7c8ba0;
            margin-top: 4px;
            display: flex;
            gap: 6px;
            justify-content: flex-end;
        }
        
        .input-area {
            display: flex;
            gap: 8px;
            padding: 16px;
            border-top: 1px solid #2d2f3e;
            background: #0f0f14;
        }
        
        .input-area input {
            flex: 1;
            background: #1e1f2c;
            border: 1px solid #2d2f3e;
            border-radius: 40px;
            padding: 12px;
            color: white;
            outline: none;
            font-size: 14px;
        }
        
        .input-area input:focus {
            border-color: #6366f1;
        }
        
        .input-area button {
            background: #6366f1;
            border: none;
            border-radius: 40px;
            padding: 0 20px;
            color: white;
            font-weight: bold;
            cursor: pointer;
            font-size: 18px;
            transition: transform 0.1s;
        }
        
        .input-area button:hover {
            background: #4f52e0;
        }
        
        .input-area button:active {
            transform: scale(0.95);
        }
        
        .status {
            font-size: 12px;
            color: #7c8ba0;
            text-align: center;
            padding: 12px;
            background: #0f0f14;
            border-top: 1px solid #2d2f3e;
        }
        
        .username {
            font-weight: bold;
            margin-bottom: 4px;
            font-size: 12px;
            color: #a5b4fc;
        }
        
        .system-message .bubble {
            background: #2d2f3e;
            color: #7c8ba0;
            font-style: italic;
            text-align: center;
            font-size: 12px;
        }
        
        @media (max-width: 600px) {
            body {
                padding: 0;
            }
            
            .container {
                height: 100%;
                max-width: 100%;
                border-radius: 0;
            }
            
            .bubble {
                max-width: 85%;
            }
            
            .room-panel .row {
                gap: 6px;
            }
            
            .room-panel input {
                padding: 8px 12px;
            }
        }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>💬 Shadow Chat</h1>
    </div>
    <div class="auth-panel" id="authPanel">
        <input type="text" id="username" placeholder="Логин" autocomplete="username">
        <input type="password" id="password" placeholder="Пароль" autocomplete="current-password">
        <div class="buttons">
            <button id="loginBtn">Войти</button>
            <button id="registerBtn">Регистрация</button>
        </div>
    </div>
    <div class="room-panel" id="roomPanel">
        <div class="row">
            <input type="text" id="roomCode" placeholder="Код комнаты (например, work, friends, gaming)" autocomplete="off">
            <button id="joinBtn">Войти</button>
        </div>
    </div>
    <div class="messages" id="messages"></div>
    <div class="input-area" id="inputArea" style="display: none;">
        <input type="text" id="messageInput" placeholder="Напишите сообщение..." autocomplete="off">
        <button id="sendBtn">➤</button>
    </div>
    <div class="status" id="status">✨ Введите логин и пароль</div>
</div>

<script>
    let socket = null;
    let currentRoom = null;
    let currentUser = null;
    
    const authPanel = document.getElementById('authPanel');
    const roomPanel = document.getElementById('roomPanel');
    const inputArea = document.getElementById('inputArea');
    const messagesDiv = document.getElementById('messages');
    const statusSpan = document.getElementById('status');
    const roomCodeInput = document.getElementById('roomCode');
    const joinBtn = document.getElementById('joinBtn');
    const messageInput = document.getElementById('messageInput');
    const sendBtn = document.getElementById('sendBtn');
    
    const savedToken = localStorage.getItem('shadow_token');
    const savedUsername = localStorage.getItem('shadow_username');
    
    function formatTime(isoString) {
        if (!isoString) return '';
        try {
            const date = new Date(isoString);
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch(e) {
            return '';
        }
    }
    
    function addMessage(text, isMy, username = '', readStatus = 'sent', timestamp = null) {
        const div = document.createElement('div');
        const isSystem = username === 'system';
        div.className = `message ${isMy ? 'my-message' : 'other-message'} ${isSystem ? 'system-message' : ''}`;
        
        if (!isMy && !isSystem) {
            const avatar = document.createElement('div');
            avatar.className = 'avatar';
            avatar.innerText = username.charAt(0).toUpperCase() || '?';
            div.appendChild(avatar);
        }
        
        const bubbleWrapper = document.createElement('div');
        bubbleWrapper.style.maxWidth = isSystem ? '100%' : '70%';
        
        const bubble = document.createElement('div');
        bubble.className = 'bubble';
        
        if (!isMy && username && username !== 'system') {
            const nameSpan = document.createElement('div');
            nameSpan.className = 'username';
            nameSpan.innerText = escapeHtml(username);
            bubble.appendChild(nameSpan);
        }
        
        const textSpan = document.createElement('span');
        textSpan.innerText = text;
        bubble.appendChild(textSpan);
        
        const info = document.createElement('div');
        info.className = 'message-info';
        const timeSpan = document.createElement('span');
        timeSpan.innerText = formatTime(timestamp);
        info.appendChild(timeSpan);
        
        if (isMy && !isSystem) {
            const statusSpanEl = document.createElement('span');
            statusSpanEl.innerText = readStatus === 'read' ? '✓✓' : '✓';
            info.appendChild(statusSpanEl);
        }
        
        bubble.appendChild(info);
        bubbleWrapper.appendChild(bubble);
        div.appendChild(bubbleWrapper);
        messagesDiv.appendChild(div);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
    
    function escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
    
    function loadHistory(history) {
        messagesDiv.innerHTML = '';
        if (!history || history.length === 0) return;
        
        for (let msg of history) {
            const isMy = (msg.username === currentUser);
            addMessage(msg.text, isMy, msg.username, msg.read_status, msg.timestamp);
        }
    }
    
    async function apiRequest(endpoint, data) {
        try {
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            return await res.json();
        } catch(e) {
            console.error('API request failed:', e);
            return { success: false, error: 'Сетевая ошибка' };
        }
    }
    
    async function autoLogin() {
        if (!savedToken || !savedUsername) return false;
        
        const result = await apiRequest('/auto_login', { token: savedToken });
        if (result.success) {
            currentUser = savedUsername;
            authPanel.style.display = 'none';
            roomPanel.style.display = 'flex';
            statusSpan.innerText = `✅ С возвращением, ${escapeHtml(currentUser)}! Введите код комнаты`;
            return true;
        } else {
            localStorage.removeItem('shadow_token');
            localStorage.removeItem('shadow_username');
            return false;
        }
    }
    
    document.getElementById('loginBtn').onclick = async () => {
        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value.trim();
        
        if (!username || !password) {
            statusSpan.innerText = '❌ Введите логин и пароль';
            return;
        }
        
        const result = await apiRequest('/login', { username, password });
        if (result.success) {
            currentUser = username;
            localStorage.setItem('shadow_token', result.token);
            localStorage.setItem('shadow_username', username);
            authPanel.style.display = 'none';
            roomPanel.style.display = 'flex';
            statusSpan.innerText = `✅ Добро пожаловать, ${escapeHtml(username)}! Введите код комнаты`;
        } else {
            statusSpan.innerText = `❌ ${result.error}`;
        }
    };
    
    document.getElementById('registerBtn').onclick = async () => {
        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value.trim();
        
        if (!username || !password) {
            statusSpan.innerText = '❌ Введите логин и пароль';
            return;
        }
        
        if (password.length < 4) {
            statusSpan.innerText = '❌ Пароль должен быть не менее 4 символов';
            return;
        }
        
        const result = await apiRequest('/register', { username, password });
        if (result.success) {
            statusSpan.innerText = '✅ Регистрация успешна! Теперь войдите';
            document.getElementById('username').value = '';
            document.getElementById('password').value = '';
        } else {
            statusSpan.innerText = `❌ ${result.error}`;
        }
    };
    
    function connectToRoom(room) {
        if (socket) {
            socket.disconnect();
        }
        
        socket = io({
            reconnection: true,
            reconnectionAttempts: Infinity,
            reconnectionDelay: 1000,
            timeout: 20000
        });
        
        socket.on('connect', () => {
            socket.emit('join', { room, username: currentUser });
            currentRoom = room;
            statusSpan.innerText = `✅ Комната: ${escapeHtml(room)}. Можете писать сообщения`;
            inputArea.style.display = 'flex';
            messageInput.focus();
        });
        
        socket.on('history', (history) => {
            loadHistory(history);
        });
        
        socket.on('new_message', (data) => {
            const isMy = (data.username === currentUser);
            addMessage(data.text, isMy, data.username, data.read_status, data.timestamp);
            
            if (!isMy && currentRoom === data.room && data.username !== 'system') {
                socket.emit('mark_read', { room: data.room });
            }
        });
        
        socket.on('read_receipt', ({ room }) => {
            if (room === currentRoom) {
                document.querySelectorAll('.my-message').forEach(msgDiv => {
                    const info = msgDiv.querySelector('.message-info');
                    if (info) {
                        const statusSpanEl = info.querySelector('span:last-child');
                        if (statusSpanEl && statusSpanEl.innerText === '✓') {
                            statusSpanEl.innerText = '✓✓';
                        }
                    }
                });
            }
        });
        
        socket.on('disconnect', () => {
            statusSpan.innerText = '⚠️ Потеря соединения. Переподключение...';
            inputArea.style.display = 'none';
        });
        
        socket.on('connect_error', (error) => {
            console.error('Connection error:', error);
            statusSpan.innerText = '❌ Ошибка подключения к серверу';
        });
        
        socket.on('reconnect', () => {
            statusSpan.innerText = `✅ Переподключено! Комната: ${escapeHtml(currentRoom)}`;
            if (currentRoom) {
                socket.emit('join', { room: currentRoom, username: currentUser });
            }
        });
    }
    
    joinBtn.onclick = () => {
        const room = roomCodeInput.value.trim();
        if (!room) {
            statusSpan.innerText = '❌ Введите код комнаты';
            return;
        }
        
        if (room.length > 50) {
            statusSpan.innerText = '❌ Название комнаты слишком длинное';
            return;
        }
        
        connectToRoom(room);
    };
    
    sendBtn.onclick = () => {
        const text = messageInput.value.trim();
        if (text && socket && currentRoom) {
            if (text.length > 500) {
                statusSpan.innerText = '❌ Сообщение слишком длинное';
                return;
            }
            socket.emit('message', { room: currentRoom, text, username: currentUser });
            messageInput.value = '';
            messageInput.focus();
        }
    };
    
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            sendBtn.click();
        }
    });
    
    roomCodeInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            joinBtn.click();
        }
    });
    
    autoLogin();
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return {'success': False, 'error': 'Введите логин и пароль'}
    
    if len(username) < 3:
        return {'success': False, 'error': 'Логин должен быть не менее 3 символов'}
    
    if len(password) < 4:
        return {'success': False, 'error': 'Пароль должен быть не менее 4 символов'}
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT username FROM users WHERE username = ?', (username,))
    if c.fetchone():
        conn.close()
        return {'success': False, 'error': 'Пользователь уже существует'}
    
    password_hash = hash_password(password)
    c.execute('INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)',
              (username, password_hash, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {'success': True}

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return {'success': False, 'error': 'Введите логин и пароль'}
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT password_hash FROM users WHERE username = ?', (username,))
    row = c.fetchone()
    conn.close()
    
    if not row or row[0] != hash_password(password):
        return {'success': False, 'error': 'Неверный логин или пароль'}
    
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=365)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO sessions (token, username, expires_at) VALUES (?, ?, ?)',
              (token, username, expires_at.isoformat()))
    conn.commit()
    conn.close()
    
    return {'success': True, 'token': token}

@app.route('/auto_login', methods=['POST'])
def auto_login():
    data = request.json
    token = data.get('token')
    
    if not token:
        return {'success': False, 'error': 'Нет токена'}
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT username, expires_at FROM sessions WHERE token = ?', (token,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return {'success': False, 'error': 'Токен не найден'}
    
    username, expires_at = row
    if datetime.now() > datetime.fromisoformat(expires_at):
        return {'success': False, 'error': 'Токен истёк'}
    
    return {'success': True, 'username': username}

@socketio.on('join')
def handle_join(data):
    room = data['room']
    username = data['username']
    join_room(room)
    
    # Отправляем историю сообщений
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT username, text, timestamp, read_status FROM messages WHERE room = ? ORDER BY timestamp ASC', (room,))
    rows = c.fetchall()
    history = [{'username': r[0], 'text': r[1], 'timestamp': r[2], 'read_status': r[3]} for r in rows]
    conn.close()
    emit('history', history)
    
    # Обновляем статус прочтения
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE messages SET read_status = "read" WHERE room = ? AND username != ? AND read_status = "sent"', 
              (room, username))
    updated = c.rowcount
    conn.commit()
    conn.close()
    
    if updated > 0:
        emit('read_receipt', {'room': room}, to=room)
    
    # Отправляем системное сообщение
    emit('new_message', {
        'username': 'system',
        'text': f'{username} присоединился к чату',
        'read_status': 'read',
        'timestamp': datetime.now().isoformat()
    }, to=room)

@socketio.on('message')
def handle_message(data):
    room = data['room']
    text = data['text'].strip()
    username = data.get('username')
    
    if not username or not text:
        return
    
    if len(text) > 500:
        return
    
    timestamp = datetime.now().isoformat()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO messages (room, username, text, timestamp, read_status) VALUES (?, ?, ?, ?, ?)',
              (room, username, text, timestamp, 'sent'))
    conn.commit()
    conn.close()
    
    emit('new_message', {
        'username': username,
        'text': text,
        'read_status': 'sent',
        'timestamp': timestamp
    }, to=room)

@socketio.on('mark_read')
def handle_mark_read(data):
    room = data['room']
    username = data.get('username')
    
    if not username:
        return
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE messages SET read_status = "read" WHERE room = ? AND username != ? AND read_status = "sent"', 
              (room, username))
    updated = c.rowcount
    conn.commit()
    conn.close()
    
    if updated > 0:
        emit('read_receipt', {'room': room}, to=room)

if __name__ == '__main__':
    # Создаем директорию для БД
    os.makedirs('/app/data', exist_ok=True)
    init_db()
    port = int(os.environ.get('PORT', 8080))
    # Убираем allow_unsafe_werkzeug - он не нужен и вызывает ошибку
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
@socketio.on('join')
def handle_join(data):
    room = data['room']
    username = data['username']
    join_room(room)
    
    # Отправляем историю сообщений
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT username, text, timestamp, read_status FROM messages WHERE room = ? ORDER BY timestamp ASC', (room,))
    rows = c.fetchall()
    history = [{'username': r[0], 'text': r[1], 'timestamp': r[2], 'read_status': r[3]} for r in rows]
    conn.close()
    emit('history', history)
    
    # Обновляем статус прочтения
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE messages SET read_status = "read" WHERE room = ? AND username != ? AND read_status = "sent"', 
              (room, username))
    updated = c.rowcount
    conn.commit()
    conn.close()
    
    if updated > 0:
        emit('read_receipt', {'room': room}, to=room)
    
    # Отправляем системное сообщение
    emit('new_message', {
        'username': 'system',
        'text': f'{username} присоединился к чату',
        'read_status': 'read',
        'timestamp': datetime.now().isoformat()
    }, to=room)

@socketio.on('message')
def handle_message(data):
    room = data['room']
    text = data['text'].strip()
    username = data.get('username')
    
    if not username or not text:
        return
    
    if len(text) > 500:
        return
    
    timestamp = datetime.now().isoformat()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO messages (room, username, text, timestamp, read_status) VALUES (?, ?, ?, ?, ?)',
              (room, username, text, timestamp, 'sent'))
    conn.commit()
    conn.close()
    
    emit('new_message', {
        'username': username,
        'text': text,
        'read_status': 'sent',
        'timestamp': timestamp
    }, to=room)

@socketio.on('mark_read')
def handle_mark_read(data):
    room = data['room']
    username = data.get('username')
    
    if not username:
        return
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE messages SET read_status = "read" WHERE room = ? AND username != ? AND read_status = "sent"', 
              (room, username))
    updated = c.rowcount
    conn.commit()
    conn.close()
    
    if updated > 0:
        emit('read_receipt', {'room': room}, to=room)

if __name__ == '__main__':
    # Создаем директорию для БД
    os.makedirs('/app/data', exist_ok=True)
    init_db()
    port = int(os.environ.get('PORT', 8080))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
