"""Database helpers: connection, schema, meta, deterministic state hashing."""

import hashlib
import json
import os
import sqlite3

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "state", "schema.sql")

# Tables hashed for the state hash. Events are hashed on their deterministic
# fields only (created_at is wall-clock time and is excluded).
STATE_TABLES = ["meta", "npcs", "engines", "bonds", "factions",
                "locations", "resources", "clocks", "eras"]


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn):
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


def get_tick(conn):
    return int(get_meta(conn, "tick", 0))


def set_tick(conn, tick):
    set_meta(conn, "tick", tick)


def state_hash(conn):
    """Deterministic SHA-256 of the full world state.

    Covers every state table in row order, plus the event log on its
    deterministic fields (id, tick, actor, action, score, effect, hashes).
    Excludes wall-clock fields (events.created_at) so the same run always
    hashes the same way.
    """
    h = hashlib.sha256()
    for table in STATE_TABLES:
        for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid"):
            h.update(json.dumps(dict(row), sort_keys=True, default=str).encode())
    for row in conn.execute(
        "SELECT id, tick, actor_id, action, score, runner_up, effect, "
        "prev_hash, event_hash FROM events ORDER BY id"
    ):
        h.update(json.dumps(dict(row), sort_keys=True, default=str).encode())
    return h.hexdigest()


def record_snapshot(conn, tick):
    digest = state_hash(conn)
    conn.execute(
        "INSERT INTO snapshots (tick, state_sha256) VALUES (?, ?) "
        "ON CONFLICT(tick) DO UPDATE SET state_sha256 = excluded.state_sha256",
        (tick, digest),
    )
    return digest
