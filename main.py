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

def generate_token(username):
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(days=365*10)).isoformat()
    supabase.table('sessions').delete().eq('username', username).execute()
    supabase.table('sessions').insert({
        'token': token,
        'username': username,
        'expires_at': expires_at
    }).execute()
    return token

def verify_token(token):
    if not token:
        return None
    res = supabase.table('sessions').select('username, expires_at').eq('token', token).execute()
    if not res.data or len(res.data) == 0:
        return None
    row = res.data[0]
    expires_at = row['expires_at'].replace('Z', '+00:00')
    if datetime.now() > datetime.fromisoformat(expires_at):
        supabase.table('sessions').delete().eq('token', token).execute()
        return None
    return row['username']

@app.route('/')
def index():
    return jsonify({'status': 'ok', 'message': 'Shadow Chat API'})

@app.route('/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        if not username or not password:
            return jsonify({'success': False, 'error': 'Введите логин и пароль'})
        
        existing = supabase.table('users').select('username').eq('username', username).execute()
        if existing.data and len(existing.data) > 0:
            return jsonify({'success': False, 'error': 'Пользователь уже существует'})
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        supabase.table('users').insert({
            'username': username,
            'password_hash': password_hash,
            'created_at': datetime.now().isoformat()
        }).execute()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        if not username or not password:
            return jsonify({'success': False, 'error': 'Введите логин и пароль'})
        
        res = supabase.table('users').select('password_hash').eq('username', username).execute()
        if not res.data or len(res.data) == 0:
            return jsonify({'success': False, 'error': 'Неверный логин или пароль'})
        
        if res.data[0]['password_hash'] != hashlib.sha256(password.encode()).hexdigest():
            return jsonify({'success': False, 'error': 'Неверный логин или пароль'})
        
        token = generate_token(username)
        return jsonify({'success': True, 'token': token, 'username': username})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/auto_login', methods=['POST', 'OPTIONS'])
def auto_login():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        data = request.json
        token = data.get('token')
        username = verify_token(token)
        if username:
            return jsonify({'success': True, 'username': username})
        return jsonify({'success': False, 'error': 'Токен недействителен'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@socketio.on('join')
def handle_join(data):
    try:
        room = data['room']
        username = data['username']
        join_room(room)
        
        res = supabase.table('messages').select('*').eq('room', room).order('timestamp').execute()
        history = []
        if res.data:
            for r in res.data:
                history.append({
                    'username': r['username'],
                    'text': r.get('text', ''),
                    'media_url': r.get('media_url', ''),
                    'media_type': r.get('media_type', ''),
                    'timestamp': r['timestamp'],
                    'read_status': r['read_status']
                })
        
        supabase.table('messages').update({'read_status': 'read'}).eq('room', room).neq('username', username).execute()
        emit('history', history)
        emit('read_receipt', {'room': room}, to=room)
    except Exception as e:
        print(f"Join error: {e}")

@socketio.on('message')
def handle_message(data):
    try:
        room = data['room']
        text = data['text']
        username = data.get('username')
        if not username or not text:
            return
        
        supabase.table('messages').insert({
            'room': room,
            'username': username,
            'text': text,
            'timestamp': datetime.now().isoformat(),
            'read_status': 'sent'
        }).execute()
        
        emit('new_message', {
            'username': username,
            'text': text,
            'read_status': 'sent',
            'timestamp': datetime.now().isoformat()
        }, to=room)
    except Exception as e:
        print(f"Message error: {e}")

@socketio.on('media_message')
def handle_media_message(data):
    try:
        room = data['room']
        media_url = data.get('media_url')
        media_type = data.get('media_type')
        text = data.get('text', '')
        username = data.get('username')
        
        if not username or not media_url:
            return
        
        supabase.table('messages').insert({
            'room': room,
            'username': username,
            'text': text,
            'media_url': media_url,
            'media_type': media_type,
            'timestamp': datetime.now().isoformat(),
            'read_status': 'sent'
        }).execute()
        
        emit('new_media', {
            'username': username,
            'text': text,
            'media_url': media_url,
            'media_type': media_type,
            'timestamp': datetime.now().isoformat()
        }, to=room)
    except Exception as e:
        print(f"Media error: {e}")

@socketio.on('mark_read')
def handle_mark_read(data):
    try:
        room = data['room']
        supabase.table('messages').update({'read_status': 'read'}).eq('room', room).eq('read_status', 'sent').execute()
        emit('read_receipt', {'room': room}, to=room)
    except Exception as e:
        print(f"Mark read error: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
