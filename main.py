from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
import hashlib
import sqlite3
from datetime import datetime, timedelta
import secrets

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'
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
        timestamp TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        expires_at TIMESTAMP
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <title>Shadow Chat</title>
    <script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{background:#0f0f14;font-family:system-ui;height:100vh;display:flex;justify-content:center;align-items:center}
        .auth-panel{background:#1e1f2c;border-radius:40px;padding:32px;width:350px}
        .auth-panel input{width:100%;background:#0f0f14;border:1px solid #2d2f3e;border-radius:40px;padding:12px 16px;color:white;margin-bottom:12px}
        .auth-panel button{background:#6366f1;border:none;border-radius:40px;padding:12px;color:white;font-weight:bold;cursor:pointer;width:100%}
        .auth-panel .buttons{display:flex;gap:12px;margin-top:12px}
        .auth-panel .buttons button{flex:1}
        .chat-container{display:flex;width:100vw;height:100vh;background:#1e1f2c}
        .sidebar{width:280px;background:#0f0f14;border-right:1px solid #2d2f3e;display:flex;flex-direction:column}
        .sidebar-header{padding:16px;border-bottom:1px solid #2d2f3e;color:white;font-weight:bold}
        .rooms-list{flex:1;overflow-y:auto}
        .room-item{padding:12px 16px;border-bottom:1px solid #2d2f3e;cursor:pointer;color:#e2e8f0}
        .room-item.active{background:#6366f1}
        .room-name{font-weight:bold}
        .chat-area{flex:1;display:flex;flex-direction:column}
        .chat-header{padding:16px;border-bottom:1px solid #2d2f3e;display:flex;justify-content:space-between}
        .chat-header h3{color:white}
        .leave-btn{background:#2d2f3e;border:none;border-radius:40px;padding:6px 16px;color:white;cursor:pointer}
        .messages{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px}
        .message{display:flex;max-width:80%}
        .my-message{align-self:flex-end;flex-direction:row-reverse}
        .bubble{background:#2d2f3e;padding:10px 14px;border-radius:20px;color:#e2e8f0}
        .my-message .bubble{background:#6366f1;color:white}
        .input-area{display:flex;gap:8px;padding:16px;border-top:1px solid #2d2f3e}
        .input-area input{flex:1;background:#0f0f14;border:1px solid #2d2f3e;border-radius:40px;padding:12px;color:white}
        .input-area button{background:#6366f1;border:none;border-radius:40px;padding:0 20px;color:white;cursor:pointer}
        .status{padding:8px;text-align:center;color:#7c8ba0;font-size:12px}
        @media (max-width:600px){.sidebar{position:fixed;left:-280px;height:100%;z-index:10}.sidebar.open{left:0}.menu-btn{position:fixed;bottom:20px;left:20px;background:#6366f1;border:none;border-radius:50%;width:50px;height:50px;color:white;font-size:24px;z-index:20}}
        .menu-btn{display:none}
    </style>
</head>
<body>
<div id="root"></div>
<script>
    let socket = null;
    let currentUser = null;
    let currentRoom = null;
    let rooms = [];
    let messages = {};
    
    const savedToken = localStorage.getItem('shadow_token');
    const savedUsername = localStorage.getItem('shadow_username');
    
    function renderAuth() {
        document.getElementById('root').innerHTML = `
            <div class="auth-panel">
                <input type="text" id="username" placeholder="Логин">
                <input type="password" id="password" placeholder="Пароль">
                <div class="buttons">
                    <button id="loginBtn">Войти</button>
                    <button id="registerBtn">Зарегистрироваться</button>
                </div>
                <div id="authStatus" style="color:#7c8ba0;text-align:center;margin-top:12px"></div>
            </div>
        `;
        document.getElementById('loginBtn').onclick = login;
        document.getElementById('registerBtn').onclick = register;
    }
    
    function renderChat() {
        document.getElementById('root').innerHTML = `
            <button class="menu-btn" id="menuBtn">☰</button>
            <div class="chat-container">
                <div class="sidebar" id="sidebar">
                    <div class="sidebar-header">📁 Чаты</div>
                    <div class="rooms-list" id="roomsList"></div>
                </div>
                <div class="chat-area">
                    <div class="chat-header">
                        <h3 id="roomTitle">${currentRoom || 'Выберите чат'}</h3>
                        ${currentRoom ? `<button class="leave-btn" id="leaveBtn">Выйти</button>` : ''}
                    </div>
                    <div class="messages" id="messages"></div>
                    <div class="input-area" id="inputArea" style="display:${currentRoom ? 'flex' : 'none'}">
                        <input type="text" id="messageInput" placeholder="Сообщение...">
                        <button id="sendBtn">➤</button>
                    </div>
                    <div class="status" id="status">Готов</div>
                </div>
            </div>
        `;
        
        renderRoomsList();
        renderMessages();
        
        document.getElementById('menuBtn')?.addEventListener('click', () => {
            document.getElementById('sidebar').classList.toggle('open');
        });
        document.getElementById('leaveBtn')?.addEventListener('click', leaveRoom);
        document.getElementById('sendBtn')?.addEventListener('click', sendMessage);
        document.getElementById('messageInput')?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
    }
    
    function renderRoomsList() {
        const container = document.getElementById('roomsList');
        if (!container) return;
        container.innerHTML = rooms.map(room => `
            <div class="room-item ${currentRoom === room ? 'active' : ''}" data-room="${room}">
                <div class="room-name">${escapeHtml(room)}</div>
            </div>
        `).join('');
        document.querySelectorAll('.room-item').forEach(el => {
            el.addEventListener('click', () => switchRoom(el.dataset.room));
        });
    }
    
    function renderMessages() {
        const container = document.getElementById('messages');
        if (!container) return;
        const msgs = messages[currentRoom] || [];
        container.innerHTML = msgs.map(msg => `
            <div class="message ${msg.username === currentUser ? 'my-message' : ''}">
                <div class="bubble">
                    ${msg.username !== currentUser ? `<b>${escapeHtml(msg.username)}</b><br>` : ''}
                    ${escapeHtml(msg.text)}
                </div>
            </div>
        `).join('');
        container.scrollTop = container.scrollHeight;
    }
    
    function escapeHtml(str) {
        return String(str).replace(/[&<>]/g, m => m === '&' ? '&amp;' : m === '<' ? '&lt;' : '&gt;');
    }
    
    async function apiRequest(endpoint, data) {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return res.json();
    }
    
    async function login() {
        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value.trim();
        if (!username || !password) return;
        const result = await apiRequest('/login', { username, password });
        if (result.success) {
            currentUser = username;
            localStorage.setItem('shadow_token', result.token);
            localStorage.setItem('shadow_username', username);
            await loadUserData();
            connectSocket();
            renderChat();
        } else {
            document.getElementById('authStatus').innerText = result.error;
        }
    }
    
    async function register() {
        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value.trim();
        if (!username || !password) return;
        const result = await apiRequest('/register', { username, password });
        document.getElementById('authStatus').innerText = result.success ? '✅ Регистрация успешна! Теперь войдите.' : result.error;
    }
    
    async function loadUserData() {
        const result = await apiRequest('/user_data', { username: currentUser });
        if (result.success) {
            rooms = result.rooms;
            messages = result.messages || {};
        }
    }
    
    function connectSocket() {
        if (socket) socket.disconnect();
        socket = io({ reconnection: true });
        socket.on('connect', () => {
            socket.emit('register', currentUser);
        });
        socket.on('new_message', (data) => {
            if (!messages[data.room]) messages[data.room] = [];
            messages[data.room].push(data);
            if (data.room === currentRoom) renderMessages();
            renderRoomsList();
        });
    }
    
    function switchRoom(room) {
        currentRoom = room;
        renderChat();
    }
    
    function leaveRoom() {
        if (currentRoom && socket) {
            socket.emit('leave_room', { room: currentRoom });
            currentRoom = null;
            renderChat();
        }
    }
    
    function sendMessage() {
        const input = document.getElementById('messageInput');
        const text = input.value.trim();
        if (!text || !currentRoom || !socket) return;
        socket.emit('message', { room: currentRoom, text });
        input.value = '';
    }
    
    async function autoLogin() {
        if (!savedToken) { renderAuth(); return; }
        const result = await apiRequest('/auto_login', { token: savedToken });
        if (result.success) {
            currentUser = savedUsername;
            await loadUserData();
            connectSocket();
            renderChat();
        } else {
            localStorage.removeItem('shadow_token');
            localStorage.removeItem('shadow_username');
            renderAuth();
        }
    }
    
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
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return {'success': False, 'error': 'Введите логин и пароль'}
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT username FROM users WHERE username = ?', (username,))
    if c.fetchone():
        conn.close()
        return {'success': False, 'error': 'Пользователь уже существует'}
    
    password_hash = hash_password(password)
    c.execute('INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)',
              (username, password_hash, datetime.now()))
    conn.commit()
    conn.close()
    return {'success': True}

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
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
    expires_at = datetime.now() + timedelta(days=365*10)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO sessions (token, username, expires_at) VALUES (?, ?, ?)',
              (token, username, expires_at))
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
    c.execute('SELECT username FROM sessions WHERE token = ?', (token,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return {'success': False, 'error': 'Токен не найден'}
    
    return {'success': True, 'username': row[0]}

@app.route('/user_data', methods=['POST'])
def user_data():
    data = request.json
    username = data.get('username')
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('SELECT DISTINCT room FROM messages WHERE username = ?', (username,))
    rooms = [row[0] for row in c.fetchall()]
    
    messages_dict = {}
    for room in rooms:
        c.execute('SELECT username, text, timestamp FROM messages WHERE room = ? ORDER BY timestamp', (room,))
        rows = c.fetchall()
        messages_dict[room] = [{'username': r[0], 'text': r[1], 'timestamp': r[2]} for r in rows]
    
    conn.close()
    return {'success': True, 'rooms': rooms, 'messages': messages_dict}

@socketio.on('register')
def handle_register(username):
    print(f'User {username} connected')

@socketio.on('message')
def handle_message(data):
    room = data['room']
    text = data['text']
    username = request.sid
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO messages (room, username, text, timestamp) VALUES (?, ?, ?, ?)',
              (room, username, text, datetime.now()))
    conn.commit()
    conn.close()
    
    emit('new_message', {'room': room, 'username': username, 'text': text}, to=room)

@socketio.on('leave_room')
def handle_leave(data):
    room = data['room']
    leave_room(room)

if __name__ == '__main__':
    init_db()
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
