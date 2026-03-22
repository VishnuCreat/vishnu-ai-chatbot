from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI
import os
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

app = FastAPI()

# Serve HTML pages
@app.get("/")
def home():
    return FileResponse("login.html")

@app.get("/login.html")
def login_page():
    return FileResponse("login.html")

@app.get("/index.html")
def index_page():
    return FileResponse("index.html")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Database
DATABASE_URL = "sqlite:///./chat.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String)
    password = Column(String)

class ChatMessage(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(String)
    username = Column(String)
    role = Column(String)
    content = Column(Text)

Base.metadata.create_all(bind=engine)

class ChatRequest(BaseModel):
    message: str
    chat_id: str
    username: str

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/register")
def register(user: LoginRequest):
    db = SessionLocal()
    db.add(User(username=user.username, password=user.password))
    db.commit()
    return {"message": "User registered"}

@app.post("/login")
def login(user: LoginRequest):
    db = SessionLocal()
    db_user = db.query(User).filter(User.username == user.username, User.password == user.password).first()
    if db_user:
        return {"message": "Login successful"}
    return {"error": "Invalid login"}

@app.post("/chat")
def chat(request: ChatRequest):
    db = SessionLocal()

    messages = db.query(ChatMessage).filter(
        ChatMessage.chat_id == request.chat_id,
        ChatMessage.username == request.username
    ).all()

    chat_history = [{"role": "system", "content": "You are a helpful AI assistant."}]

    for msg in messages:
        chat_history.append({"role": msg.role, "content": msg.content})

    chat_history.append({"role": "user", "content": request.message})

    db.add(ChatMessage(chat_id=request.chat_id, username=request.username, role="user", content=request.message))
    db.commit()

    def stream_response():
        stream = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=chat_history,
            stream=True
        )

        full_reply = ""

        for chunk in stream:
            if chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                full_reply += text
                yield text

        db.add(ChatMessage(chat_id=request.chat_id, username=request.username, role="assistant", content=full_reply))
        db.commit()

    return StreamingResponse(stream_response(), media_type="text/plain")

@app.get("/chats/{username}")
def get_chats(username: str):
    db = SessionLocal()
    chats = db.query(ChatMessage.chat_id).filter(ChatMessage.username == username).distinct().all()
    return {"chats": [c[0] for c in chats]}

@app.get("/messages/{chat_id}/{username}")
def get_messages(chat_id: str, username: str):
    db = SessionLocal()
    messages = db.query(ChatMessage).filter(
        ChatMessage.chat_id == chat_id,
        ChatMessage.username == username
    ).all()
    return {"messages": [{"role": m.role, "content": m.content} for m in messages]}
