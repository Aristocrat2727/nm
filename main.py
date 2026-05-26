import os
import hashlib
import secrets
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit, join_room
from flask_cors import CORS
from supabase import create_client

SUPABASE_URL = "https://bjqgguylmkgvqxqblsni.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJqcWdndXlsbWtndnF4cWJsc25pIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk2MjUzOTgsImV4cCI6MjA5NTIwMTM5OH0.-oFtd1CPQfGuXQK1AEiCkYWmGrb5IEvrfGUrpa6he2o"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'
CORS(app, origins=["*"])

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

@app.route('/')
def index():
    return jsonify({'status': 'ok'})

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'success': False, 'error': 'Введите логин и пароль'})
    
    existing = supabase.table('users').select('username').eq('username', username).execute()
    if existing.data:
        return jsonify({'success': False, 'error': 'Пользователь уже существует'})
    
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    supabase.table('users').insert({'username': username, 'password_hash': password_hash, 'created_at': datetime.now().isoformat()}).execute()
    return jsonify({'success': True})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'success': False, 'error': 'Введите логин и пароль'})
    
    res = supabase.table('users').select('password_hash').eq('username', username).execute()
    if not res.data or res.data[0]['password_hash'] != hashlib.sha256(password.encode()).hexdigest():
        return jsonify({'success': False, 'error': 'Неверный логин или пароль'})
    
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(days=365*50)).isoformat()
    supabase.table('sessions').upsert({'token': token, 'username': username, 'expires_at': expires_at}).execute()
    return jsonify({'success': True, 'token': token})

@app.route('/auto_login', methods=['POST'])
def auto_login():
    data = request.json
    token = data.get('token')
    if not token:
        return jsonify({'success': False, 'error': 'Нет токена'})
    
    res = supabase.table('sessions').select('username, expires_at').eq('token', token).execute()
    if not res.data:
        return jsonify({'success': False, 'error': 'Токен не найден'})
    
    row = res.data[0]
    if datetime.now() > datetime.fromisoformat(row['expires_at'].replace('Z', '+00:00')):
        return jsonify({'success': False, 'error': 'Токен истёк'})
    return jsonify({'success': True, 'username': row['username']})

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
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
