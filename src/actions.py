"""Material effects. Every effect op changes state and returns the op that
was actually applied (with clamped quantities and old values), so the event
log records what really happened, not what was requested.

`when` clauses: an op may carry "when" (a condition in the conditions.py
language). All whens are evaluated against the state as it was when the
action began; ops whose when fails are skipped and recorded with
"skipped": true. That is what keeps a multi-step bargain to one step per
action and makes blocked raids visible in the log instead of silent.

Effect ops (values support {self}, {pilot}, {bonded_engine}, {location},
{holder}, {faction} placeholders, substituted by tick.py before application;
target selectors {"target": ...} are resolved by tick.py first — see
src/targets.py):

  {"op": "resource_add", "holder": "<id>", "holder_kind": "npc|faction|location|pack",
   "resource": "Feed", "qty": 3}
  {"op": "resource_move", "from": "<id>", "from_kind": "...", "to": "<id>",
   "to_kind": "...", "resource": "Salvage", "qty": 2}
  {"op": "clock_add", "clock": "<id>", "qty": 1}   (qty < 0 raises: DC-09)
  {"op": "bond_add", "engine": "<id>", "qty": -2}
      -- Bond is looked up by engine only; the pilot may be null (Pack bond).
      -- qty > 0 raises unless the caller allows it (DC-18/DC-19: only the
      -- Dream Share action passes allow_bond_increase).
  {"op": "bond_add_pack", "faction": "<id>", "min_bond": 3, "qty": -1}
  {"op": "pack_merge_burn", "location": "<id>", "min_bond": 3, "qty": -2}
      -- Burns Bond on the top-2 Bond engines at the location (the merge pair).
  {"op": "free_netted", "location": "<id>"}
      -- A netted Engine at the location becomes field-patched (freed by a
      -- Pack Merge); returns the freed engine id, or nothing.
  {"op": "hunger_add", "engine": "<id>", "qty": 1}
  {"op": "hunger_set", "engine": "<id>", "value": 0}
  {"op": "molt_trigger_set", "engine": "<id>", "value": 1}
  {"op": "location_set", "location": "<id>", "controller": "<faction>|null",
   "status": "standing|fortified|...", "mapped": 0|1}
      -- controller/status/mapped are optional; the applied op records the
      -- old values (DC-13 / map-event rule).
  {"op": "status_set", "entity_kind": "npc|engine|location", "id": "<id>",
   "status": "<status>"}   -- applied op records old_status
  {"op": "move", "entity_kind": "npc|engine", "id": "<id>",
   "location": "<id>"}     -- applied op records old_location
  {"op": "standing_set", "faction": "<id>", "other": "<id>",
   "value": "hostile"}     -- applied op records old_value
  {"op": "flag_set", "flag": "<flag>", "value": "<value>"}
  {"op": "note", "text": "<log-only text>"}   -- no state change
  {"op": "rest"}  -- no state change; the actor rests
"""

from . import conditions
from . import db
from . import resources


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _bond_row(conn, engine_id):
    return conn.execute(
        "SELECT bond FROM bonds WHERE engine_id = ?", (engine_id,)
    ).fetchone()


def apply_effect(conn, op, allow_bond_increase=False):
    kind = op["op"]
    if kind == "rest":
        return {"op": "rest"}
    if kind == "note":
        return {"op": "note", "text": op["text"]}
    if kind == "resource_add":
        applied = resources.add_qty(conn, op["holder"], op["holder_kind"],
                                    op["resource"], op["qty"])
        return {**op, "applied_qty": applied}
    if kind == "resource_move":
        moved = resources.move_qty(conn, op["from"], op["from_kind"],
                                   op["to"], op["to_kind"],
                                   op["resource"], op["qty"])
        return {**op, "applied_qty": moved}
    if kind == "clock_add":
        if op["qty"] < 0:
            raise ValueError("clocks never decrease (DC-09)")
        row = conn.execute(
            "SELECT value, max, status FROM clocks WHERE id = ?",
            (op["clock"],)
        ).fetchone()
        if row is None or row["status"] == "complete":
            return {**op, "applied_qty": 0}
        current, maximum = row["value"], row["max"]
        new = min(maximum, current + op["qty"])
        applied = new - current
        conn.execute("UPDATE clocks SET value = ? WHERE id = ?",
                     (new, op["clock"]))
        return {**op, "applied_qty": applied}
    if kind == "bond_add":
        # DC-18 is a Fork A rule, not a universal engine law: it applies
        # only when the seed declares bond_recovery "dream_share_only".
        # The fixture's feed/molt actions raise Bond by design.
        if (op["qty"] > 0 and not allow_bond_increase
                and db.get_meta(conn, "bond_recovery", "")
                == "dream_share_only"):
            raise ValueError(
                "Bond increases only through Dream Share (DC-18)")
        row = _bond_row(conn, op["engine"])
        if row is None:
            return {**op, "applied_qty": 0}
        new = _clamp(row["bond"] + op["qty"], 0, 5)
        applied = new - row["bond"]
        conn.execute("UPDATE bonds SET bond = ? WHERE engine_id = ?",
                     (new, op["engine"]))
        return {**op, "applied_qty": applied}
    if kind == "bond_add_pack":
        rows = conn.execute(
            "SELECT b.engine_id, b.bond FROM bonds b "
            "JOIN engines e ON e.id = b.engine_id "
            "JOIN npcs n ON n.id = b.pilot_id "
            "WHERE n.faction_id = ? AND e.status = 'active' "
            "AND b.bond >= ? ORDER BY b.engine_id",
            (op["faction"], op["min_bond"]),
        ).fetchall()
        applied = []
        for row in rows:
            new = _clamp(row["bond"] + op["qty"], 0, 5)
            conn.execute(
                "UPDATE bonds SET bond = ? WHERE engine_id = ?",
                (new, row["engine_id"]),
            )
            applied.append({"engine": row["engine_id"],
                            "applied_qty": new - row["bond"]})
        return {**op, "applied": applied}
    if kind == "pack_merge_burn":
        rows = conn.execute(
            "SELECT b.engine_id, b.bond FROM bonds b "
            "JOIN engines e ON e.id = b.engine_id "
            "WHERE e.location_id = ? AND b.bond >= ? "
            "AND e.status != 'dead' ORDER BY b.bond DESC, b.engine_id",
            (op["location"], op["min_bond"]),
        ).fetchall()
        pair = rows[:2]
        applied = []
        for row in pair:
            new = _clamp(row["bond"] + op["qty"], 0, 5)
            conn.execute(
                "UPDATE bonds SET bond = ? WHERE engine_id = ?",
                (new, row["engine_id"]),
            )
            applied.append({"engine": row["engine_id"],
                            "applied_qty": new - row["bond"]})
        return {**op, "applied": applied,
                "pair": [r["engine_id"] for r in pair]}
    if kind == "free_netted":
        row = conn.execute(
            "SELECT id FROM engines WHERE location_id = ? "
            "AND status = 'netted' ORDER BY id LIMIT 1",
            (op["location"],),
        ).fetchone()
        if row is None:
            return {**op, "applied": []}
        conn.execute(
            "UPDATE engines SET status = 'field-patched' WHERE id = ?",
            (row["id"],))
        return {**op, "applied": [{"engine": row["id"],
                                    "old_status": "netted",
                                    "status": "field-patched"}]}
    if kind == "hunger_add":
        row = conn.execute(
            "SELECT hunger FROM engines WHERE id = ?", (op["engine"],)
        ).fetchone()
        if row is None:
            return {**op, "applied_qty": 0}
        new = _clamp(row["hunger"] + op["qty"], 0, 10)
        applied = new - row["hunger"]
        conn.execute("UPDATE engines SET hunger = ? WHERE id = ?",
                     (new, op["engine"]))
        return {**op, "applied_qty": applied}
    if kind == "hunger_set":
        row = conn.execute(
            "SELECT hunger FROM engines WHERE id = ?", (op["engine"],)
        ).fetchone()
        if row is None:
            return {**op, "applied_qty": 0}
        new = _clamp(op["value"], 0, 10)
        conn.execute("UPDATE engines SET hunger = ? WHERE id = ?",
                     (new, op["engine"]))
        return {**op, "applied_qty": new - row["hunger"]}
    if kind == "molt_trigger_set":
        conn.execute("UPDATE engines SET molt_trigger = ? WHERE id = ?",
                     (1 if op["value"] else 0, op["engine"]))
        return dict(op)
    if kind == "location_set":
        row = conn.execute(
            "SELECT controller_faction_id, status, mapped FROM locations "
            "WHERE id = ?", (op["location"],)
        ).fetchone()
        if row is None:
            return {**op, "applied": []}
        old = {"old_controller": row["controller_faction_id"],
               "old_status": row["status"], "old_mapped": row["mapped"]}
        sets, params = [], []
        if "controller" in op:
            sets.append("controller_faction_id = ?")
            params.append(op["controller"])
        if "status" in op:
            sets.append("status = ?")
            params.append(op["status"])
        if "mapped" in op:
            sets.append("mapped = ?")
            params.append(1 if op["mapped"] else 0)
        if sets:
            params.append(op["location"])
            conn.execute(
                f"UPDATE locations SET {', '.join(sets)} WHERE id = ?",
                params,
            )
        return {**op, **old}
    if kind == "status_set":
        table = {"npc": "npcs", "engine": "engines",
                 "location": "locations"}[op["entity_kind"]]
        row = conn.execute(
            f"SELECT status FROM {table} WHERE id = ?", (op["id"],)
        ).fetchone()
        old = row["status"] if row else None
        conn.execute(f"UPDATE {table} SET status = ? WHERE id = ?",
                     (op["status"], op["id"]))
        return {**op, "old_status": old}
    if kind == "move":
        table = {"npc": "npcs", "engine": "engines"}[op["entity_kind"]]
        row = conn.execute(
            f"SELECT location_id FROM {table} WHERE id = ?", (op["id"],)
        ).fetchone()
        old = row["location_id"] if row else None
        conn.execute(f"UPDATE {table} SET location_id = ? WHERE id = ?",
                     (op["location"], op["id"]))
        return {**op, "old_location": old}
    if kind == "standing_set":
        import json
        row = conn.execute(
            "SELECT standings FROM factions WHERE id = ?", (op["faction"],)
        ).fetchone()
        standings = json.loads(row["standings"]) if row else {}
        old = standings.get(op["other"])
        standings[op["other"]] = op["value"]
        conn.execute("UPDATE factions SET standings = ? WHERE id = ?",
                     (json.dumps(standings, sort_keys=True), op["faction"]))
        return {**op, "old_value": old}
    if kind == "flag_set":
        conn.execute(
            "INSERT INTO tick_flags (flag, tick, value) VALUES (?, ?, ?) "
            "ON CONFLICT(flag) DO UPDATE SET tick = excluded.tick, "
            "value = excluded.value",
            (op["flag"], op.get("tick", 0), op.get("value", "")),
        )
        return dict(op)
    raise ValueError(f"unknown effect op: {kind}")


def apply_effects(conn, effects, tick=None, allow_bond_increase=False):
    """Apply an action's effect ops in order, against pre-action state for
    `when` clauses. Returns the applied-op records for the event log.

    Bond increases only through Dream Share (DC-18/DC-19): a positive bond_add
    raises unless the caller passes allow_bond_increase, which only the
    Dream Share action does. Pack Merge burns Bond (negative) and is always
    allowed.
    """
    effects = list(effects or [])
    passes = []
    for op in effects:
        when = op.get("when")
        if when is None or conditions.condition_holds(conn, when):
            passes.append(True)
        else:
            passes.append(False)
    applied = []
    for op, ok in zip(effects, passes):
        if not ok:
            skipped = {k: v for k, v in op.items() if k != "when"}
            skipped["skipped"] = True
            applied.append(skipped)
            continue
        if op["op"] == "flag_set" and "tick" not in op and tick is not None:
            op = {**op, "tick": tick}
        if _target_missing(op):
            skipped = dict(op)
            skipped["skipped"] = True
            skipped["reason"] = "no target"
            applied.append(skipped)
            continue
        applied.append(apply_effect(conn, op, allow_bond_increase))
    return applied


def _target_missing(op):
    """True when an op's target entity resolved to nothing."""
    if op.get("engine") is None and "engine" in op:
        return True
    if op.get("location") is None and "location" in op:
        return True
    if op.get("id") is None and "id" in op:
        return True
    return False
