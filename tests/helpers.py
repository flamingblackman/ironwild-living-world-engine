"""Shared helpers for the Living World Engine tests.

Two databases:
  - the synthetic fixture (tests/fixture_seed.json), labeled NOT CANON,
    for proving the machine itself;
  - the real Fork A seed (seed/fork-a.internal.json), produced by the
    adapter from the Lore Team's fork-a.json, for acceptance.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import db, seed as seed_mod  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.dirname(BASE)
FIXTURE_PATH = os.path.join(BASE, "fixture_seed.json")
LORE_SEED_PATH = os.path.join(ENGINE_DIR, "seed", "fork-a.json")
INTERNAL_SEED_PATH = os.path.join(ENGINE_DIR, "seed", "fork-a.internal.json")
INTERNAL_SEED_G_PATH = os.path.join(ENGINE_DIR, "seed", "fork-g.internal.json")

CANON_FILES = [
    os.path.join(ENGINE_DIR, "..", "universe-1-ironwild.md"),
    os.path.join(ENGINE_DIR, "..", "combat-codex-ironwild-hunt-warfare.md"),
    os.path.join(ENGINE_DIR, "..", "mechanic-registry", "registry-ironwild.md"),
    os.path.join(ENGINE_DIR, "..", "gem-instructions",
                 "ironwild-gem-instructions.md"),
]


def fresh_db(tmp_path, seed_path):
    os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
    with open(seed_path) as f:
        seed_data = json.load(f)
    conn = db.connect(tmp_path)
    db.init_schema(conn)
    seed_mod.load_seed(conn, seed_data)
    return conn, seed_data


def fresh_fixture_db(tmp_path):
    return fresh_db(tmp_path, FIXTURE_PATH)


def fresh_fork_db(tmp_path):
    return fresh_db(tmp_path, INTERNAL_SEED_PATH)


def fresh_fork_g_db(tmp_path):
    """Fork G: Fork A v1.6 re-seeded under world_id ironwild-fork-g,
    for the Gemini DM test. Same tick-0 state, separate ledger."""
    return fresh_db(tmp_path, INTERNAL_SEED_G_PATH)


def load_lore_seed():
    with open(LORE_SEED_PATH) as f:
        return json.load(f)


def load_internal_seed():
    with open(INTERNAL_SEED_PATH) as f:
        return json.load(f)


def event_log(conn):
    rows = conn.execute(
        "SELECT tick, actor_id, action, effect, event_hash FROM events "
        "ORDER BY id").fetchall()
    return [(r["tick"], r["actor_id"], r["action"], r["effect"],
             r["event_hash"]) for r in rows]


def event_text(conn):
    """All event log text as one string (for forbidden-word scans)."""
    rows = conn.execute(
        "SELECT actor_id, action, effect FROM events ORDER BY id").fetchall()
    return "\n".join(
        f"{r['actor_id']} {r['action']} {r['effect']}" for r in rows)
