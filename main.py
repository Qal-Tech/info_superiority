main.py
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

"""
Information Superiority Engine - Modular Framework
--------------------------------------------------
Цель: создать модуль, который обрабатывает поток информации от момента получения
до аналитических выводов, обеспечивая чистоту данных, смысловую ценность и поддержку решений.
"""

from typing import List, Dict, Any
from datetime import datetime
import hashlib
import difflib
import sqlite3
import json


# ────────────────────────────────────────────────
# [1] Модуль СБОРА данных (Ingestion)
# ────────────────────────────────────────────────
class DataIngestion:
    """Принимает и подготавливает входящие события."""

    def ingest(self, source: str, text: str, **kwargs) -> Dict[str, Any]:
        return {
            "source": source,
            "text": text.strip(),
            "received_at": datetime.utcnow().isoformat(),
            "meta": kwargs
        }


# ────────────────────────────────────────────────
# [2] Модуль НОРМАЛИЗАЦИИ (Normalization)
# ────────────────────────────────────────────────
class Normalization:
    """Приводит событие к стандартному виду (чистка, приведение регистра и т.д.)."""

    def normalize(self, record: Dict[str, Any]) -> Dict[str, Any]:
        record["text"] = record["text"].lower().strip()
        return record


# ────────────────────────────────────────────────
# [3] Модуль ДЕДУПЛИКАЦИИ и контроля качества (QC)
# ────────────────────────────────────────────────
class DeduplicationEngine:
    """Отсекает дубликаты и мусорные записи, защищая память от засорения."""

    def __init__(self, db_path: str = "info_superiority.db"):
        self.conn = sqlite3.connect(db_path)
        self._init_db()

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                source TEXT,
                text TEXT,
                hash TEXT UNIQUE,
                received_at TEXT,
                meta TEXT
            );
        """)
        self.conn.commit()

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def is_duplicate(self, text: str) -> bool:
        text_hash = self._hash(text)
        cur = self.conn.execute("SELECT text FROM events WHERE hash = ?", (text_hash,))
        if cur.fetchone():
            return True
        # Проверка на «почти дубликат»
        cur = self.conn.execute("SELECT text FROM events")
        for (existing,) in cur.fetchall():
            if difflib.SequenceMatcher(None, text, existing).ratio() > 0.9:
                return True
        return False

    def validate_and_store(self, record: Dict[str, Any]) -> bool:
        text = record.get("text", "")
        if len(text) < 5 or self.is_duplicate(text):
            return False
        self.conn.execute(
            "INSERT INTO events (source, text, hash, received_at, meta) VALUES (?, ?, ?, ?, ?)",
            (record["source"], text, self._hash(text), record["received_at"], json.dumps(record.get("meta", {})))
        )
        self.conn.commit()
        return True


# ────────────────────────────────────────────────
# [4] Модуль КЛАССИФИКАЦИИ (Classification)
# ────────────────────────────────────────────────
class ClassificationEngine:
    """
    Присваивает каждой записи базовую категорию.
    (Пока - правило на основе ключевых слов, позже - ML/NLP.)
    """

    CATEGORIES = {
        "protest": "CIVIL_ACTIVITY",
        "threat": "SECURITY_ALERT",
        "outage": "INFRASTRUCTURE",
        "attack": "CRISIS_EVENT"
    }

    def classify(self, record: Dict[str, Any]) -> Dict[str, Any]:
        text = record["text"]
        record["category"] = "UNCLASSIFIED"
        for kw, cat in self.CATEGORIES.items():
            if kw in text:
                record["category"] = cat
                break
        return record


# ────────────────────────────────────────────────
# [5] Модуль ОБОГАЩЕНИЯ данных (Enrichment)
# ────────────────────────────────────────────────
class EnrichmentEngine:
    """Извлекает сущности: локации, даты, акторов и т.д. (пока - заготовка)."""

    def enrich(self, record: Dict[str, Any]) -> Dict[str, Any]:
        # TODO: подключить NER / геоаналитику / парсеры
        record["entities"] = {
            "location": "unknown",
            "timestamp": record["received_at"],
            "actors": []
        }
        return record


# ────────────────────────────────────────────────
# [6] Модуль АНАЛИТИКИ и ИНТЕЛЛЕКТА (Analytics)
# ────────────────────────────────────────────────
class AnalyticsEngine:
    """Строит базовые аналитические выводы (паттерны, тренды, индикаторы)."""

    def analyze(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        summary = {}
        for r in records:
            cat = r.get("category", "UNCLASSIFIED")
            summary[cat] = summary.get(cat, 0) + 1
        return summary


# ────────────────────────────────────────────────
# [7] Основной процессор (Pipeline Orchestrator)
# ────────────────────────────────────────────────
class InformationSuperiorityPipeline:
    """Оркестрирует весь процесс от данных до выводов."""

    def __init__(self):
        self.ingestor = DataIngestion()
        self.normalizer = Normalization()
        self.dedup = DeduplicationEngine()
        self.classifier = ClassificationEngine()
        self.enricher = EnrichmentEngine()
        self.analytics = AnalyticsEngine()

    def process_event(self, source: str, text: str, **meta) -> Dict[str, Any]:
        event = self.ingestor.ingest(source, text, **meta)
        event = self.normalizer.normalize(event)
        if not self.dedup.validate_and_store(event):
            return {"status": "rejected", "reason": "duplicate_or_invalid"}
        event = self.classifier.classify(event)
        event = self.enricher.enrich(event)
        return {"status": "processed", "event": event}

    def analyze_all(self) -> Dict[str, Any]:
        # Здесь можно вытянуть все записи из базы и проанализировать
        # Для упрощения: анализируем список вручную переданных событий
        # (в реальности - SELECT * FROM events)
        return {"status": "analytics_ready"}


# ────────────────────────────────────────────────
# Пример запуска
# ────────────────────────────────────────────────
if __name__ == "__main__":
    engine = InformationSuperiorityPipeline()

    # Примерные события
    examples = [
        ("OSINT", "Peaceful protest observed in Almaty"),
        ("SENSOR", "Power outage detected in north sector"),
        ("API", "Threat detected near border checkpoint"),
        ("NEWS", "Protest gathering planned tomorrow")
    ]

    for src, text in examples:
        result = engine.process_event(src, text)
        print(result)

    # Заготовка аналитики
    print(engine.analyze_all())
    main