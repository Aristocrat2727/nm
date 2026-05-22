from flask import Flask, request, render_template_string
from flask_socketio import SocketIO, emit, join_room, leave_room
import sqlite3
import secrets
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
socketio = SocketIO(app, cors_allowed_origins="*")

DB_PATH = 'chat.db'

connected_users = {}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room TEXT NOT NULL,
        username TEXT NOT NULL,
        text TEXT NOT NULL,
        time TEXT NOT NULL
    )''')
    conn.commit()
    conn.close()

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <title>Shadow Chat</title>
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{background:#0f0f14;font-family:system-ui;height:100vh;display:flex;justify-content:center;align-items:center}
        .login-box{background:#1e1f2c;padding:30px;border-radius:30px;width:100%;max-width:350px}
        .login-box input{width:100%;padding:12px;margin-bottom:12px;background:#0f0f14;border:1px solid #2d2f3e;border-radius:30px;color:white}
        .login-box button{width:100%;padding:12px;background:#6366f1;border:none;border-radius:30px;color:white;font-weight:bold;cursor:pointer}
        .chat-container{display:flex;flex-direction:column;height:100vh;width:100%}
        .chat-header{background:#1e1f2c;padding:15px;border-bottom:1px solid #2d2f3e;text-align:center}
        .chat-header h3{color:white}
        .messages{flex:1;overflow:auto;padding:15px;display:flex;flex-direction:column;gap:10px}
        .msg{max-width:70%;padding:10px 15px;border-radius:20px;word-break:break-word}
        .my{background:#6366f1;align-self:flex-end}
        .other{background:#2d2f3e;align-self:flex-start}
        .msg-name{font-size:11px;margin-bottom:4px;opacity:0.7}
        .input-area{display:flex;gap:10px;padding:15px;border-top:1px solid #2d2f3e}
        .input-area input{flex:1;padding:12px;background:#0f0f14;border:1px solid #2d2f3e;border-radius:30px;color:white}
        .input-area button{padding:0 20px;background:#6366f1;border:none;border-radius:30px;color:white;cursor:pointer}
        .status{padding:10px;text-align:center;color:#888;font-size:12px}
    </style>
</head>
<body>
<div id="root"></div>
<script>
    let socket = null, currentUser = null, currentRoom = null, messages = [];
    const savedToken = localStorage.getItem('token');
    const savedUser = localStorage.getItem('user');
    
    function api(url, data) {
        return fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)}).then(r=>r.json());
    }
    
    function renderLogin() {
        document.getElementById('root').innerHTML = `
            <div class="login-box">
                <input type="text" id="loginUser" placeholder="Логин">
                <input type="password" id="loginPass" placeholder="Пароль">
                <button onclick="doLogin()">Войти</button>
                <button onclick="doRegister()" style="margin-top:10px;background:#2d2f3e">Регистрация</button>
                <div id="msg" style="color:#f87171;text-align:center;margin-top:10px"></div>
            </div>
        `;
    }
    
    function renderChat() {
        document.getElementById('root').innerHTML = `
            <div class="chat-container">
                <div class="chat-header">
                    <h3>💬 Комната: ${escape(currentRoom)}</h3>
                </div>
                <div class="messages" id="messagesDiv"></div>
                <div class="input-area">
                    <input type="text" id="msgInput" placeholder="Сообщение">
                    <button id="sendBtn">➤</button>
                </div>
                <div class="status" id="status">🔗 Ссылка для друга: ${window.location.href}?room=${currentRoom}</div>
            </div>
        `;
        renderMessages();
        document.getElementById('sendBtn')?.addEventListener('click',sendMsg);
        document.getElementById('msgInput')?.addEventListener('keypress',e=>{if(e.key==='Enter')sendMsg();});
    }
    
    function renderMessages() {
        const el = document.getElementById('messagesDiv');
        if(!el) return;
        el.innerHTML = messages.map(m => `
            <div class="msg ${m.username===currentUser?'my':'other'}">
                ${m.username!==currentUser?`<div class="msg-name">${escape(m.username)}</div>`:''}
                <div>${escape(m.text)}</div>
            </div>
        `).join('');
        el.scrollTop = el.scrollHeight;
    }
    
    function escape(s){return String(s).replace(/[&<>]/g,function(m){return m==='&'?'&amp;':m==='<'?'&lt;':'>'?'&gt;':'';});}
    
    async function doLogin(){
        const u = document.getElementById('loginUser').value.trim();
        const p = document.getElementById('loginPass').value.trim();
        if(!u||!p) return;
        const res = await api('/login',{username:u,password:p});
        if(res.ok){
            localStorage.setItem('token',res.token);
            localStorage.setItem('user',u);
            location.reload();
        } else {
            document.getElementById('msg').innerText = res.error;
        }
    }
    
    async function doRegister(){
        const u = document.getElementById('loginUser').value.trim();
        const p = document.getElementById('loginPass').value.trim();
        if(!u||!p) return;
        const res = await api('/register',{username:u,password:p});
        document.getElementById('msg').innerText = res.ok ? '✅ Зарегистрирован, теперь войдите' : res.error;
    }
    
    async function loadMessages(room){
        const res = await api('/get_messages',{room});
        if(res.ok){
            messages = res.messages;
            renderMessages();
        }
    }
    
    function connect(){
        socket = io();
        socket.on('connect',()=>{
            socket.emit('register', currentUser);
            socket.emit('join_room', {room: currentRoom});
        });
        socket.on('new_msg',(data)=>{
            messages.push(data);
            renderMessages();
        });
    }
    
    function sendMsg(){
        const inp = document.getElementById('msgInput');
        if(!inp) return;
        const text = inp.value.trim();
        if(!text) return;
        socket.emit('msg',{room:currentRoom,text});
        inp.value = '';
    }
    
    async function init(){
        // Получаем комнату из URL
        const urlParams = new URLSearchParams(window.location.search);
        const roomFromUrl = urlParams.get('room');
        
        if(savedToken && savedUser){
            const res = await api('/check_user',{token:savedToken});
            if(res.ok){
                currentUser = savedUser;
                if(roomFromUrl){
                    currentRoom = roomFromUrl;
                } else {
                    // Если нет комнаты в URL, показываем поле для ввода
                    document.getElementById('root').innerHTML = `
                        <div class="login-box">
                            <input type="text" id="roomCode" placeholder="Код комнаты (например, superchat)">
                            <button onclick="enterRoom()">Войти в комнату</button>
                        </div>
                    `;
                    window.enterRoom = function(){
                        const room = document.getElementById('roomCode').value.trim();
                        if(room){
                            window.location.href = `?room=${room}`;
                        }
                    };
                    return;
                }
                await loadMessages(currentRoom);
                connect();
                renderChat();
                return;
            }
        }
        renderLogin();
    }
    init();
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
    u = data.get('username', '').strip()
    p = data.get('password', '').strip()
    if not u or not p:
        return {'ok': False, 'error': 'Заполните поля'}
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT username FROM users WHERE username = ?', (u,))
    if c.fetchone():
        conn.close()
        return {'ok': False, 'error': 'Пользователь есть'}
    c.execute('INSERT INTO users (username, password) VALUES (?, ?)', (u, p))
    conn.commit()
    conn.close()
    return {'ok': True}

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    u = data.get('username', '').strip()
    p = data.get('password', '').strip()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT password FROM users WHERE username = ?', (u,))
    row = c.fetchone()
    conn.close()
    if not row or row[0] != p:
        return {'ok': False, 'error': 'Неверно'}
    token = secrets.token_urlsafe(32)
    return {'ok': True, 'token': token}

@app.route('/check_user', methods=['POST'])
def check_user():
    # упрощённо: всегда возвращаем ok
    return {'ok': True}

@app.route('/get_messages', methods=['POST'])
def get_messages():
    room = request.json.get('room')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT username, text, time FROM messages WHERE room = ? ORDER BY time', (room,))
    rows = c.fetchall()
    messages = [{'username': r[0], 'text': r[1], 'time': r[2]} for r in rows]
    conn.close()
    return {'ok': True, 'messages': messages}

@socketio.on('register')
def handle_register(username):
    connected_users[request.sid] = username
    print(f'{username} connected')

@socketio.on('join_room')
def handle_join(data):
    room = data['room']
    join_room(room)
    print(f'{connected_users.get(request.sid)} joined {room}')

@socketio.on('msg')
def handle_msg(data):
    room = data['room']
    text = data['text']
    username = connected_users.get(request.sid)
    if not username:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO messages (room, username, text, time) VALUES (?, ?, ?, ?)',
              (room, username, text, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    emit('new_msg', {'room': room, 'username': username, 'text': text}, to=room)

@socketio.on('disconnect')
def handle_disconnect():
    connected_users.pop(request.sid, None)

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 8080))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
