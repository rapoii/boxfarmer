"""SQLite injector — insert harvested keys into 9Router database."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

# Auto-discover 9Router DB
def _discover_db_paths() -> list[Path]:
    env_path = os.environ.get("PROVIDER_DB_PATH")
    if env_path:
        return [Path(env_path)]
    home = Path.home()
    return [
        home / "AppData" / "Roaming" / "9router" / "db" / "data.sqlite",
        home / ".local" / "share" / "provider" / "db.sqlite",
    ]

# New custom node config (NOT the built-in blackbox provider)
# Created via SQLite: openai-compatible-chat-e1da0f1a
PROVIDER_NODE_ID = "openai-compatible-chat-e1da0f1a"
PREFIX = "bb2"
AUTH_TYPE = "apikey"
BASE_URL = "https://api.blackbox.ai/v1"


def find_9router_db() -> Path | None:
    for p in _discover_db_paths():
        if p.exists():
            return p
    return None


def inject_keys(keys_path: str = "output/keys.txt", db_path: str | None = None) -> int:
    """Inject API keys from keys.txt into 9Router's custom bb2 node.

    keys.txt format: email:password:apikey per line
    """
    db = Path(db_path) if db_path else find_9router_db()
    if db is None:
        raise FileNotFoundError("9Router database not found. Set PROVIDER_DB_PATH or pass --db-path.")

    keys_file = Path(keys_path)
    if not keys_file.exists():
        raise FileNotFoundError(f"Keys file not found: {keys_path}")

    lines = [l.strip() for l in keys_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        return 0

    conn = sqlite3.connect(str(db))
    cursor = conn.cursor()
    injected = 0

    for line in lines:
        parts = line.split(":")
        if len(parts) < 3:
            continue

        email = parts[0]
        password = parts[1]
        api_key = parts[2]

        conn_id = f"bb2_{api_key[:12]}"
        name = f"bb2-{email.split('@')[0][:12]}"

        data = json.dumps({
            "apiKey": api_key,
            "testStatus": "active",
            "providerSpecificData": {
                "baseUrl": BASE_URL,
                "connectionProxyEnabled": False,
                "connectionProxyUrl": "",
                "connectionNoProxy": "",
            },
        })

        # Skip if already exists
        cursor.execute("SELECT id FROM providerConnections WHERE id = ?", (conn_id,))
        if cursor.fetchone():
            cursor.execute(
                """UPDATE providerConnections
                   SET authType = ?, data = ?, updatedAt = datetime('now')
                   WHERE id = ?""",
                (AUTH_TYPE, data, conn_id),
            )
            continue

        cursor.execute(
            """INSERT INTO providerConnections
               (id, provider, authType, name, email, priority, isActive, data, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, 50, 1, ?, datetime('now'), datetime('now'))""",
            (conn_id, PROVIDER_NODE_ID, AUTH_TYPE, name, email, data),
        )
        injected += 1

    conn.commit()
    conn.close()
    return injected


def list_injected(db_path: str | None = None) -> list[dict[str, Any]]:
    """List all bb2 connections."""
    db = Path(db_path) if db_path else find_9router_db()
    if db is None or not db.exists():
        return []

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM providerConnections WHERE provider = ?", (PROVIDER_NODE_ID,)
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def remove_keys(db_path: str | None = None) -> int:
    """Remove all bb2 connections."""
    db = Path(db_path) if db_path else find_9router_db()
    if db is None or not db.exists():
        return 0

    conn = sqlite3.connect(str(db))
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM providerConnections WHERE provider = ?", (PROVIDER_NODE_ID,)
    )
    removed = cursor.rowcount
    conn.commit()
    conn.close()
    return removed
