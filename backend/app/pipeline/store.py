"""Result store: a SQLite lookup table keyed by run_id + customer_id /
product_id. Not a feature store or vector DB -- just "read the row for
this key" at a scale where that's sufficient.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.config import RUNS_DIR

DB_PATH = RUNS_DIR / "results.db"


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                industry TEXT,
                status TEXT,
                computed_at TEXT,
                error TEXT,
                eda_json TEXT,
                metrics_json TEXT,
                model_config_json TEXT
            );
            CREATE TABLE IF NOT EXISTS personalized (
                run_id TEXT, customer_id TEXT, items_json TEXT,
                PRIMARY KEY (run_id, customer_id)
            );
            CREATE TABLE IF NOT EXISTS fbt (
                run_id TEXT, product_id TEXT, items_json TEXT,
                PRIMARY KEY (run_id, product_id)
            );
            CREATE TABLE IF NOT EXISTS popularity (
                run_id TEXT, segment_key TEXT, items_json TEXT,
                PRIMARY KEY (run_id, segment_key)
            );
            CREATE TABLE IF NOT EXISTS name_maps (
                run_id TEXT PRIMARY KEY, customer_names_json TEXT, product_names_json TEXT
            );
            """
        )
        try:
            conn.execute("ALTER TABLE runs ADD COLUMN metrics_json TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists (pre-existing db file)
        try:
            conn.execute("ALTER TABLE runs ADD COLUMN model_config_json TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists (pre-existing db file)


def create_run(run_id: str, industry: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO runs (run_id, industry, status, computed_at) VALUES (?, ?, 'validating', ?)",
            (run_id, industry, datetime.now(timezone.utc).isoformat()),
        )


def mark_eda_ready(run_id: str, eda: dict) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE runs SET status='eda_ready', computed_at=?, eda_json=? WHERE run_id=?",
            (datetime.now(timezone.utc).isoformat(), json.dumps(eda), run_id),
        )


def mark_training_started(run_id: str, model_config: dict | None = None) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE runs SET status='training', model_config_json=? WHERE run_id=?",
            (json.dumps(model_config) if model_config else None, run_id),
        )


def mark_training_completed(run_id: str, metrics: dict | None) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE runs SET status='completed', computed_at=?, metrics_json=? WHERE run_id=?",
            (datetime.now(timezone.utc).isoformat(), json.dumps(metrics) if metrics else None, run_id),
        )


def mark_run_failed(run_id: str, error: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE runs SET status='failed', error=? WHERE run_id=?",
            (error, run_id),
        )


def get_run(run_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT run_id, industry, status, computed_at, error, eda_json, metrics_json, model_config_json "
            "FROM runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "run_id": row[0],
        "industry": row[1],
        "status": row[2],
        "computed_at": row[3],
        "error": row[4],
        "eda": json.loads(row[5]) if row[5] else None,
        "metrics": json.loads(row[6]) if row[6] else None,
        "model_config": json.loads(row[7]) if row[7] else None,
    }


def latest_completed_run() -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT run_id FROM runs WHERE status='completed' ORDER BY computed_at DESC LIMIT 1"
        ).fetchone()
    return get_run(row[0]) if row else None


def list_runs(limit: int = 50) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT run_id, industry, status, computed_at, error FROM runs ORDER BY computed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"run_id": r[0], "industry": r[1], "status": r[2], "computed_at": r[3], "error": r[4]} for r in rows
    ]


def write_name_maps(run_id: str, customer_names: dict[str, str], product_names: dict[str, str]) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO name_maps (run_id, customer_names_json, product_names_json) VALUES (?, ?, ?)",
            (run_id, json.dumps(customer_names), json.dumps(product_names)),
        )


def get_name_maps(run_id: str) -> tuple[dict[str, str], dict[str, str]]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT customer_names_json, product_names_json FROM name_maps WHERE run_id=?", (run_id,)
        ).fetchone()
    if not row:
        return {}, {}
    return json.loads(row[0]), json.loads(row[1])


def write_personalized(run_id: str, results: dict[str, list[str]]) -> None:
    with _conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO personalized (run_id, customer_id, items_json) VALUES (?, ?, ?)",
            [(run_id, cust, json.dumps(items)) for cust, items in results.items()],
        )


def write_fbt(run_id: str, results: dict[str, list[str]]) -> None:
    with _conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO fbt (run_id, product_id, items_json) VALUES (?, ?, ?)",
            [(run_id, prod, json.dumps(items)) for prod, items in results.items()],
        )


def write_popularity(run_id: str, results: dict[str, list[str]]) -> None:
    with _conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO popularity (run_id, segment_key, items_json) VALUES (?, ?, ?)",
            [(run_id, seg, json.dumps(items)) for seg, items in results.items()],
        )


def get_personalized(run_id: str, customer_id: str) -> list[str] | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT items_json FROM personalized WHERE run_id=? AND customer_id=?", (run_id, customer_id)
        ).fetchone()
    return json.loads(row[0]) if row else None


def get_fbt(run_id: str, product_id: str) -> list[str] | None:
    with _conn() as conn:
        row = conn.execute("SELECT items_json FROM fbt WHERE run_id=? AND product_id=?", (run_id, product_id)).fetchone()
    return json.loads(row[0]) if row else None


def get_popularity(run_id: str, segment_key: str = "overall") -> list[str] | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT items_json FROM popularity WHERE run_id=? AND segment_key=?", (run_id, segment_key)
        ).fetchone()
    return json.loads(row[0]) if row else None


def all_tables_for_export(run_id: str) -> dict[str, list[dict]]:
    with _conn() as conn:
        personalized = conn.execute(
            "SELECT customer_id, items_json FROM personalized WHERE run_id=?", (run_id,)
        ).fetchall()
        fbt = conn.execute("SELECT product_id, items_json FROM fbt WHERE run_id=?", (run_id,)).fetchall()
        popularity = conn.execute(
            "SELECT segment_key, items_json FROM popularity WHERE run_id=?", (run_id,)
        ).fetchall()
    return {
        "personalized": [{"customer_id": c, "recommendations": json.loads(j)} for c, j in personalized],
        "frequently_bought_together": [{"product_id": p, "recommendations": json.loads(j)} for p, j in fbt],
        "popularity": [{"segment": s, "recommendations": json.loads(j)} for s, j in popularity],
    }
