from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, join_room
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <title>Shadow Chat — с галочками</title>
    <script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{background:#0f0f14;font-family:system-ui;height:100vh;display:flex;justify-content:center;align-items:center;padding:20px}
        .container{background:#1e1f2c;border-radius:40px;width:100%;max-width:600px;height:90%;display:flex;flex-direction:column;overflow:hidden}
        .header{background:#1e1f2c;padding:16px;border-bottom:1px solid #2d2f3e;text-align:center}
        .header h1{color:#f1f5f9;font-size:1.3rem}
        .auth-panel{display:flex;flex-direction:column;gap:12px;padding:20px;background:#0f0f14;border-bottom:1px solid #2d2f3e}
        .auth-panel input{background:#1e1f2c;border:1px solid #2d2f3e;border-radius:40px;padding:12px 16px;color:white;outline:none;width:100%}
        .auth-panel input:focus{border-color:#6366f1}
        .buttons{display:flex;gap:12px;margin-top:8px}
        .buttons button{flex:1;background:#6366f1;border:none;border-radius:40px;padding:12px;color:white;font-weight:bold;cursor:pointer}
        .buttons button:active{transform:scale(0.97)}
        .room-panel{display:flex;flex-direction:column;gap:8px;padding:12px;background:#0f0f14;border-bottom:1px solid #2d2f3e;display:none}
        .room-panel .row{display:flex;gap:8px}
        .room-panel input{flex:1;background:#1e1f2c;border:1px solid #2d2f3e;border-radius:40px;padding:10px 16px;color:white;outline:none}
        .room-panel button{background:#6366f1;border:none;border-radius:40px;padding:0 20px;color:white;font-weight:bold;cursor:pointer}
        .messages{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px}
        .message{display:flex;gap:10px}
        .my-message{justify-content:flex-end}
        .bubble{max-width:70%;padding:10px 14px;border-radius:20px;font-size:14px;line-height:1.4;word-break:break-word}
        .my-message .bubble{background:#6366f1;color:white}
        .other-message .bubble{background:#2d2f3e;color:#e2e8f0}
        .message-info{font-size:10px;color:#7c8ba0;margin-top:4px;text-align:right}
        .input-area{display:flex;gap:8px;padding:16px;border-top:1px solid #2d2f3e;background:#0f0f14;display:none}
        .input-area input{flex:1;background:#1e1f2c;border:1px solid #2d2f3e;border-radius:40px;padding:12px;color:white;outline:none}
        .input-area button{background:#6366f1;border:none;border-radius:40px;padding:0 20px;color:white;font-weight:bold;cursor:pointer}
        .status{font-size:12px;color:#7c8ba0;text-align:center;padding:8px}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>💬 Shadow Chat</h1>
    </div>
    <div class="auth-panel" id="authPanel">
        <input type="text" id="username" placeholder="Логин">
        <input type="password" id="password" placeholder="Пароль">
        <div class="buttons">
            <button id="loginBtn">Войти</button>
            <button id="registerBtn">Зарегистрироваться</button>
        </div>
    </div>
    <div class="room-panel" id="roomPanel">
        <div class="row">
            <input type="text" id="roomCode" placeholder="Код комнаты (например, superchat)">
            <button id="joinBtn">Войти в комнату</button>
        </div>
    </div>
    <div class="messages" id="messages"></div>
    <div class="input-area" id="inputArea">
        <input type="text" id="messageInput" placeholder="Напиши сообщение..." autocomplete="off">
        <button id="sendBtn">➤</button>
    </div>
    <div class="status" id="status">Введите логин и пароль</div>
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
    
    function addMessage(text, isMy, username = '', readStatus = 'sent') {
        const div = document.createElement('div');
        div.className = `message ${isMy ? 'my-message' : 'other-message'}`;
        const bubble = document.createElement('div');
        bubble.className = 'bubble';
        if (!isMy && username) bubble.innerHTML = `<b>${escapeHtml(username)}</b><br>${escapeHtml(text)}`;
        else bubble.innerText = text;
        if (isMy) {
            const info = document.createElement('div');
            info.className = 'message-info';
            info.innerText = readStatus === 'read' ? '✓✓' : '✓';
            bubble.appendChild(info);
        }
        div.appendChild(bubble);
        messagesDiv.appendChild(div);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
    
    function escapeHtml(str) {
        return str.replace(/[&<>]/g, function(m) {
            if (m === '&') return '&amp;';
            if (m === '<') return '&lt;';
            if (m === '>') return '&gt;';
            return m;
        });
    }
    
    function loadHistory(history) {
        messagesDiv.innerHTML = '';
        for (let msg of history) {
            const isMy = (msg.username === currentUser);
            addMessage(msg.text, isMy, isMy ? '' : msg.username, msg.read_status);
        }
    }
    
    async function apiRequest(endpoint, data) {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return res.json();
    }
    
    async function autoLogin() {
        if (!savedToken) return false;
        const result = await apiRequest('/auto_login', { token: savedToken });
        if (result.success) {
            currentUser = savedUsername;
            authPanel.style.display = 'none';
            roomPanel.style.display = 'flex';
            statusSpan.innerText = `✅ С возвращением, ${currentUser}! Введите код комнаты.`;
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
            statusSpan.innerText = `✅ Добро пожаловать, ${username}! Введите код комнаты.`;
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
        const result = await apiRequest('/register', { username, password });
        if (result.success) {
            statusSpan.innerText = `✅ Регистрация успешна! Теперь войдите.`;
        } else {
            statusSpan.innerText = `❌ ${result.error}`;
        }
    };
    
    function connectToRoom(room) {
        if (socket) socket.disconnect();
        socket = io({ reconnection: true, reconnectionAttempts: Infinity });
        socket.on('connect', () => {
            socket.emit('join', { room, username: currentUser });
            currentRoom = room;
            statusSpan.innerText = `✅ Комната: ${room}. Пишите сообщения.`;
            messageInput.focus();
        });
        socket.on('history', (history) => {
            loadHistory(history);
            inputArea.style.display = 'flex';
        });
        socket.on('new_message', (data) => {
            const isMy = (data.username === currentUser);
            addMessage(data.text, isMy, isMy ? '' : data.username, data.read_status);
            if (!isMy && currentRoom === data.room) {
                socket.emit('mark_read', { room: data.room });
            }
        });
        socket.on('read_receipt', ({ room }) => {
            if (room === currentRoom) {
                document.querySelectorAll('.my-message .message-info').forEach(info => {
                    if (info.innerText === '✓') info.innerText = '✓✓';
                });
            }
        });
    }
    
    joinBtn.onclick = () => {
        const room = roomCodeInput.value.trim();
        if (!room) {
            statusSpan.innerText = '❌ Введите код комнаты';
            return;
        }
        connectToRoom(room);
    };
    
    sendBtn.onclick = () => {
        const text = messageInput.value.trim();
        if (text && socket && currentRoom) {
            socket.emit('message', { room: currentRoom, text, username: currentUser });
            messageInput.value = '';
        }
    };
    
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendBtn.click();
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
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT username, text, timestamp, read_status FROM messages WHERE room = ? ORDER BY timestamp', (room,))
    rows = c.fetchall()
    history = [{'username': r[0], 'text': r[1], 'timestamp': r[2], 'read_status': r[3]} for r in rows]
    conn.close()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE messages SET read_status = "read" WHERE room = ? AND username != ? AND read_status = "sent"', (room, username))
    conn.commit()
    conn.close()
    emit('read_receipt', {'room': room, 'username': username}, to=room)
    emit('history', history)
    emit('new_message', {'username': 'system', 'text': f'{username} присоединился к чату', 'read_status': 'read'}, to=room, skip_sid=request.sid)

@socketio.on('message')
def handle_message(data):
    room = data['room']
    text = data['text']
    username = data.get('username')
    if not username:
        return
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO messages (room, username, text, timestamp, read_status) VALUES (?, ?, ?, ?, ?)',
              (room, username, text, datetime.now(), 'sent'))
    conn.commit()
    conn.close()
    
    emit('new_message', {'username': username, 'text': text, 'read_status': 'sent'}, to=room)

@socketio.on('mark_read')
def handle_mark_read(data):
    room = data['room']
    username = data.get('username') or request.sid
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE messages SET read_status = "read" WHERE room = ? AND username != ? AND read_status = "sent"', (room, username))
    conn.commit()
    conn.close()
    emit('read_receipt', {'room': room, 'username': username}, to=room)

if __name__ == '__main__':
    init_db()
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
