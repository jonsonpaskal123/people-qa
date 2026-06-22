# agent/main.py
import os
import logging
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from graph import run_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger(__name__)

app = FastAPI(title="AI Agent", version="1.0.0")


# ─── Schemas ─────────────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    question:   str
    history:    list = []
    session_id: str  = "default"


class QueryResponse(BaseModel):
    answer: str
    sql:    str | None = None


# ─── Endpoints ───────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    try:
        log.info(f"❓ Question: {req.question}")
        result = await run_agent(req.question, req.history)
        log.info(f"✅ Answer: {result['answer'][:100]}")
        log.info(f"🔍 SQL: {result.get('sql')}")
        return QueryResponse(
            answer=result["answer"],
            sql=result.get("sql"),
        )
    except Exception as e:
        log.error(f"❌ Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=False)