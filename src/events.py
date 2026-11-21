"""Append-only event log with a hash chain.

Every event carries prev_hash (the previous event's hash, or GENESIS) and its
own event_hash = sha256(prev_hash | tick | actor | action | effect). The
database triggers in schema.sql refuse UPDATE/DELETE on events; the hash
chain makes silent tampering detectable even if the triggers were bypassed.
"""

import hashlib
import json

GENESIS = "GENESIS"


def _hash_event(prev_hash, tick, actor_id, action, effect):
    payload = "|".join([
        prev_hash,
        str(tick),
        actor_id,
        action,
        json.dumps(effect, sort_keys=True),
    ])
    return hashlib.sha256(payload.encode()).hexdigest()


def last_hash(conn):
    row = conn.execute(
        "SELECT event_hash FROM events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row["event_hash"] if row else GENESIS


def append_event(conn, tick, actor_id, action, score, runner_up, effect):
    """Insert one event. `effect` is the list of effect ops actually applied."""
    prev = last_hash(conn)
    digest = _hash_event(prev, tick, actor_id, action, effect)
    cur = conn.execute(
        "INSERT INTO events (tick, actor_id, action, score, runner_up, "
        "effect, prev_hash, event_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (tick, actor_id, action, score, runner_up,
         json.dumps(effect, sort_keys=True), prev, digest),
    )
    return cur.lastrowid


def verify_chain(conn):
    """Recompute the hash chain. Returns (ok, bad_event_id_or_None)."""
    prev = GENESIS
    for row in conn.execute("SELECT * FROM events ORDER BY id"):
        effect = json.loads(row["effect"])
        expect = _hash_event(prev, row["tick"], row["actor_id"],
                             row["action"], effect)
        if expect != row["event_hash"] or row["prev_hash"] != prev:
            return False, row["id"]
        prev = row["event_hash"]
    return True, None


def count_events(conn):
    return conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
