"""9Router SQLite DB injector for Blackbox.ai API keys."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional


def find_9router_db() -> Optional[Path]:
    """Auto-discover 9Router database path."""
    home = Path.home()
    candidates = [
        home / "AppData" / "Roaming" / "9router" / "db" / "data.sqlite",
        home / ".local" / "share" / "provider" / "db.sqlite",
        home / ".config" / "provider" / "db.sqlite",
        home / "provider" / "db.sqlite",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def inject_key(
    email: str,
    api_key: str,
    db_path: Optional[str] = None,
    provider: str = "blackbox",
    base_url: str = "https://api.blackbox.ai/v1",
) -> str:
    """Inject a single API key into 9Router SQLite DB.

    Returns the connection ID.
    """
    db = Path(db_path) if db_path else find_9router_db()
    if not db or not db.exists():
        raise FileNotFoundError("9Router database not found")

    conn_id = f"bb_{api_key[:12]}"
    name = f"blackbox-{email.split('@')[0][:12]}"

    data = json.dumps({
        "apiKey": api_key,
        "testStatus": "active",
        "providerSpecificData": {
            "baseUrl": base_url,
            "connectionProxyEnabled": False,
            "connectionProxyUrl": "",
            "connectionNoProxy": "",
        },
    })

    conn = sqlite3.connect(str(db))
    cur = conn.cursor()

    cur.execute("SELECT id FROM providerConnections WHERE id = ?", (conn_id,))
    if cur.fetchone():
        cur.execute(
            "UPDATE providerConnections SET authType=?, data=?, updatedAt=datetime('now') WHERE id=?",
            ("apikey", data, conn_id),
        )
    else:
        cur.execute(
            """INSERT INTO providerConnections
               (id, provider, authType, name, email, priority, isActive, data, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, 50, 1, ?, datetime('now'), datetime('now'))""",
            (conn_id, provider, "apikey", name, email, data),
        )

    conn.commit()
    conn.close()
    return conn_id


def count_blackbox(db_path: Optional[str] = None) -> int:
    """Count active blackbox connections in 9Router."""
    db = Path(db_path) if db_path else find_9router_db()
    if not db or not db.exists():
        return 0
    conn = sqlite3.connect(str(db))
    count = conn.execute(
        "SELECT COUNT(*) FROM providerConnections WHERE provider='blackbox' AND isActive=1"
    ).fetchone()[0]
    conn.close()
    return count


def list_blackbox(db_path: Optional[str] = None) -> list[dict]:
    """List all blackbox connections in 9Router."""
    db = Path(db_path) if db_path else find_9router_db()
    if not db or not db.exists():
        return []
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, name, email, isActive FROM providerConnections WHERE provider='blackbox'"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
