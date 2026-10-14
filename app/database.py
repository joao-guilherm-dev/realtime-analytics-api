import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS points (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  metric TEXT NOT NULL,
  ts REAL NOT NULL,
  value REAL NOT NULL,
  tags TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_points_metric_ts ON points(metric, ts);
CREATE TABLE IF NOT EXISTS alert_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  metric TEXT NOT NULL,
  kind TEXT NOT NULL,
  op TEXT,
  threshold REAL,
  method TEXT NOT NULL DEFAULT 'zscore',
  sensitivity REAL,
  cooldown_seconds INTEGER NOT NULL DEFAULT 60,
  active INTEGER NOT NULL DEFAULT 1,
  created_by TEXT,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS alert_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rule_id INTEGER NOT NULL,
  metric TEXT NOT NULL,
  ts REAL NOT NULL,
  value REAL NOT NULL,
  message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON alert_events(ts);
"""


class Database:
    """Camada fina sobre sqlite3 (thread-safe via lock; WAL ligado)."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()

    def init(self) -> None:
        with self._lock:
            if self._conn is not None:
                return
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(SCHEMA)
            conn.commit()
            self._conn = conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def ping(self) -> bool:
        try:
            with self._lock:
                self._conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    # ---- usuários
    def create_user(self, username: str, password_hash: str) -> bool:
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)",
                    (username, password_hash, time.time()),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def get_user(self, username: str) -> Optional[sqlite3.Row]:
        with self._lock:
            return self._conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

    # ---- pontos
    def insert_points(self, rows: Sequence[Tuple[str, float, float, str]]) -> None:
        if not rows:
            return
        with self._lock:
            self._conn.executemany("INSERT INTO points(metric,ts,value,tags) VALUES(?,?,?,?)", rows)
            self._conn.commit()

    def metric_names(self) -> List[str]:
        with self._lock:
            return [r[0] for r in self._conn.execute("SELECT DISTINCT metric FROM points")]

    def recent_points(self, metric: str, limit: int) -> List[Tuple[float, float]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts,value FROM points WHERE metric=? ORDER BY ts DESC LIMIT ?", (metric, limit)
            ).fetchall()
        return [(r["ts"], r["value"]) for r in reversed(rows)]

    def delete_metric(self, metric: str) -> int:
        with self._lock:
            cur = self._conn.execute("DELETE FROM points WHERE metric=?", (metric,))
            self._conn.commit()
            return cur.rowcount

    def purge_older_than(self, ts: float) -> int:
        with self._lock:
            cur = self._conn.execute("DELETE FROM points WHERE ts<?", (ts,))
            self._conn.execute("DELETE FROM alert_events WHERE ts<?", (ts,))
            self._conn.commit()
            return cur.rowcount

    # ---- regras de alerta
    def add_rule(self, rule: Dict, created_by: str) -> Dict:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO alert_rules(metric,kind,op,threshold,method,sensitivity,cooldown_seconds,active,created_by,created_at)"
                " VALUES(?,?,?,?,?,?,?,1,?,?)",
                (rule["metric"], rule["kind"], rule.get("op"), rule.get("threshold"), rule["method"],
                 rule.get("sensitivity"), rule["cooldown_seconds"], created_by, time.time()),
            )
            self._conn.commit()
            return self.get_rule(cur.lastrowid)

    def get_rule(self, rule_id: int) -> Optional[Dict]:
        with self._lock:
            r = self._conn.execute("SELECT * FROM alert_rules WHERE id=?", (rule_id,)).fetchone()
        return dict(r) if r else None

    def list_rules(self) -> List[Dict]:
        with self._lock:
            return [dict(r) for r in self._conn.execute("SELECT * FROM alert_rules ORDER BY id")]

    def delete_rule(self, rule_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM alert_rules WHERE id=?", (rule_id,))
            self._conn.commit()
            return cur.rowcount > 0

    # ---- eventos de alerta
    def insert_events(self, events: Sequence[Dict]) -> List[int]:
        ids: List[int] = []
        if not events:
            return ids
        with self._lock:
            for e in events:
                cur = self._conn.execute(
                    "INSERT INTO alert_events(rule_id,metric,ts,value,message) VALUES(?,?,?,?,?)",
                    (e["rule_id"], e["metric"], e["ts"], e["value"], e["message"]),
                )
                ids.append(cur.lastrowid)
            self._conn.commit()
        return ids

    def list_events(self, limit: int, metric: Optional[str] = None) -> List[Dict]:
        sql, params = "SELECT * FROM alert_events", []
        if metric:
            sql += " WHERE metric=?"
            params.append(metric)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params)]
