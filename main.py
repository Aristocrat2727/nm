from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash

import os
import sqlite3
import secrets

from datetime import datetime, timedelta

# =========================
# APP
# =========================

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get(
    'SECRET_KEY',
    secrets.token_hex(32)
)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    ping_timeout=60,
    ping_interval=25
)

# =========================
# DB
# =========================

os.makedirs('/app/data', exist_ok=True)

DB_PATH = '/app/data/shadow_chat.db'

connected_users = {}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room TEXT NOT NULL,
        username TEXT NOT NULL,
        text TEXT NOT NULL,
        timestamp TIMESTAMP,
        read_status TEXT DEFAULT 'sent'
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        expires_at TIMESTAMP
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS user_rooms (
        username TEXT NOT NULL,
        room TEXT NOT NULL,
        last_read TIMESTAMP,
        PRIMARY KEY (username, room)
    )
    ''')

    conn.commit()
    conn.close()


# =========================
# HTML
# =========================

HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Shadow Chat</title>

<script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>

<style>
*{
    margin:0;
    padding:0;
    box-sizing:border-box;
}

body{
    background:#0f0f14;
    color:white;
    font-family:system-ui;
    height:100vh;
}

.auth-panel{
    width:350px;
    margin:100px auto;
    background:#1e1f2c;
    border-radius:24px;
    padding:24px;
}

.auth-panel input{
    width:100%;
    margin-bottom:12px;
    padding:12px;
    border:none;
    border-radius:12px;
    background:#0f0f14;
    color:white;
}

.auth-panel button{
    width:100%;
    padding:12px;
    border:none;
    border-radius:12px;
    background:#6366f1;
    color:white;
    cursor:pointer;
    margin-top:8px;
}

.chat-container{
    display:flex;
    height:100vh;
}

.sidebar{
    width:280px;
    background:#15161f;
    border-right:1px solid #2d2f3e;
    display:flex;
    flex-direction:column;
}

.sidebar-header{
    padding:16px;
    border-bottom:1px solid #2d2f3e;
}

.rooms-list{
    flex:1;
    overflow-y:auto;
}

.room-item{
    padding:14px;
    cursor:pointer;
    border-bottom:1px solid #2d2f3e;
}

.room-item.active{
    background:#6366f1;
}

.chat-area{
    flex:1;
    display:flex;
    flex-direction:column;
}

.chat-header{
    padding:16px;
    border-bottom:1px solid #2d2f3e;
}

.messages{
    flex:1;
    overflow-y:auto;
    padding:16px;
    display:flex;
    flex-direction:column;
    gap:12px;
}

.message{
    max-width:75%;
}

.my-message{
    align-self:flex-end;
}

.bubble{
    background:#2d2f3e;
    padding:12px;
    border-radius:18px;
}

.my-message .bubble{
    background:#6366f1;
}

.message-info{
    font-size:10px;
    margin-top:4px;
    opacity:0.7;
    text-align:right;
}

.input-area{
    display:flex;
    gap:8px;
    padding:16px;
    border-top:1px solid #2d2f3e;
}

.input-area input{
    flex:1;
    padding:12px;
    border:none;
    border-radius:12px;
    background:#0f0f14;
    color:white;
}

.input-area button{
    border:none;
    border-radius:12px;
    padding:0 20px;
    background:#6366f1;
    color:white;
    cursor:pointer;
}

.unread{
    background:red;
    border-radius:20px;
    padding:2px 8px;
    font-size:11px;
    margin-left:8px;
}
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
let unreadCount = {};

const savedToken = localStorage.getItem('shadow_token');
const savedUsername = localStorage.getItem('shadow_username');

if (Notification.permission === 'default') {
    Notification.requestPermission();
}

function escapeHtml(str){
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

async function apiRequest(endpoint, data){
    const res = await fetch(endpoint,{
        method:'POST',
        headers:{
            'Content-Type':'application/json'
        },
        body:JSON.stringify(data)
    });

    return res.json();
}

function renderAuth(){

    document.getElementById('root').innerHTML = `
        <div class="auth-panel">

            <input id="username" placeholder="Логин">
            <input id="password" type="password" placeholder="Пароль">

            <button onclick="login()">Войти</button>
            <button onclick="register()">Регистрация</button>

            <div id="authStatus" style="margin-top:12px;text-align:center;"></div>

        </div>
    `;
}

function renderChat(){

    document.getElementById('root').innerHTML = `
        <div class="chat-container">

            <div class="sidebar">

                <div class="sidebar-header">
                    <button onclick="createRoom()">+ Новый чат</button>
                </div>

                <div class="rooms-list" id="roomsList"></div>

            </div>

            <div class="chat-area">

                <div class="chat-header">
                    <h3>${currentRoom || 'Выберите чат'}</h3>
                </div>

                <div class="messages" id="messages"></div>

                <div class="input-area" style="display:${currentRoom ? 'flex' : 'none'}">

                    <input id="messageInput" placeholder="Сообщение">

                    <button onclick="sendMessage()">➤</button>

                </div>

            </div>

        </div>
    `;

    renderRooms();
    renderMessages();

    const input = document.getElementById('messageInput');

    if(input){
        input.addEventListener('keypress',(e)=>{
            if(e.key === 'Enter'){
                sendMessage();
            }
        });
    }
}

function renderRooms(){

    const el = document.getElementById('roomsList');

    if(!el) return;

    el.innerHTML = rooms.map(room => `
        <div
            class="room-item ${currentRoom === room ? 'active' : ''}"
            onclick="switchRoom('${room}')"
        >
            ${escapeHtml(room)}

            ${
                unreadCount[room]
                ? `<span class="unread">${unreadCount[room]}</span>`
                : ''
            }
        </div>
    `).join('');
}

function renderMessages(){

    const el = document.getElementById('messages');

    if(!el) return;

    const msgs = messages[currentRoom] || [];

    el.innerHTML = msgs.map(msg => `
        <div class="message ${msg.username === currentUser ? 'my-message' : ''}">
            <div class="bubble">

                ${
                    msg.username !== currentUser
                    ? `<b>${escapeHtml(msg.username)}</b><br>`
                    : ''
                }

                ${escapeHtml(msg.text)}

                <div class="message-info">
                    ${
                        msg.username === currentUser
                        ? (msg.read_status === 'read' ? '✓✓' : '✓')
                        : ''
                    }
                </div>

            </div>
        </div>
    `).join('');

    el.scrollTop = el.scrollHeight;
}

async function register(){

    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value.trim();

    const result = await apiRequest('/register',{
        username,
        password
    });

    document.getElementById('authStatus').innerText =
        result.success
        ? 'Регистрация успешна'
        : result.error;
}

async function login(){

    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value.trim();

    const result = await apiRequest('/login',{
        username,
        password
    });

    if(!result.success){

        document.getElementById('authStatus').innerText = result.error;

        return;
    }

    localStorage.setItem('shadow_token', result.token);
    localStorage.setItem('shadow_username', username);

    currentUser = username;

    await loadData();

    connectSocket();

    renderChat();
}

async function loadData(){

    const token = localStorage.getItem('shadow_token');

    const result = await apiRequest('/user_data',{
        token
    });

    if(result.success){

        rooms = result.rooms;
        messages = result.messages;
        unreadCount = result.unreadCount;
    }
}

function connectSocket(){

    if(socket){
        socket.disconnect();
    }

    socket = io();

    socket.on('connect',()=>{

        socket.emit('register', currentUser);

    });

    socket.on('new_message',(data)=>{

        if(!messages[data.room]){
            messages[data.room] = [];
        }

        messages[data.room].push(data);

        if(data.room !== currentRoom){

            unreadCount[data.room] =
                (unreadCount[data.room] || 0) + 1;

            if(Notification.permission === 'granted'){

                new Notification('Новое сообщение',{
                    body:`${data.username}: ${data.text}`
                });
            }

            renderRooms();
        }

        if(data.room === currentRoom){

            renderMessages();

            socket.emit('mark_read',{
                room:data.room
            });
        }
    });

    socket.on('read_receipt',(data)=>{

        const room = data.room;

        if(messages[room]){

            messages[room].forEach(msg=>{

                if(
                    msg.username === currentUser &&
                    msg.read_status !== 'read'
                ){
                    msg.read_status = 'read';
                }
            });
        }

        renderMessages();
    });
}

function switchRoom(room){

    currentRoom = room;

    unreadCount[room] = 0;

    socket.emit('join_room',{
        room
    });

    socket.emit('mark_read',{
        room
    });

    renderChat();
}

async function createRoom(){

    const room = prompt('Название чата');

    if(!room) return;

    const clean = room.trim();

    if(!clean) return;

    if(rooms.includes(clean)){
        alert('Чат уже существует');
        return;
    }

    rooms.push(clean);

    await apiRequest('/add_room',{
        token:localStorage.getItem('shadow_token'),
        room:clean
    });

    switchRoom(clean);
}

function sendMessage(){

    const input = document.getElementById('messageInput');

    const text = input.value.trim();

    if(!text || !currentRoom){
        return;
    }

    socket.emit('message',{
        room:currentRoom,
        text
    });

    input.value = '';
}

async function autoLogin(){

    if(!savedToken){

        renderAuth();

        return;
    }

    const result = await apiRequest('/auto_login',{
        token:savedToken
    });

    if(!result.success){

        localStorage.removeItem('shadow_token');
        localStorage.removeItem('shadow_username');

        renderAuth();

        return;
    }

    currentUser = savedUsername;

    await loadData();

    connectSocket();

    renderChat();
}

autoLogin();

</script>

</body>
</html>
"""

# =========================
# HELPERS
# =========================


def get_username_by_token(token):

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
    SELECT username
    FROM sessions
    WHERE token = ?
    AND expires_at > ?
    ''', (token, datetime.now()))

    row = c.fetchone()

    conn.close()

    if not row:
        return None

    return row[0]


# =========================
# ROUTES
# =========================

@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/register', methods=['POST'])
def register():

    data = request.json

    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return {
            'success': False,
            'error': 'Введите логин и пароль'
        }

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        'SELECT username FROM users WHERE username = ?',
        (username,)
    )

    if c.fetchone():

        conn.close()

        return {
            'success': False,
            'error': 'Пользователь уже существует'
        }

    password_hash = generate_password_hash(password)

    c.execute('''
    INSERT INTO users(username, password_hash, created_at)
    VALUES(?,?,?)
    ''', (
        username,
        password_hash,
        datetime.now()
    ))

    conn.commit()
    conn.close()

    return {'success': True}


@app.route('/login', methods=['POST'])
def login():

    data = request.json

    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
    SELECT password_hash
    FROM users
    WHERE username = ?
    ''', (username,))

    row = c.fetchone()

    conn.close()

    if not row or not check_password_hash(row[0], password):

        return {
            'success': False,
            'error': 'Неверный логин или пароль'
        }

    token = secrets.token_urlsafe(32)

    expires_at = datetime.now() + timedelta(days=365)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
    INSERT OR REPLACE INTO sessions(token, username, expires_at)
    VALUES(?,?,?)
    ''', (
        token,
        username,
        expires_at
    ))

    conn.commit()
    conn.close()

    return {
        'success': True,
        'token': token
    }


@app.route('/auto_login', methods=['POST'])
def auto_login():

    data = request.json

    token = data.get('token')

    username = get_username_by_token(token)

    if not username:

        return {
            'success': False
        }

    return {
        'success': True,
        'username': username
    }


@app.route('/add_room', methods=['POST'])
def add_room():

    data = request.json

    token = data.get('token')
    room = data.get('room')

    username = get_username_by_token(token)

    if not username:

        return {'success': False}

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
    INSERT OR IGNORE INTO user_rooms(username, room, last_read)
    VALUES(?,?,?)
    ''', (
        username,
        room,
        datetime.now()
    ))

    conn.commit()
    conn.close()

    return {'success': True}


@app.route('/user_data', methods=['POST'])
def user_data():

    data = request.json

    token = data.get('token')

    username = get_username_by_token(token)

    if not username:

        return {'success': False}

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
    SELECT room
    FROM user_rooms
    WHERE username = ?
    ''', (username,))

    rooms = [x[0] for x in c.fetchall()]

    messages_dict = {}
    unread = {}

    for room in rooms:

        c.execute('''
        SELECT username, text, timestamp, read_status
        FROM messages
        WHERE room = ?
        ORDER BY timestamp
        ''', (room,))

        rows = c.fetchall()

        msgs = []

        for r in rows:

            msgs.append({
                'username': r[0],
                'text': r[1],
                'timestamp': r[2],
                'read_status': r[3]
            })

        messages_dict[room] = msgs

        c.execute('''
        SELECT last_read
        FROM user_rooms
        WHERE username = ?
        AND room = ?
        ''', (
            username,
            room
        ))

        last_read_row = c.fetchone()

        last_read = last_read_row[0] if last_read_row else None

        if last_read:

            unread[room] = sum(
                1 for m in msgs
                if (
                    m['username'] != username and
                    m['timestamp'] > last_read
                )
            )

        else:

            unread[room] = sum(
                1 for m in msgs
                if m['username'] != username
            )

    conn.close()

    return {
        'success': True,
        'rooms': rooms,
        'messages': messages_dict,
        'unreadCount': unread
    }


# =========================
# SOCKETS
# =========================

@socketio.on('register')
def socket_register(username):

    connected_users[request.sid] = username

    print(f'{username} connected')


@socketio.on('disconnect')
def socket_disconnect():

    connected_users.pop(request.sid, None)


@socketio.on('join_room')
def socket_join(data):

    room = data['room']

    join_room(room)


@socketio.on('leave_room')
def socket_leave(data):

    room = data['room']

    leave_room(room)


@socketio.on('message')
def socket_message(data):

    room = data['room']
    text = data['text']

    username = connected_users.get(request.sid)

    if not username:
        return

    timestamp = datetime.now()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
    INSERT INTO messages(
        room,
        username,
        text,
        timestamp,
        read_status
    )
    VALUES(?,?,?,?,?)
    ''', (
        room,
        username,
        text,
        timestamp,
        'sent'
    ))

    conn.commit()
    conn.close()

    emit('new_message', {
        'room': room,
        'username': username,
        'text': text,
        'timestamp': str(timestamp),
        'read_status': 'sent'
    }, to=room)


@socketio.on('mark_read')
def socket_mark_read(data):

    room = data['room']

    username = connected_users.get(request.sid)

    if not username:
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
    INSERT OR REPLACE INTO user_rooms(
        username,
        room,
        last_read
    )
    VALUES(?,?,?)
    ''', (
        username,
        room,
        datetime.now()
    ))

    c.execute('''
    UPDATE messages
    SET read_status = 'read'
    WHERE room = ?
    AND username != ?
    ''', (
        room,
        username
    ))

    conn.commit()
    conn.close()

    emit('read_receipt', {
        'room': room,
        'username': username
    }, to=room)


# =========================
# RUN
# =========================

if __name__ == '__main__':

    init_db()

    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 8080))
    )
