from flask import Flask, request, render_template_string
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash

import sqlite3
import secrets
import os

from datetime import datetime, timedelta

# =========================================
# APP
# =========================================

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get(
    'SECRET_KEY',
    secrets.token_hex(32)
)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading"
)

# =========================================
# DB
# =========================================

os.makedirs('./data', exist_ok=True)

DB_PATH = './data/shadow_chat.db'

connected_users = {}


def init_db():

    conn = sqlite3.connect(DB_PATH)

    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS users(
        username TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        created_at TEXT
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS sessions(
        token TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        expires_at TEXT
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room TEXT NOT NULL,
        username TEXT NOT NULL,
        text TEXT NOT NULL,
        timestamp TEXT,
        read_status TEXT DEFAULT 'sent'
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS user_rooms(
        username TEXT NOT NULL,
        room TEXT NOT NULL,
        last_read TEXT,
        PRIMARY KEY(username, room)
    )
    ''')

    conn.commit()
    conn.close()


# =========================================
# HELPERS
# =========================================

def db():

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    return conn


def get_username_by_token(token):

    if not token:
        return None

    conn = db()

    c = conn.cursor()

    c.execute('''
    SELECT username
    FROM sessions
    WHERE token = ?
    AND expires_at > ?
    ''', (
        token,
        datetime.now().isoformat()
    ))

    row = c.fetchone()

    conn.close()

    if not row:
        return None

    return row['username']


# =========================================
# HTML
# =========================================

HTML = """
<!DOCTYPE html>
<html lang="ru">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

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
    font-family:Arial;
    height:100vh;
}

.auth{
    width:340px;
    margin:100px auto;
    background:#1e1f2c;
    padding:24px;
    border-radius:24px;
}

.auth input{
    width:100%;
    padding:12px;
    margin-bottom:12px;
    border:none;
    border-radius:12px;
    background:#0f0f14;
    color:white;
}

.auth button{
    width:100%;
    padding:12px;
    border:none;
    border-radius:12px;
    background:#6366f1;
    color:white;
    cursor:pointer;
    margin-bottom:8px;
}

.chat{
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

.sidebar-top{
    padding:16px;
    border-bottom:1px solid #2d2f3e;
}

.sidebar-top button{
    width:100%;
    padding:10px;
    border:none;
    border-radius:12px;
    background:#6366f1;
    color:white;
    cursor:pointer;
}

.rooms{
    flex:1;
    overflow:auto;
}

.room{
    padding:14px;
    cursor:pointer;
    border-bottom:1px solid #2d2f3e;
}

.room.active{
    background:#6366f1;
}

.main{
    flex:1;
    display:flex;
    flex-direction:column;
}

.header{
    padding:16px;
    border-bottom:1px solid #2d2f3e;
}

.messages{
    flex:1;
    overflow:auto;
    padding:16px;
    display:flex;
    flex-direction:column;
    gap:12px;
}

.message{
    max-width:75%;
}

.my{
    align-self:flex-end;
}

.bubble{
    background:#2d2f3e;
    padding:12px;
    border-radius:16px;
    word-break:break-word;
}

.my .bubble{
    background:#6366f1;
}

.input{
    display:flex;
    gap:8px;
    padding:16px;
    border-top:1px solid #2d2f3e;
}

.input input{
    flex:1;
    padding:12px;
    border:none;
    border-radius:12px;
    background:#0f0f14;
    color:white;
}

.input button{
    border:none;
    border-radius:12px;
    padding:0 20px;
    background:#6366f1;
    color:white;
    cursor:pointer;
}

.status{
    margin-top:12px;
    text-align:center;
    color:#aaa;
}

</style>

</head>

<body>

<div id="app"></div>

<script>

let socket = null;

let currentUser = null;
let currentRoom = null;

let rooms = [];
let messages = {};

function escapeHtml(str){

    return String(str)
        .replace(/&/g,'&amp;')
        .replace(/</g,'&lt;')
        .replace(/>/g,'&gt;');
}

async function api(url,data){

    const res = await fetch(url,{
        method:'POST',
        headers:{
            'Content-Type':'application/json'
        },
        body:JSON.stringify(data)
    });

    return await res.json();
}

function renderAuth(){

    document.getElementById('app').innerHTML = `
        <div class="auth">

            <input
                id="username"
                placeholder="Логин"
            >

            <input
                id="password"
                type="password"
                placeholder="Пароль"
            >

            <button id="loginBtn">
                Войти
            </button>

            <button id="registerBtn">
                Регистрация
            </button>

            <div
                class="status"
                id="status"
            ></div>

        </div>
    `;

    document
        .getElementById('loginBtn')
        .onclick = login;

    document
        .getElementById('registerBtn')
        .onclick = register;
}

function renderChat(){

    document.getElementById('app').innerHTML = `
        <div class="chat">

            <div class="sidebar">

                <div class="sidebar-top">

                    <button id="createRoomBtn">
                        + Новый чат
                    </button>

                </div>

                <div
                    class="rooms"
                    id="rooms"
                ></div>

            </div>

            <div class="main">

                <div class="header">
                    ${currentRoom || 'Выберите чат'}
                </div>

                <div
                    class="messages"
                    id="messages"
                ></div>

                <div
                    class="input"
                    style="
                        display:
                        ${currentRoom ? 'flex' : 'none'}
                    "
                >

                    <input
                        id="messageInput"
                        placeholder="Сообщение"
                    >

                    <button id="sendBtn">
                        ➤
                    </button>

                </div>

            </div>

        </div>
    `;

    renderRooms();
    renderMessages();

    document
        .getElementById('createRoomBtn')
        .onclick = createRoom;

    const sendBtn =
        document.getElementById('sendBtn');

    if(sendBtn){

        sendBtn.onclick = sendMessage;
    }

    const input =
        document.getElementById('messageInput');

    if(input){

        input.addEventListener(
            'keypress',
            (e)=>{

                if(e.key === 'Enter'){
                    sendMessage();
                }
            }
        );
    }
}

function renderRooms(){

    const el =
        document.getElementById('rooms');

    if(!el) return;

    el.innerHTML = '';

    rooms.forEach(room=>{

        const div =
            document.createElement('div');

        div.className =
            'room' +
            (
                room === currentRoom
                ? ' active'
                : ''
            );

        div.innerText = room;

        div.onclick = ()=>{

            switchRoom(room);
        };

        el.appendChild(div);
    });
}

function renderMessages(){

    const el =
        document.getElementById('messages');

    if(!el) return;

    const msgs =
        messages[currentRoom] || [];

    el.innerHTML = '';

    msgs.forEach(msg=>{

        const div =
            document.createElement('div');

        div.className =
            'message' +
            (
                msg.username === currentUser
                ? ' my'
                : ''
            );

        div.innerHTML = `
            <div class="bubble">

                ${
                    msg.username !== currentUser
                    ? '<b>' +
                      escapeHtml(msg.username) +
                      '</b><br>'
                    : ''
                }

                ${escapeHtml(msg.text)}

            </div>
        `;

        el.appendChild(div);
    });

    el.scrollTop = el.scrollHeight;
}

async function register(){

    const username =
        document
            .getElementById('username')
            .value
            .trim();

    const password =
        document
            .getElementById('password')
            .value
            .trim();

    const result = await api(
        '/register',
        {
            username,
            password
        }
    );

    document
        .getElementById('status')
        .innerText =
            result.success
            ? 'Успешно'
            : result.error;
}

async function login(){

    const username =
        document
            .getElementById('username')
            .value
            .trim();

    const password =
        document
            .getElementById('password')
            .value
            .trim();

    const result = await api(
        '/login',
        {
            username,
            password
        }
    );

    if(!result.success){

        document
            .getElementById('status')
            .innerText = result.error;

        return;
    }

    localStorage.setItem(
        'shadow_token',
        result.token
    );

    localStorage.setItem(
        'shadow_username',
        username
    );

    currentUser = username;

    await loadData();

    connectSocket();

    renderChat();
}

async function loadData(){

    const token =
        localStorage.getItem(
            'shadow_token'
        );

    const result = await api(
        '/user_data',
        {token}
    );

    if(result.success){

        rooms = result.rooms || {};

        messages =
            result.messages || {};
    }
}

function connectSocket(){

    socket = io();

    socket.on(
        'connect',
        ()=>{

            socket.emit(
                'register',
                currentUser
            );
        }
    );

    socket.on(
        'new_message',
        (data)=>{

            if(!messages[data.room]){

                messages[data.room] = [];
            }

            messages[data.room]
                .push(data);

            renderMessages();
        }
    );
}

function switchRoom(room){

    currentRoom = room;

    socket.emit(
        'join_room',
        {room}
    );

    renderChat();
}

async function createRoom(){

    const room =
        prompt('Название чата');

    if(!room) return;

    const clean = room.trim();

    if(!clean) return;

    if(rooms.includes(clean)){
        return;
    }

    rooms.push(clean);

    await api(
        '/add_room',
        {
            token:
                localStorage.getItem(
                    'shadow_token'
                ),
            room:clean
        }
    );

    renderChat();
}

function sendMessage(){

    const input =
        document
            .getElementById(
                'messageInput'
            );

    if(!input) return;

    const text =
        input.value.trim();

    if(!text) return;

    socket.emit(
        'message',
        {
            room:currentRoom,
            text
        }
    );

    input.value = '';
}

async function autoLogin(){

    const token =
        localStorage.getItem(
            'shadow_token'
        );

    const username =
        localStorage.getItem(
            'shadow_username'
        );

    if(!token || !username){

        renderAuth();

        return;
    }

    const result = await api(
        '/auto_login',
        {token}
    );

    if(!result.success){

        localStorage.clear();

        renderAuth();

        return;
    }

    currentUser = username;

    await loadData();

    connectSocket();

    renderChat();
}

autoLogin();

</script>

</body>

</html>
"""

# =========================================
# ROUTES
# =========================================

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

    conn = db()
    c = conn.cursor()

    c.execute('''
    SELECT username
    FROM users
    WHERE username = ?
    ''', (username,))

    if c.fetchone():

        conn.close()

        return {
            'success': False,
            'error': 'Пользователь уже существует'
        }

    password_hash = generate_password_hash(password)

    c.execute('''
    INSERT INTO users(
        username,
        password_hash,
        created_at
    )
    VALUES(?,?,?)
    ''', (
        username,
        password_hash,
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()

    return {'success': True}


@app.route('/login', methods=['POST'])
def login():

    data = request.json

    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    conn = db()
    c = conn.cursor()

    c.execute('''
    SELECT password_hash
    FROM users
    WHERE username = ?
    ''', (username,))

    row = c.fetchone()

    conn.close()

    if not row:

        return {
            'success': False,
            'error': 'Неверный логин'
        }

    if not check_password_hash(
        row['password_hash'],
        password
    ):

        return {
            'success': False,
            'error': 'Неверный пароль'
        }

    token = secrets.token_urlsafe(32)

    expires =
        datetime.now() + timedelta(days=365)

    conn = db()
    c = conn.cursor()

    c.execute('''
    INSERT OR REPLACE INTO sessions(
        token,
        username,
        expires_at
    )
    VALUES(?,?,?)
    ''', (
        token,
        username,
        expires.isoformat()
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

    username =
        get_username_by_token(token)

    if not username:

        return {'success': False}

    return {
        'success': True,
        'username': username
    }


@app.route('/add_room', methods=['POST'])
def add_room():

    data = request.json

    token = data.get('token')
    room = data.get('room')

    username =
        get_username_by_token(token)

    if not username:

        return {'success': False}

    conn = db()
    c = conn.cursor()

    c.execute('''
    INSERT OR IGNORE INTO user_rooms(
        username,
        room,
        last_read
    )
    VALUES(?,?,?)
    ''', (
        username,
        room,
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()

    return {'success': True}


@app.route('/user_data', methods=['POST'])
def user_data():

    data = request.json

    token = data.get('token')

    username =
        get_username_by_token(token)

    if not username:

        return {'success': False}

    conn = db()
    c = conn.cursor()

    c.execute('''
    SELECT room
    FROM user_rooms
    WHERE username = ?
    ''', (username,))

    room_rows = c.fetchall()

    rooms = []

    for row in room_rows:

        rooms.append(row['room'])

    messages = {}

    for room in rooms:

        c.execute('''
        SELECT *
        FROM messages
        WHERE room = ?
        ORDER BY timestamp
        ''', (room,))

        rows = c.fetchall()

        messages[room] = []

        for r in rows:

            messages[room].append({
                'username': r['username'],
                'text': r['text'],
                'timestamp': r['timestamp'],
                'read_status': r['read_status']
            })

    conn.close()

    return {
        'success': True,
        'rooms': rooms,
        'messages': messages
    }


# =========================================
# SOCKETS
# =========================================

@socketio.on('connect')
def on_connect():

    print('socket connected')


@socketio.on('disconnect')
def on_disconnect():

    connected_users.pop(
        request.sid,
        None
    )

    print('socket disconnected')


@socketio.on('register')
def socket_register(username):

    connected_users[
        request.sid
    ] = username

    print(username, 'registered')


@socketio.on('join_room')
def socket_join(data):

    room = data['room']

    join_room(room)

    print('joined', room)


@socketio.on('leave_room')
def socket_leave(data):

    room = data['room']

    leave_room(room)


@socketio.on('message')
def socket_message(data):

    room = data['room']
    text = data['text']

    username =
        connected_users.get(
            request.sid
        )

    if not username:
        return

    timestamp =
        datetime.now().isoformat()

    conn = db()
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

    emit(
        'new_message',
        {
            'room': room,
            'username': username,
            'text': text,
            'timestamp': timestamp,
            'read_status': 'sent'
        },
        to=room
    )


# =========================================
# START
# =========================================

if __name__ == '__main__':

    init_db()

    socketio.run(
        app,
        host='0.0.0.0',
        port=8080,
        debug=True
    )
