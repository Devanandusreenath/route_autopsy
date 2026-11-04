import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .config import DATABASE_PATH

Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)

@contextmanager
def connect():
    con=sqlite3.connect(DATABASE_PATH, timeout=15)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def init_db():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS vehicles (id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS defects (id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS restrictions (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS inspections (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS repairs (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS evidence_analyses (id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL);
        ''')

def put_json(table, key, payload, updated_at=None):
    raw=json.dumps(payload,ensure_ascii=False)
    with connect() as c:
        if table == "vehicles":
            c.execute("INSERT INTO vehicles(id,payload,updated_at) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",(key,raw,updated_at or payload.get("updatedAt", "")))
        elif table == "defects":
            c.execute("INSERT INTO defects(id,payload,created_at) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,created_at=excluded.created_at",(key,raw,updated_at or payload.get("reportedAt", "")))
        elif table == "evidence_analyses":
            c.execute("INSERT INTO evidence_analyses(id,payload,created_at) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",(key,raw,updated_at or payload.get("createdAt", "")))
        elif table == "restrictions":
            c.execute("INSERT INTO restrictions(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",(key,raw))

def get_all(table):
    with connect() as c:
        rows=c.execute(f"SELECT payload FROM {table}").fetchall()
    return [json.loads(r[0]) for r in rows]

def get_one(table,key):
    with connect() as c:
        row=c.execute(f"SELECT payload FROM {table} WHERE id=?",(key,)).fetchone()
    return json.loads(row[0]) if row else None

def delete_one(table,key):
    with connect() as c:
        c.execute(f"DELETE FROM {table} WHERE id=?",(key,))
