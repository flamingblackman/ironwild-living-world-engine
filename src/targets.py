"""Target selectors: resolve "which entity?" at apply time.

An effect op may use a selector dict instead of a fixed id, e.g. the
"engine" field of a hunger op:
  {"target": "engine_at_location", "location": "{location}",
   "prefer": "highest_hunger", "min_hunger": 1}
  {"target": "engine_at_location", "location": "{location}",
   "prefer": "status_order", "status_in": ["netted", "exhausted", "damaged"]}
  {"target": "unmapped_location"}
  {"target": "lowest_bond_engine", "max_bond": 5}
      -- the lowest-Bond living Engine with Bond below max_bond, ties to
      -- Sledge first (v1.5: Dream Share restores the lowest Bond).

Resolution is deterministic (ORDER BY ... LIMIT 1) and happens once per
action application, so the trigger check and the effect agree on the same
entity. If nothing matches, the selector resolves to None and the op is
recorded as skipped ("no target") instead of failing.
"""

def resolve_targets(conn, obj):
    if isinstance(obj, dict):
        if obj.get("target") in ("engine_at_location", "unmapped_location",
                                 "uncontrolled_mapped_location",
                                 "lowest_bond_engine"):
            return _resolve_selector(conn, obj)
        return {k: resolve_targets(conn, v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_targets(conn, item) for item in obj]
    return obj


def _resolve_selector(conn, sel):
    kind = sel["target"]
    if kind == "engine_at_location":
        sql = ("SELECT id, hunger, status FROM engines WHERE location_id = ? "
               "AND hunger >= ?")
        params = [sel["location"], sel.get("min_hunger", 0)]
        status_in = sel.get("status_in")
        if status_in:
            sql += " AND status IN (%s)" % ", ".join("?" * len(status_in))
            params += list(status_in)
        prefer = sel.get("prefer", "id")
        if prefer == "highest_hunger":
            sql += " ORDER BY hunger DESC, id ASC LIMIT 1"
        elif prefer == "status_order" and status_in:
            case = " ".join(
                f"WHEN '{s}' THEN {i}" for i, s in enumerate(status_in))
            sql += (f" ORDER BY CASE status {case} ELSE 99 END, "
                    "id ASC LIMIT 1")
        else:
            sql += " ORDER BY id ASC LIMIT 1"
        row = conn.execute(sql, params).fetchone()
        return row["id"] if row else None
    if kind == "unmapped_location":
        row = conn.execute(
            "SELECT id FROM locations WHERE mapped = 0 ORDER BY id ASC "
            "LIMIT 1").fetchone()
        return row["id"] if row else None
    if kind == "uncontrolled_mapped_location":
        # The lowest-id mapped location with no controller. Claim can
        # never take a controlled location (DC-17): the selector only
        # ever returns uncontrolled ground.
        row = conn.execute(
            "SELECT id FROM locations WHERE mapped = 1 "
            "AND controller_faction_id IS NULL ORDER BY id ASC "
            "LIMIT 1").fetchone()
        return row["id"] if row else None
    if kind == "lowest_bond_engine":
        # The lowest-Bond living Engine below max_bond, ties to Sledge
        # first (Dream Share restores the lowest Bond, ties to Sledge).
        row = conn.execute(
            "SELECT e.id FROM engines e JOIN bonds b "
            "ON b.engine_id = e.id WHERE e.status != 'dead' "
            "AND b.bond < ? ORDER BY b.bond ASC, (e.id = 'sledge') DESC, "
            "e.id ASC LIMIT 1",
            (sel.get("max_bond", 5),)).fetchone()
        return row["id"] if row else None
    raise ValueError(f"unknown target selector: {kind}")
