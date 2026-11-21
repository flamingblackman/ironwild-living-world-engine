"""Condition language for triggers, needs, and effect `when` clauses.

A condition is one of:
  - a list of conditions (AND, backward compatible with the fixture)
  - {"all": [cond, ...]}   -- every branch holds
  - {"any": [cond, ...]}   -- at least one branch holds
  - {"not": cond}          -- the branch does not hold
  - a leaf clause {"kind": ...}

`when` clauses on effect ops are evaluated against the state as it was when
the action began (all whens first, then the passing ops apply in order).
That is what keeps a multi-step bargain to one step per action.

Leaf clause kinds (values may use {self}, {pilot}, {bonded_engine},
{location}, {holder}, {faction} placeholders, substituted by the caller):

  {"kind": "always"}
  {"kind": "resource", "holder": "<id>", "holder_kind": "npc|faction|location|pack",
   "resource": "Feed", "op": "<", "value": 3}
  {"kind": "clock", "id": "<clock>", "op": "<", "value": 6}
  {"kind": "bond", "engine": "<id>", "op": ">=", "value": 3}
      -- Bond is looked up by engine only; the pilot may be null (Pack bond).
  {"kind": "any_bond", "op": "<", "value": 5}
      -- at least one living Engine's Bond satisfies the comparison
      -- (v1.5: Dream Share's trigger needs "an Engine's Bond is below 5").
  {"kind": "hunger", "engine": "<id>", "op": ">=", "value": 7}
  {"kind": "status", "entity_kind": "npc|engine|location", "id": "<id>",
   "value": "standing"}
  {"kind": "status_in", "entity_kind": "npc|engine|location", "id": "<id>",
   "values": ["exhausted", "damaged"]}
  {"kind": "actor_location", "actor": "<npc id>", "location": "<id>"}
  {"kind": "engine_present", "location": "<id>", "min_hunger": 1,
   "status_in": ["active", "field-patched"]}
      -- an Engine exists at the location matching the filters
  {"kind": "engines_ready", "location": "<id>", "min_bond": 3, "count": 2}
      -- at least `count` engines at the location with Bond >= min_bond
  {"kind": "unmapped_exists"}
      -- at least one location with mapped = 0
  {"kind": "location_is", "location": "<id>", "loc_kind": "wreck",
   "mapped": true}
      -- the location row matches kind and mapped state (keys optional)
  {"kind": "flag", "flag": "patrolled:great_basin", "present": true}
      -- a per-tick flag set this tick (tick_flags table)
  {"kind": "pack_ready", "faction": "<id>", "min_bond": 3, "count": 2}
      -- at least `count` engines of the faction with Bond >= min_bond
      -- (fixture-era clause; Fork A uses engines_ready instead)
  {"kind": "has_capability", "actor": "<id>", "capability": "<cap>"}

Ops: <, <=, >, >=, ==, !=
"""

import json

OPS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def _compare(op, actual, expected):
    if op not in OPS:
        raise ValueError(f"unknown op: {op}")
    return OPS[op](actual, expected)


def _resource_qty(conn, holder_id, holder_kind, resource):
    row = conn.execute(
        "SELECT qty FROM resources WHERE holder_id = ? AND holder_kind = ? "
        "AND resource = ?",
        (holder_id, holder_kind, resource),
    ).fetchone()
    return row["qty"] if row else 0


def _bond(conn, engine_id):
    row = conn.execute(
        "SELECT bond FROM bonds WHERE engine_id = ?", (engine_id,)
    ).fetchone()
    return row["bond"] if row else 0


def _engine_status_ok(row_status, status_in):
    if status_in is None:
        return True
    return row_status in status_in


def condition_holds(conn, cond):
    """Evaluate one condition (clause, list, all/any/not) against state."""
    if cond is None:
        return True
    if isinstance(cond, list):
        return all(condition_holds(conn, c) for c in cond)
    if isinstance(cond, dict):
        if "all" in cond:
            return all(condition_holds(conn, c) for c in cond["all"])
        if "any" in cond:
            return any(condition_holds(conn, c) for c in cond["any"])
        if "not" in cond:
            return not condition_holds(conn, cond["not"])
        return clause_holds(conn, cond)
    raise ValueError(f"bad condition: {cond!r}")


def clauses_hold(conn, clauses):
    return condition_holds(conn, clauses)


def clause_holds(conn, clause):
    kind = clause.get("kind")
    if kind == "always":
        return True
    if kind == "resource":
        actual = _resource_qty(conn, clause["holder"], clause["holder_kind"],
                               clause["resource"])
        return _compare(clause["op"], actual, clause["value"])
    if kind == "clock":
        row = conn.execute(
            "SELECT value, status FROM clocks WHERE id = ?", (clause["id"],)
        ).fetchone()
        if row is None:
            return False
        return _compare(clause["op"], row["value"], clause["value"])
    if kind == "bond":
        actual = _bond(conn, clause["engine"])
        return _compare(clause["op"], actual, clause["value"])
    if kind == "any_bond":
        rows = conn.execute(
            "SELECT b.bond FROM bonds b JOIN engines e "
            "ON e.id = b.engine_id WHERE e.status != 'dead'"
        ).fetchall()
        return any(_compare(clause["op"], r["bond"], clause["value"])
                   for r in rows)
    if kind == "hunger":
        row = conn.execute(
            "SELECT hunger FROM engines WHERE id = ?", (clause["engine"],)
        ).fetchone()
        if row is None:
            return False
        return _compare(clause["op"], row["hunger"], clause["value"])
    if kind == "status":
        table = {"npc": "npcs", "engine": "engines",
                 "location": "locations"}[clause["entity_kind"]]
        row = conn.execute(
            f"SELECT status FROM {table} WHERE id = ?", (clause["id"],)
        ).fetchone()
        if row is None:
            return False
        return row["status"] == clause["value"]
    if kind == "status_in":
        table = {"npc": "npcs", "engine": "engines",
                 "location": "locations"}[clause["entity_kind"]]
        row = conn.execute(
            f"SELECT status FROM {table} WHERE id = ?", (clause["id"],)
        ).fetchone()
        if row is None:
            return False
        return row["status"] in clause["values"]
    if kind == "actor_location":
        row = conn.execute(
            "SELECT location_id FROM npcs WHERE id = ?", (clause["actor"],)
        ).fetchone()
        if row is None:
            return False
        return row["location_id"] == clause["location"]
    if kind == "engine_present":
        rows = conn.execute(
            "SELECT hunger, status FROM engines WHERE location_id = ?",
            (clause["location"],),
        ).fetchall()
        for r in rows:
            if r["hunger"] < clause.get("min_hunger", 0):
                continue
            if not _engine_status_ok(r["status"], clause.get("status_in")):
                continue
            return True
        return False
    if kind == "engines_ready":
        rows = conn.execute(
            "SELECT e.id FROM engines e "
            "JOIN bonds b ON b.engine_id = e.id "
            "WHERE e.location_id = ? AND b.bond >= ? "
            "AND e.status != 'dead'",
            (clause["location"], clause["min_bond"]),
        ).fetchall()
        return len(rows) >= clause["count"]
    if kind == "unmapped_exists":
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM locations WHERE mapped = 0"
        ).fetchone()
        return row["n"] > 0
    if kind == "mapped_location_exists":
        # A mapped location exists, optionally of a kind and/or
        # uncontrolled (controller NULL). Used by scavenge (mapped wreck)
        # and claim (uncontrolled mapped ground).
        sql = "SELECT COUNT(*) AS n FROM locations WHERE mapped = 1"
        params = []
        if "loc_kind" in clause:
            sql += " AND kind = ?"
            params.append(clause["loc_kind"])
        if clause.get("controlled") is False:
            sql += " AND controller_faction_id IS NULL"
        elif clause.get("controlled") is True:
            sql += " AND controller_faction_id IS NOT NULL"
        row = conn.execute(sql, params).fetchone()
        return row["n"] > 0
    if kind == "location_is":
        row = conn.execute(
            "SELECT kind, mapped FROM locations WHERE id = ?",
            (clause["location"],),
        ).fetchone()
        if row is None:
            return False
        if "loc_kind" in clause and row["kind"] != clause["loc_kind"]:
            return False
        if "mapped" in clause and bool(row["mapped"]) != clause["mapped"]:
            return False
        return True
    if kind == "flag":
        row = conn.execute(
            "SELECT flag FROM tick_flags WHERE flag = ?", (clause["flag"],)
        ).fetchone()
        return (row is not None) == clause.get("present", True)
    if kind == "pack_ready":
        rows = conn.execute(
            "SELECT e.id, b.bond FROM engines e "
            "JOIN npcs n ON e.pilot_id = n.id "
            "JOIN bonds b ON b.engine_id = e.id "
            "WHERE n.faction_id = ? AND e.status = 'active'",
            (clause["faction"],),
        ).fetchall()
        ready = sum(1 for r in rows if r["bond"] >= clause["min_bond"])
        return ready >= clause["count"]
    if kind == "has_capability":
        row = conn.execute(
            "SELECT capabilities FROM npcs WHERE id = ?", (clause["actor"],)
        ).fetchone()
        if row is None:
            return False
        return clause["capability"] in json.loads(row["capabilities"])
    raise ValueError(f"unknown clause kind: {kind}")
