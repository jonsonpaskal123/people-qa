# backend/main.py
import os
import uuid
import logging
import httpx
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer
from sqlalchemy.orm import declarative_base, sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger(__name__)

AGENT_URL    = os.getenv("AGENT_URL",    "http://agent:8001")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////app/data/conversations.db")

# ─── Database ─────────────────────────────────────────────────────────────────
Base    = declarative_base()
engine  = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine)


class Conversation(Base):
    __tablename__ = "conversations"
    id         = Column(String,   primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String,   index=True)
    role       = Column(String)
    content    = Column(Text)
    sql_query  = Column(Text,     nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class RequestLog(Base):
    __tablename__ = "request_logs"
    id          = Column(String,   primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id  = Column(String)
    question    = Column(Text)
    sql_query   = Column(Text,     nullable=True)
    answer      = Column(Text)
    duration_ms = Column(Integer)
    created_at  = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="People QA Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Schemas ──────────────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role:    str
    content: str


class ChatRequest(BaseModel):
    model:    str            = "people-qa"
    messages: list[ChatMessage]
    stream:   bool           = False


class ChatChoice(BaseModel):
    message:       ChatMessage
    index:         int = 0
    finish_reason: str = "stop"


class ChatResponse(BaseModel):
    id:      str
    object:  str = "chat.completion"
    model:   str = "people-qa"
    choices: list[ChatChoice]


# ─── Endpoints ────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/v1/models")
async def list_models():
    """برای Open WebUI"""
    return {
        "object": "list",
        "data": [{
            "id":       "people-qa",
            "object":   "model",
            "created":  1700000000,
            "owned_by": "local"
        }]
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    """endpoint اصلی سازگار با OpenAI API"""
    start      = datetime.utcnow()
    session_id = str(uuid.uuid4())[:8]

    # آخرین سوال کاربر
    user_messages = [m for m in request.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(400, "No user message found")

    question = user_messages[-1].content
    log.info(f"❓ [{session_id}] Question: {question}")

    # تاریخچه گفتگو
    history = [
        {"role": m.role, "content": m.content}
        for m in request.messages[:-1]
        if m.role in ("user", "assistant")
    ]

    # ذخیره سوال کاربر
    db = Session()
    try:
        db.add(Conversation(
            session_id=session_id,
            role="user",
            content=question
        ))
        db.commit()

        # ارسال به Agent
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{AGENT_URL}/query",
                json={
                    "question":   question,
                    "history":    history,
                    "session_id": session_id,
                }
            )
            response.raise_for_status()
            data = response.json()

        answer    = data["answer"]
        sql_query = data.get("sql")

        # اضافه کردن SQL به پاسخ
        full_answer = answer
        if sql_query:
            full_answer += f"\n\n```sql\n{sql_query}\n```"

        # محاسبه زمان
        duration = int((datetime.utcnow() - start).total_seconds() * 1000)
        log.info(f"✅ [{session_id}] Answer in {duration}ms")
        log.info(f"🔍 [{session_id}] SQL: {sql_query}")

        # ذخیره پاسخ و لاگ
        db.add(Conversation(
            session_id=session_id,
            role="assistant",
            content=full_answer,
            sql_query=sql_query
        ))
        db.add(RequestLog(
            session_id=session_id,
            question=question,
            sql_query=sql_query,
            answer=answer,
            duration_ms=duration
        ))
        db.commit()

        return ChatResponse(
            id=f"chatcmpl-{session_id}",
            choices=[ChatChoice(
                message=ChatMessage(
                    role="assistant",
                    content=full_answer
                )
            )]
        )

    except httpx.HTTPError as e:
        log.error(f"❌ Agent error: {e}")
        raise HTTPException(503, f"Agent unavailable: {e}")
    except Exception as e:
        log.error(f"❌ Error: {e}", exc_info=True)
        raise HTTPException(500, str(e))
    finally:
        db.close()


@app.get("/history/{session_id}")
async def get_history(session_id: str):
    """تاریخچه گفتگوی یک session"""
    db = Session()
    try:
        convs = (
            db.query(Conversation)
            .filter(Conversation.session_id == session_id)
            .order_by(Conversation.created_at)
            .all()
        )
        return [
            {
                "role":    c.role,
                "content": c.content,
                "sql":     c.sql_query,
                "time":    c.created_at.isoformat(),
            }
            for c in convs
        ]
    finally:
        db.close()


@app.get("/logs")
async def get_logs(limit: int = 50):
    """لیست آخرین درخواست‌ها"""
    db = Session()
    try:
        logs = (
            db.query(RequestLog)
            .order_by(RequestLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id":          l.id,
                "session_id":  l.session_id,
                "question":    l.question,
                "sql":         l.sql_query,
                "answer":      l.answer[:200],
                "duration_ms": l.duration_ms,
                "time":        l.created_at.isoformat(),
            }
            for l in logs
        ]
    finally:
        db.close()