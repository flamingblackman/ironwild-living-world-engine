"""Seed loading: turn a seed JSON (internal format) into a fresh database.

The seed is the engine's only canon input. It must name its source snapshot
(Turn 131 vFINAL for Fork A). Anything not in the seed cannot happen.
The Lore seed (fork-a.json) is translated to this internal format by
src/lore_seed.py; this loader never reads Lore's prose format directly.
"""

import json

from . import db


def load_seed(conn, seed):
    required = ["world_id", "fork_label", "source_snapshot", "rng_seed",
                "era_length", "factions", "locations", "npcs", "engines",
                "bonds", "resources", "clocks", "actions"]
    missing = [k for k in required if k not in seed]
    if missing:
        raise ValueError(f"seed is missing keys: {missing}")
    if "Turn 136" in seed["source_snapshot"] or "Krov" in seed["source_snapshot"]:
        raise ValueError(
            "seed source must never be Turn 136 / the Krov scene (freeze)")

    db.set_meta(conn, "world_id", seed["world_id"])
    db.set_meta(conn, "fork_label", seed["fork_label"])
    db.set_meta(conn, "source_snapshot", seed["source_snapshot"])
    db.set_meta(conn, "rng_seed", seed["rng_seed"])
    # rng_scheme: v2 is the default for new worlds; a seed may pin
    # "v1" explicitly. Pre-scheme DBs have no key and the tick path
    # treats a missing key as v1, so they replay identically.
    db.set_meta(conn, "rng_scheme", str(seed.get("rng_scheme", "v2")))
    db.set_meta(conn, "era_length", seed["era_length"])
    db.set_meta(conn, "tick", 0)
    db.set_meta(conn, "legacy", json.dumps(seed.get("legacy", {})))
    db.set_meta(conn, "actions", json.dumps(seed["actions"]))
    db.set_meta(conn, "feed_burn", json.dumps(seed.get("feed_burn", [])))
    db.set_meta(conn, "bond_recovery",
                seed.get("bond_recovery", ""))

    for f in seed["factions"]:
        conn.execute(
            "INSERT INTO factions (id, name, doctrine, standings) "
            "VALUES (?, ?, ?, ?)",
            (f["id"], f["name"], f.get("doctrine", ""),
             json.dumps(f.get("standings", {}))),
        )
    for loc in seed["locations"]:
        conn.execute(
            "INSERT INTO locations (id, name, kind, controller_faction_id, "
            "status, mapped, condition) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (loc["id"], loc["name"], loc["kind"], loc.get("controller"),
             loc.get("status", "standing"), 1 if loc.get("mapped", True) else 0,
             loc.get("condition")),
        )
    for npc in seed["npcs"]:
        conn.execute(
            "INSERT INTO npcs (id, name, faction_id, location_id, age, "
            "status, goals, capabilities, successor) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (npc["id"], npc["name"], npc.get("faction"), npc.get("location"),
             npc.get("age"), npc.get("status", "active"),
             json.dumps(npc.get("goals", [])),
             json.dumps(npc.get("capabilities", [])),
             None),  # successors linked in a second pass (FK order)
        )
    for npc in seed["npcs"]:
        if npc.get("successor"):
            conn.execute("UPDATE npcs SET successor = ? WHERE id = ?",
                         (npc["successor"], npc["id"]))
    for eng in seed["engines"]:
        conn.execute(
            "INSERT INTO engines (id, name, shape, pilot_id, location_id, "
            "hunger, hunger_type, hunger_threshold, molt_trigger, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (eng["id"], eng["name"], eng["shape"], eng.get("pilot"),
             eng.get("location"), eng.get("hunger", 0),
             eng["hunger_type"], eng.get("hunger_threshold", 7),
             1 if eng.get("molt_trigger") else 0,
             eng.get("status", "active")),
        )
    for bond in seed["bonds"]:
        conn.execute(
            "INSERT INTO bonds (engine_id, pilot_id, bond) VALUES (?, ?, ?)",
            (bond["engine"], bond.get("pilot"), bond["bond"]),
        )
    for res in seed["resources"]:
        conn.execute(
            "INSERT INTO resources (holder_id, holder_kind, resource, qty) "
            "VALUES (?, ?, ?, ?)",
            (res["holder"], res["holder_kind"], res["resource"],
             res["qty"]),
        )
    for clock in seed["clocks"]:
        conn.execute(
            "INSERT INTO clocks (id, name, value, max, status, on_complete) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (clock["id"], clock["name"], clock.get("value", 0),
             clock["max"], clock.get("status", "running"),
             json.dumps(clock.get("on_complete", []))),
        )
    conn.execute(
        "INSERT INTO eras (name, start_tick, end_tick, legacy_applied) "
        "VALUES (?, 1, NULL, 0)",
        (_first_era_name(seed),),
    )
    conn.commit()


def _first_era_name(seed):
    names = (seed.get("legacy") or {}).get("era_names") or []
    return names[0] if names else None


def load_catalog(conn):
    return json.loads(db.get_meta(conn, "actions", "[]"))


def load_legacy(conn):
    legacy = json.loads(db.get_meta(conn, "legacy", "{}"))
    legacy["era_length"] = int(db.get_meta(conn, "era_length", 365))
    return legacy
