import os
import uuid
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from supabase import create_client, Client
from pydantic import BaseModel
import socketio
import jwt
from typing import Optional

# Конфиг
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-this")

# Инициализация
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
app = FastAPI()
sio = socketio.AsyncServer(cors_allowed_origins="*", async_mode="asgi")
socket_app = socketio.ASGIApp(sio, app)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Модели
class User(BaseModel):
    username: str
    password: str

class Message(BaseModel):
    room: str
    text: str
    username: str
    media_url: Optional[str] = None
    media_type: Optional[str] = None

# ========== АУТЕНТИФИКАЦИЯ ==========
def hash_password(password: str) -> str:
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token(username: str) -> str:
    return jwt.encode({"username": username, "exp": datetime.utcnow()}, JWT_SECRET, algorithm="HS256")

@app.post("/register")
async def register(user: User):
    try:
        hashed = hash_password(user.password)
        supabase.table("users").insert({
            "username": user.username,
            "password_hash": hashed
        }).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": "Пользователь уже существует"}

@app.post("/login")
async def login(user: User):
    hashed = hash_password(user.password)
    result = supabase.table("users").select("*").eq("username", user.username).eq("password_hash", hashed).execute()
    if result.data:
        token = generate_token(user.username)
        return {"success": True, "token": token}
    return {"success": False, "error": "Неверный логин или пароль"}

@app.post("/auto_login")
async def auto_login(data: dict):
    try:
        payload = jwt.decode(data["token"], JWT_SECRET, algorithms=["HS256"])
        return {"success": True, "username": payload["username"]}
    except:
        return {"success": False}

# ========== ЗАГРУЗКА МЕДИА ==========
@app.post("/upload_media")
async def upload_media(
    file: UploadFile = File(...),
    room: str = Form(...),
    username: str = Form(...),
    token: str = Depends(lambda: None)  # упрощенно, проверяйте в реальном проекте
):
    # Проверяем пользователя
    if not username:
        return {"success": False, "error": "No username"}
    
    # Генерируем имя файла
    ext = file.filename.split(".")[-1]
    file_id = str(uuid.uuid4())
    file_path = f"media/{room}/{file_id}.{ext}"
    
    # Определяем тип
    media_type = "image" if file.content_type.startswith("image") else "video"
    
    # Загружаем в Supabase Storage
    try:
        content = await file.read()
        supabase.storage.from_("chat-media").upload(file_path, content, {"content-type": file.content_type})
        public_url = supabase.storage.from_("chat-media").get_public_url(file_path)
        
        return {
            "success": True,
            "media_url": public_url,
            "media_type": media_type,
            "text": f"[{media_type}]"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ========== SOCKET.IO ==========
connected_users = {}

@sio.event
async def connect(sid, environ):
    print(f"Connected: {sid}")

@sio.event
async def join(sid, data):
    room = data["room"]
    username = data["username"]
    connected_users[sid] = {"room": room, "username": username}
    sio.enter_room(sid, room)
    
    # Загружаем историю из БД
    result = supabase.table("messages").select("*").eq("room", room).order("timestamp", desc=False).limit(100).execute()
    history = []
    for msg in result.data:
        history.append({
            "text": msg["text"],
            "username": msg["username"],
            "timestamp": msg["timestamp"],
            "read_status": msg["read_status"],
            "media_url": msg.get("media_url"),
            "media_type": msg.get("media_type")
        })
    await sio.emit("history", history, to=sid)

@sio.event
async def message(sid, data):
    room = data["room"]
    msg_data = {
        "room": room,
        "text": data.get("text", ""),
        "username": data["username"],
        "timestamp": datetime.utcnow().isoformat(),
        "read_status": "sent",
        "media_url": data.get("media_url"),
        "media_type": data.get("media_type")
    }
    
    # Сохраняем в Supabase
    supabase.table("messages").insert(msg_data).execute()
    
    # Рассылаем всем в комнате
    await sio.emit("new_message", msg_data, to=room)

@sio.event
async def mark_read(sid, data):
    room = data["room"]
    # Обновляем статус прочтения в БД (упрощенно)
    await sio.emit("read_receipt", {"room": room}, to=room)

@sio.event
async def disconnect(sid):
    if sid in connected_users:
        del connected_users[sid]

# Запуск
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(socket_app, host="0.0.0.0", port=8000)
