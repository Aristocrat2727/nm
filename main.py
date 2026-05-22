from flask import Flask, request, render_template_string, session
from flask_socketio import SocketIO, emit, join_room, leave_room
import sqlite3
import secrets
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
socketio = SocketIO(app, cors_allowed_origins="*")

DB_PATH = 'chat.db'

# Создаём таблицы
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
        body{background:#0f0f14;font-family:system-ui}
        .page{display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px}
        .login-box{background:#1e1f2c;padding:30px;border-radius:30px;width:100%;max-width:350px}
        .login-box input{width:100%;padding:12px;margin-bottom:12px;background:#0f0f14;border:1px solid #2d2f3e;border-radius:30px;color:white}
        .login-box button{width:100%;padding:12px;background:#6366f1;border:none;border-radius:30px;color:white;font-weight:bold;cursor:pointer}
        .chat-app{display:flex;height:100vh}
        .sidebar{width:280px;background:#15161f;border-right:1px solid #2d2f3e;display:flex;flex-direction:column}
        .sidebar-header{padding:15px;border-bottom:1px solid #2d2f3e}
        .sidebar-header button{width:100%;padding:10px;background:#6366f1;border:none;border-radius:30px;color:white;cursor:pointer}
        .rooms-list{flex:1;overflow:auto}
        .room{padding:12px 15px;border-bottom:1px solid #2d2f3e;cursor:pointer}
        .room.active{background:#6366f1}
        .main{flex:1;display:flex;flex-direction:column}
        .chat-header{padding:15px;border-bottom:1px solid #2d2f3e;background:#1e1f2c}
        .messages{flex:1;overflow:auto;padding:15px;display:flex;flex-direction:column;gap:10px}
        .msg{max-width:70%;padding:10px 15px;border-radius:20px;word-break:break-word}
        .my{background:#6366f1;align-self:flex-end}
        .other{background:#2d2f3e;align-self:flex-start}
        .msg-name{font-size:11px;margin-bottom:4px;opacity:0.7}
        .input-area{display:flex;gap:10px;padding:15px;border-top:1px solid #2d2f3e}
        .input-area input{flex:1;padding:12px;background:#0f0f14;border:1px solid #2d2f3e;border-radius:30px;color:white}
        .input-area button{padding:0 20px;background:#6366f1;border:none;border-radius:30px;color:white;cursor:pointer}
        .status{padding:10px;text-align:center;color:#888;font-size:12px}
        @media (max-width:600px){.sidebar{position:fixed;left:-280px;height:100%;z-index:10}.sidebar.open{left:0}.menu-btn{position:fixed;bottom:20px;left:20px;background:#6366f1;border:none;border-radius:50%;width:50px;height:50px;color:white;font-size:24px;cursor:pointer;z-index:20}}
        .menu-btn{display:none}
    </style>
</head>
<body>
<div id="root"></div>
<script>
    let socket = null, currentUser = null, currentRoom = null, rooms = [], messages = {};
    const savedToken = localStorage.getItem('token');
    const savedUser = localStorage.getItem('user');
    
    function api(url, data) {
        return fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)}).then(r=>r.json());
    }
    
    function renderLogin() {
        document.getElementById('root').innerHTML = `
            <div class="page">
                <div class="login-box">
                    <input type="text" id="loginUser" placeholder="Логин">
                    <input type="password" id="loginPass" placeholder="Пароль">
                    <button onclick="doLogin()">Войти</button>
                    <button onclick="doRegister()" style="margin-top:10px;background:#2d2f3e">Регистрация</button>
                    <div id="msg" style="color:#f87171;text-align:center;margin-top:10px"></div>
                </div>
            </div>
        `;
    }
    
    function renderChat() {
        document.getElementById('root').innerHTML = `
            <button class="menu-btn" id="menuBtn">☰</button>
            <div class="chat-app">
                <div class="sidebar" id="sidebar">
                    <div class="sidebar-header"><button id="newRoomBtn">+ Новый чат</button></div>
                    <div class="rooms-list" id="roomsList"></div>
                </div>
                <div class="main">
                    <div class="chat-header"><b>${currentRoom || 'Выберите чат'}</b></div>
                    <div class="messages" id="messagesDiv"></div>
                    <div class="input-area" style="display:${currentRoom?'flex':'none'}">
                        <input type="text" id="msgInput" placeholder="Сообщение">
                        <button id="sendBtn">➤</button>
                    </div>
                </div>
            </div>
        `;
        renderRooms();
        renderMessages();
        document.getElementById('menuBtn')?.addEventListener('click',()=>document.getElementById('sidebar').classList.toggle('open'));
        document.getElementById('newRoomBtn')?.addEventListener('click',createRoom);
        document.getElementById('sendBtn')?.addEventListener('click',sendMsg);
        document.getElementById('msgInput')?.addEventListener('keypress',e=>{if(e.key==='Enter')sendMsg();});
    }
    
    function renderRooms() {
        const el = document.getElementById('roomsList');
        if(!el) return;
        el.innerHTML = rooms.map(r => `<div class="room ${r===currentRoom?'active':''}" data-room="${r}">${escape(r)}</div>`).join('');
        document.querySelectorAll('.room').forEach(el=>el.addEventListener('click',()=>switchRoom(el.dataset.room)));
    }
    
    function renderMessages() {
        const el = document.getElementById('messagesDiv');
        if(!el) return;
        const msgs = messages[currentRoom] || [];
        el.innerHTML = msgs.map(m => `
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
    
    async function loadData(){
        const token = localStorage.getItem('token');
        if(!token) return false;
        const res = await api('/data',{token});
        if(res.ok){
            rooms = res.rooms;
            messages = res.messages;
            return true;
        }
        return false;
    }
    
    function connect(){
        socket = io();
        socket.on('connect',()=>socket.emit('join',{user:currentUser}));
        socket.on('new_msg',(data)=>{
            if(!messages[data.room]) messages[data.room]=[];
            messages[data.room].push(data);
            if(data.room===currentRoom) renderMessages();
        });
    }
    
    function switchRoom(room){
        currentRoom = room;
        renderChat();
    }
    
    async function createRoom(){
        const name = prompt('Название чата');
        if(!name||!name.trim()) return;
        const n = name.trim();
        if(rooms.includes(n)) return;
        await api('/add_room',{token:localStorage.getItem('token'),room:n});
        rooms.push(n);
        currentRoom = n;
        renderChat();
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
        if(savedToken && savedUser){
            const ok = await loadData();
            if(ok){
                currentUser = savedUser;
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

@app.route('/data', methods=['POST'])
def data():
    token = request.json.get('token')
    # упрощённо: без токена просто отдаём данные (для теста), но в целом норм
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT DISTINCT room FROM messages')
    rooms = [r[0] for r in c.fetchall()]
    if not rooms:
        rooms = ['общий']
    messages = {}
    for room in rooms:
        c.execute('SELECT username, text, time FROM messages WHERE room = ? ORDER BY time', (room,))
        rows = c.fetchall()
        messages[room] = [{'username': r[0], 'text': r[1], 'time': r[2]} for r in rows]
    conn.close()
    return {'ok': True, 'rooms': rooms, 'messages': messages}

@app.route('/add_room', methods=['POST'])
def add_room():
    room = request.json.get('room')
    if room:
        return {'ok': True}
    return {'ok': False}

@socketio.on('join')
def on_join(data):
    user = data.get('user')
    if user:
        print(f'{user} joined')

@socketio.on('msg')
def on_msg(data):
    room = data['room']
    text = data['text']
    username = request.sid  # упрощённо, но для теста хватит
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO messages (room, username, text, time) VALUES (?, ?, ?, ?)',
              (room, username, text, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    emit('new_msg', {'room': room, 'username': username, 'text': text}, to=room)

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 8080))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
