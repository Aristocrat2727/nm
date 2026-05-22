from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# Хранилище сообщений: {room_code: [{"text": "...", "user": "..."}]}
messages = {}

HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <title>Shadow Chat — комнаты</title>
    <script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{background:#0f0f14;font-family:system-ui;height:100vh;display:flex;justify-content:center;align-items:center;padding:20px}
        .container{background:#1e1f2c;border-radius:40px;width:100%;max-width:600px;height:90%;display:flex;flex-direction:column;overflow:hidden}
        .header{background:#1e1f2c;padding:16px;border-bottom:1px solid #2d2f3e;text-align:center}
        .header h1{color:#f1f5f9;font-size:1.3rem}
        .room-panel{display:flex;gap:8px;padding:12px;background:#0f0f14;border-bottom:1px solid #2d2f3e}
        .room-panel input{flex:1;background:#1e1f2c;border:1px solid #2d2f3e;border-radius:40px;padding:10px 16px;color:white;outline:none}
        .room-panel button{background:#6366f1;border:none;border-radius:40px;padding:0 20px;color:white;font-weight:bold;cursor:pointer}
        .messages{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px}
        .message{display:flex;gap:10px}
        .my-message{justify-content:flex-end}
        .bubble{max-width:70%;padding:10px 14px;border-radius:20px;font-size:14px;line-height:1.4}
        .my-message .bubble{background:#6366f1;color:white}
        .other-message .bubble{background:#2d2f3e;color:#e2e8f0}
        .input-area{display:flex;gap:8px;padding:16px;border-top:1px solid #2d2f3e;background:#0f0f14}
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
    <div class="room-panel">
        <input type="text" id="roomCode" placeholder="Код комнаты (например, superchat)">
        <button id="joinBtn">Войти / Создать</button>
    </div>
    <div class="messages" id="messages"></div>
    <div class="input-area" style="display:none">
        <input type="text" id="messageInput" placeholder="Напиши сообщение..." autocomplete="off">
        <button id="sendBtn">➤</button>
    </div>
    <div class="status" id="status">Введи код комнаты</div>
</div>
<script>
    let socket = null;
    let currentRoom = null;
    const messagesDiv = document.getElementById('messages');
    const roomCodeInput = document.getElementById('roomCode');
    const joinBtn = document.getElementById('joinBtn');
    const inputArea = document.querySelector('.input-area');
    const messageInput = document.getElementById('messageInput');
    const sendBtn = document.getElementById('sendBtn');
    const statusSpan = document.getElementById('status');

    function addMessage(text, isMy, username = '') {
        const div = document.createElement('div');
        div.className = `message ${isMy ? 'my-message' : 'other-message'}`;
        const bubble = document.createElement('div');
        bubble.className = 'bubble';
        if (!isMy && username) bubble.innerHTML = `<b>${username}</b><br>${text}`;
        else bubble.innerText = text;
        div.appendChild(bubble);
        messagesDiv.appendChild(div);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }

    function loadHistory(history) {
        messagesDiv.innerHTML = '';
        for (let msg of history) {
            const isMy = (msg.user === localStorage.getItem('shadow_username'));
            addMessage(msg.text, isMy, isMy ? '' : msg.user);
        }
    }

    joinBtn.onclick = () => {
        const room = roomCodeInput.value.trim();
        if (!room) return;
        if (socket) socket.disconnect();
        
        const username = localStorage.getItem('shadow_username') || `User${Math.floor(Math.random()*1000)}`;
        localStorage.setItem('shadow_username', username);
        
        socket = io();
        socket.emit('join', { room, username });
        currentRoom = room;
        
        socket.on('history', (history) => {
            loadHistory(history);
            inputArea.style.display = 'flex';
            statusSpan.innerText = `✅ Комната: ${room}. Можешь писать.`;
            messageInput.focus();
        });
        
        socket.on('new_message', (data) => {
            const isMy = (data.user === username);
            addMessage(data.text, isMy, isMy ? '' : data.user);
        });
        
        socket.on('error', (msg) => {
            statusSpan.innerText = `❌ ${msg}`;
        });
        
        socket.on('disconnect', () => {
            statusSpan.innerText = 'Потеряно соединение. Перезагрузи страницу.';
        });
    };
    
    sendBtn.onclick = () => {
        const text = messageInput.value.trim();
        if (text && socket && currentRoom) {
            socket.emit('message', { room: currentRoom, text });
            messageInput.value = '';
        }
    };
    
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendBtn.click();
    });
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML)

@socketio.on('join')
def handle_join(data):
    room = data['room']
    username = data['username']
    join_room(room)
    
    # Отправляем историю этому пользователю
    room_history = messages.get(room, [])
    emit('history', room_history)
    
    # Уведомляем остальных (опционально)
    emit('new_message', {'user': 'system', 'text': f'{username} присоединился к чату'}, to=room, skip_sid=request.sid)

@socketio.on('message')
def handle_message(data):
    room = data['room']
    text = data['text']
    username = request.sid  # упрощённо, но можно передавать с клиента
    
    # Сохраняем сообщение в историю
    if room not in messages:
        messages[room] = []
    messages[room].append({'text': text, 'user': username})
    
    emit('new_message', {'user': username, 'text': text}, to=room)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
