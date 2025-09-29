# api/app/main.py
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import os, hashlib, json, datetime, requests, psycopg2
from typing import Optional, Dict, Any

app = FastAPI(title="InfoSuperiority API")

DATABASE_URL = os.getenv("DATABASE_URL")
ML_STUB = os.getenv("ML_STUB", "http://ml_stub:5000/classify")

# --- DB helper (psycopg2 simple) ---
def get_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    sql = """
    CREATE TABLE IF NOT EXISTS events (
      id SERIAL PRIMARY KEY,
      source TEXT,
      text TEXT,
      received_at TIMESTAMP,
      hash TEXT UNIQUE,
      meta JSONB,
      category TEXT,
      provenance JSONB
    );
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            conn.commit()

# call at startup
@app.on_event("startup")
def startup():
    init_db()

# --- models ---
class IngestPayload(BaseModel):
    source: str
    text: str
    meta: Optional[Dict[str, Any]] = {}

# --- helpers ---
def make_hash(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode()).hexdigest()

def check_duplicate(text: str) -> bool:
    h = make_hash(text)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM events WHERE hash=%s", (h,))
            return cur.fetchone() is not None

def save_event(record: dict):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO events (source, text, received_at, hash, meta, category, provenance) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (
                    record["source"], record["text"], record["received_at"],
                    record["hash"], json.dumps(record.get("meta", {})),
                    record.get("category"), json.dumps(record.get("provenance", {}))
                )
            )
            eid = cur.fetchone()[0]
            conn.commit()
            return eid

# --- endpoints ---
@app.post("/ingest")
def ingest(payload: IngestPayload, request: Request):
    text = payload.text.strip()
    if len(text) < 5:
        raise HTTPException(400, "Text too short")
    if check_duplicate(text):
        return {"status": "rejected", "reason": "duplicate"}

    # provenance: who/when/where in pipeline
    prov = {
        "ingested_by": "api",
        "ingested_at": datetime.datetime.utcnow().isoformat(),
        "client": request.client.host
    }

    # call ML stub for lightweight classification (can be NER/embeds later)
    try:
        r = requests.post(ML_STUB, json={"text": text}, timeout=2.0)
        ml_out = r.json()
    except Exception:
        ml_out = {"category": "UNCLASSIFIED", "confidence": 0.0}

    record = {
        "source": payload.source,
        "text": text,
        "received_at": datetime.datetime.utcnow(),
        "hash": make_hash(text),
        "meta": payload.meta,
        "category": ml_out.get("category"),
        "provenance": {"ingest": prov, "ml": ml_out}
    }
    eid = save_event(record)
    # optionally push to Neo4j / KG async (here: stub)
    return {"status": "accepted", "id": eid, "category": record["category"]}

@app.get("/events")
def list_events(limit: int = 50):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, source, text, received_at, category FROM events ORDER BY id DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
    return [{"id": r[0], "source": r[1], "text": r[2], "received_at": r[3].isoformat(), "category": r[4]} for r in rows]

@app.get("/analytics/summary")
def analytics_summary():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT category, count(*) FROM events GROUP BY category")
            rows = cur.fetchall()
    return {r[0] or "UNCLASSIFIED": r[1] for r in rows}
