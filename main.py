import os
import hashlib
import secrets
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, join_room
from supabase import create_client

# ========== ТВОИ ДАННЫЕ ИЗ SUPABASE ==========
SUPABASE_URL = "https://bjqgguylmkgvqxqblsni.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJqcWdndXlsbWtndnF4cWJsc25pIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk2MjUzOTgsImV4cCI6MjA5NTIwMTM5OH0.-oFtd1CPQfGuXQK1AEiCkYWmGrb5IEvrfGUrpa6he2o"
# ============================================

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shadow Chat</title>
    <script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #0f0f14;
            font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 12px;
        }
        .container {
            background: #1e1f2c;
            border-radius: 32px;
            width: 100%;
            max-width: 600px;
            height: 90vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25);
        }
        .header { background: #1e1f2c; padding: 16px; border-bottom: 1px solid #2d2f3e; text-align: center; }
        .header h1 { color: #f1f5f9; font-size: 1.3rem; }
        .auth-panel { display: flex; flex-direction: column; gap: 12px; padding: 20px; background: #0f0f14; border-bottom: 1px solid #2d2f3e; }
        .auth-panel input { background: #1e1f2c; border: 1px solid #2d2f3e; border-radius: 40px; padding: 14px 16px; color: white; outline: none; width: 100%; font-size: 16px; }
        .buttons { display: flex; gap: 12px; margin-top: 8px; }
        .buttons button { flex: 1; background: #6366f1; border: none; border-radius: 40px; padding: 14px; color: white; font-weight: bold; cursor: pointer; font-size: 16px; }
        .room-panel { display: none; flex-direction: column; gap: 8px; padding: 12px; background: #0f0f14; border-bottom: 1px solid #2d2f3e; }
        .room-panel .row { display: flex; gap: 8px; }
        .room-panel input { flex: 1; background: #1e1f2c; border: 1px solid #2d2f3e; border-radius: 40px; padding: 12px 16px; color: white; outline: none; font-size: 16px; }
        .room-panel button { background: #6366f1; border: none; border-radius: 40px; padding: 0 24px; color: white; font-weight: bold; cursor: pointer; }
        .messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 8px; }
        .message { display: flex; width: 100%; animation: fadeIn 0.2s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
        .my-message { justify-content: flex-end; }
        .other-message { justify-content: flex-start; }
        .avatar { width: 32px; height: 32px; border-radius: 50%; background: #2d2f3e; display: flex; align-items: center; justify-content: center; font-size: 12px; color: #e2e8f0; margin-right: 8px; }
        .my-message .avatar { display: none; }
        .bubble { max-width: 75%; padding: 8px 12px; border-radius: 18px; font-size: 15px; line-height: 1.4; word-wrap: break-word; }
        .my-message .bubble { background: #6366f1; color: white; border-bottom-right-radius: 4px; }
        .other-message .bubble { background: #2d2f3e; color: #e2e8f0; border-bottom-left-radius: 4px; }
        .message-info { font-size: 10px; color: #7c8ba0; margin-top: 4px; display: flex; gap: 4px; justify-content: flex-end; }
        .username { font-weight: bold; margin-bottom: 4px; font-size: 12px; color: #a5b4fc; }
        .input-area { display: none; gap: 8px; padding: 12px; border-top: 1px solid #2d2f3e; background: #0f0f14; }
        .input-area input { flex: 1; background: #1e1f2c; border: 1px solid #2d2f3e; border-radius: 40px; padding: 14px; color: white; outline: none; font-size: 16px; }
        .input-area button { background: #6366f1; border: none; border-radius: 40px; padding: 0 24px; color: white; font-weight: bold; cursor: pointer; }
        .status { font-size: 11px; color: #7c8ba0; text-align: center; padding: 8px; background: #0f0f14; }
        .hidden { display: none; }
    </style>
</head>
<body>
<div class="container">
    <div class="header"><h1>💬 Shadow Chat</h1></div>
    <div class="auth-panel" id="authPanel">
        <input type="text" id="username" placeholder="Логин">
        <input type="password" id="password" placeholder="Пароль">
        <div class="buttons">
            <button id="loginBtn">Войти</button>
            <button id="registerBtn">Регистрация</button>
        </div>
    </div>
    <div class="room-panel" id="roomPanel">
        <div class="row">
            <input type="text" id="roomCode" placeholder="Код комнаты">
            <button id="joinBtn">Войти</button>
        </div>
    </div>
    <div class="messages" id="messages"></div>
    <div class="input-area" id="inputArea">
        <input type="text" id="messageInput" placeholder="Сообщение...">
        <button id="sendBtn">➤</button>
    </div>
    <div class="status" id="status">Введите логин и пароль</div>
</div>
<script>
    let socket = null, currentRoom = null, currentUser = null;
    const savedToken = localStorage.getItem('shadow_token');
    const savedUsername = localStorage.getItem('shadow_username');
    
    function formatTime(isoString) {
        if (!isoString) return '';
        try { let d = new Date(isoString); return d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}); }
        catch(e) { return ''; }
    }
    
    function addMessage(text, isMy, username='', readStatus='sent', timestamp=null) {
        const div = document.createElement('div');
        div.className = 'message';
        if (isMy) {
            div.classList.add('my-message');
            const bubble = document.createElement('div');
            bubble.className = 'bubble';
            bubble.innerText = text;
            const info = document.createElement('div');
            info.className = 'message-info';
            info.innerHTML = `<span>${formatTime(timestamp)}</span><span>${readStatus === 'read' ? '✓✓' : '✓'}</span>`;
            bubble.appendChild(info);
            div.appendChild(bubble);
        } else {
            div.classList.add('other-message');
            const avatar = document.createElement('div');
            avatar.className = 'avatar';
            avatar.innerText = (username.charAt(0) || '?').toUpperCase();
            const bubble = document.createElement('div');
            bubble.className = 'bubble';
            const nameSpan = document.createElement('div');
            nameSpan.className = 'username';
            nameSpan.innerText = username;
            bubble.appendChild(nameSpan);
            bubble.appendChild(document.createTextNode(text));
            const info = document.createElement('div');
            info.className = 'message-info';
            info.innerHTML = `<span>${formatTime(timestamp)}</span>`;
            bubble.appendChild(info);
            div.appendChild(avatar);
            div.appendChild(bubble);
        }
        document.getElementById('messages').appendChild(div);
        document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight;
    }
    
    function loadHistory(history) {
        const container = document.getElementById('messages');
        container.innerHTML = '';
        for (let msg of history) { addMessage(msg.text, msg.username === currentUser, msg.username, msg.read_status, msg.timestamp); }
    }
    
    async function apiRequest(endpoint, data) {
        let res = await fetch(endpoint, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data) });
        return await res.json();
    }
    
    async function autoLogin() {
        if (!savedToken || !savedUsername) return false;
        let result = await apiRequest('/auto_login', {token: savedToken});
        if (result.success) {
            currentUser = savedUsername;
            document.getElementById('authPanel').style.display = 'none';
            document.getElementById('roomPanel').style.display = 'flex';
            document.getElementById('status').innerText = '✅ Введите код комнаты';
            return true;
        } else {
            localStorage.removeItem('shadow_token');
            localStorage.removeItem('shadow_username');
            return false;
        }
    }
    
    document.getElementById('loginBtn').onclick = async () => {
        let username = document.getElementById('username').value.trim();
        let password = document.getElementById('password').value.trim();
        if (!username || !password) { document.getElementById('status').innerText = '❌ Введите логин и пароль'; return; }
        let result = await apiRequest('/login', {username, password});
        if (result.success) {
            currentUser = username;
            localStorage.setItem('shadow_token', result.token);
            localStorage.setItem('shadow_username', username);
            document.getElementById('authPanel').style.display = 'none';
            document.getElementById('roomPanel').style.display = 'flex';
            document.getElementById('status').innerText = '✅ Введите код комнаты';
        } else { document.getElementById('status').innerText = `❌ ${result.error}`; }
    };
    
    document.getElementById('registerBtn').onclick = async () => {
        let username = document.getElementById('username').value.trim();
        let password = document.getElementById('password').value.trim();
        if (!username || !password) { document.getElementById('status').innerText = '❌ Введите логин и пароль'; return; }
        let result = await apiRequest('/register', {username, password});
        if (result.success) {
            document.getElementById('status').innerText = '✅ Регистрация успешна! Теперь войдите.';
            document.getElementById('username').value = '';
            document.getElementById('password').value = '';
        } else { document.getElementById('status').innerText = `❌ ${result.error}`; }
    };
    
    function connectToRoom(room) {
        if (socket) socket.close();
        localStorage.setItem('shadow_room', room);
        socket = io();
        socket.on('connect', () => {
            socket.emit('join', {room, username: currentUser});
            currentRoom = room;
            document.getElementById('status').innerText = `✅ Комната: ${room}`;
            document.getElementById('inputArea').style.display = 'flex';
        });
        socket.on('history', (history) => { loadHistory(history); });
        socket.on('new_message', (data) => {
            let isMy = (data.username === currentUser);
            addMessage(data.text, isMy, data.username, data.read_status, data.timestamp);
            if (!isMy && currentRoom === data.room) { socket.emit('mark_read', {room: data.room}); }
        });
        socket.on('read_receipt', ({room}) => {
            if (room === currentRoom) { document.querySelectorAll('.my-message .message-info span:last-child').forEach(el => { if(el.innerText === '✓') el.innerText = '✓✓'; }); }
        });
        socket.on('disconnect', () => { document.getElementById('status').innerText = '⚠️ Потеря соединения'; });
    }
    
    document.getElementById('joinBtn').onclick = () => {
        let room = document.getElementById('roomCode').value.trim();
        if (!room) { document.getElementById('status').innerText = '❌ Введите код комнаты'; return; }
        connectToRoom(room);
    };
    document.getElementById('sendBtn').onclick = () => {
        let text = document.getElementById('messageInput').value.trim();
        if (text && socket && currentRoom) {
            socket.emit('message', {room: currentRoom, text, username: currentUser});
            document.getElementById('messageInput').value = '';
        }
    };
    document.getElementById('messageInput').addEventListener('keypress', (e) => { if(e.key === 'Enter') document.getElementById('sendBtn').click(); });
    
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
    
    existing = supabase.table('users').select('username').eq('username', username).execute()
    if existing.data:
        return {'success': False, 'error': 'Пользователь уже существует'}
    
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    supabase.table('users').insert({'username': username, 'password_hash': password_hash, 'created_at': datetime.now().isoformat()}).execute()
    return {'success': True}

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return {'success': False, 'error': 'Введите логин и пароль'}
    
    res = supabase.table('users').select('password_hash').eq('username', username).execute()
    if not res.data or res.data[0]['password_hash'] != hashlib.sha256(password.encode()).hexdigest():
        return {'success': False, 'error': 'Неверный логин или пароль'}
    
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(days=365*50)).isoformat()
    supabase.table('sessions').upsert({'token': token, 'username': username, 'expires_at': expires_at}).execute()
    return {'success': True, 'token': token}

@app.route('/auto_login', methods=['POST'])
def auto_login():
    data = request.json
    token = data.get('token')
    if not token:
        return {'success': False, 'error': 'Нет токена'}
    
    res = supabase.table('sessions').select('username, expires_at').eq('token', token).execute()
    if not res.data:
        return {'success': False, 'error': 'Токен не найден'}
    
    row = res.data[0]
    if datetime.now() > datetime.fromisoformat(row['expires_at'].replace('Z', '+00:00')):
        return {'success': False, 'error': 'Токен истёк'}
    return {'success': True, 'username': row['username']}

@socketio.on('join')
def handle_join(data):
    room = data['room']
    username = data['username']
    join_room(room)
    
    res = supabase.table('messages').select('username, text, timestamp, read_status').eq('room', room).order('timestamp').execute()
    history = [{'username': r['username'], 'text': r['text'], 'timestamp': r['timestamp'], 'read_status': r['read_status']} for r in res.data]
    supabase.table('messages').update({'read_status': 'read'}).eq('room', room).neq('username', username).execute()
    emit('history', history)
    emit('read_receipt', {'room': room}, to=room)

@socketio.on('message')
def handle_message(data):
    room = data['room']
    text = data['text']
    username = data.get('username')
    if not username or not text:
        return
    supabase.table('messages').insert({'room': room, 'username': username, 'text': text, 'timestamp': datetime.now().isoformat(), 'read_status': 'sent'}).execute()
    emit('new_message', {'username': username, 'text': text, 'read_status': 'sent', 'timestamp': datetime.now().isoformat()}, to=room)

@socketio.on('mark_read')
def handle_mark_read(data):
    room = data['room']
    supabase.table('messages').update({'read_status': 'read'}).eq('room', room).eq('read_status', 'sent').execute()
    emit('read_receipt', {'room': room}, to=room)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
