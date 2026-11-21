"""World view: a read-only HTML page generated from the database alone.

Phase 1 stand-in for the in-app Companion view (approved). Static HTML.
The Territory section lists every location with its controller and status,
because location and territory changes are state — a future dynamic map
(Phase 4) renders its changes from these same tables and the event log.
"""

import html
import json

from . import db


def _effect_text(op):
    # A skipped op (its `when` failed) never happened: it renders as
    # nothing, never as if it applied. The log records what really
    # happened, not what was requested. Callers filter out None.
    if op.get("skipped"):
        return None
    kind = op.get("op")
    if kind == "rest":
        return "rests"
    if kind == "resource_add":
        return (f"{op['resource']} {op.get('applied_qty', op['qty']):+d} "
                f"({op['holder']})")
    if kind == "resource_move":
        return (f"{op['resource']} {op.get('applied_qty', op['qty'])} "
                f"{op['from']} -> {op['to']}")
    if kind == "clock_add":
        return f"clock {op['clock']} +{op.get('applied_qty', op['qty'])}"
    if kind == "bond_add":
        # Bond is looked up by engine only; the pilot may be null (Pack
        # bond), so a bond_add op carries no pilot key. (v1.5 exposed
        # this: Dream Share firing is the first bond_add to reach the
        # render, and the old code crashed on op['pilot'].)
        pilot = op.get("pilot") or "-"
        return (f"Bond {op.get('applied_qty', op['qty']):+d} "
                f"({pilot} / {op['engine']})")
    if kind == "hunger_add":
        return f"Hunger {op.get('applied_qty', op['qty']):+d} ({op['engine']})"
    if kind == "hunger_set":
        return f"Hunger -> {op['value']} ({op['engine']})"
    if kind == "location_set":
        bits = []
        if "controller" in op:
            bits.append(f"controller -> {op['controller']}")
        if "status" in op:
            bits.append(f"status -> {op['status']}")
        return f"{op['location']}: {', '.join(bits)}"
    if kind == "status_set":
        return f"{op['id']}: status -> {op['status']}"
    if kind == "move":
        return (f"{op['id']}: {op.get('old_location', '?')} -> "
                f"{op['location']}")
    if kind == "flag_set":
        return f"flag {op.get('flag')}"
    if kind == "sweep_clock":
        return (f"sweep: clock {op['clock']} {op['old']} -> {op['new']} "
                f"(Turn {op['source_turn']})")
    if kind == "sweep_bond":
        return (f"sweep: Bond {op['engine']} {op['old']} -> {op['new']} "
                f"(Turn {op['source_turn']})")
    if kind == "note":
        return op.get("text", "note")
    if "era_closed" in op:
        return f"era closed: {op['era_closed']}"
    return json.dumps(op, sort_keys=True)


def _section(title, rows):
    body = "".join(f"<tr>{r}</tr>" for r in rows)
    return (f"<h2>{html.escape(title)}</h2>"
            f"<table>{body}</table>")


def _td(text):
    return f"<td>{html.escape(str(text))}</td>"


def render_world_view_json(conn, out_path, carried=None):
    """Stable JSON export of the world state, for the Companion app.

    Mirrors render_world_view's data (world, tick, era, clocks,
    factions, locations, engines, resources, recent events) plus the
    sweep ledger (last_swept_turn/version, pending_decision) and,
    when a carried record is given, the scene/tension/trade-off/
    decision the last approved block carried. The app reads this
    file through its own import action; the engine never writes
    app.db. `carried` is a dict (the carried.json record) or None —
    without it the scene fields are null and the pending decision
    comes from meta. The live campaign has no engine DB yet, so
    this export is built and proven against the Fork A test DB; the
    app's live Ironwild campaign is never fed Fork A state.
    """
    import datetime

    tick = db.get_tick(conn)
    world = db.get_meta(conn, "world_id", "?")
    fork = db.get_meta(conn, "fork_label", "?")
    source = db.get_meta(conn, "source_snapshot", "?")
    era = conn.execute(
        "SELECT name FROM eras WHERE end_tick IS NULL ORDER BY id DESC "
        "LIMIT 1").fetchone()
    era_name = era["name"] if era and era["name"] else None
    pending = db.get_meta(conn, "pending_decision", "") or ""
    last_swept_turn = db.get_meta(conn, "last_swept_turn")
    last_swept_version = db.get_meta(conn, "last_swept_version")

    view = {
        "world_id": world,
        "fork_label": fork,
        "source_snapshot": source,
        "tick": tick,
        "era": era_name,
        "last_swept_turn": (int(last_swept_turn)
                            if last_swept_turn is not None else None),
        "last_swept_version": last_swept_version,
        "pending_decision": (carried.get("pending_decision")
                             if carried else pending),
        "scene": carried.get("scene") if carried else None,
        "scene_tension": carried.get("scene_tension") if carried else None,
        "active_trade_off": (carried.get("active_trade_off")
                             if carried else None),
        "clocks": [{"id": r["id"], "name": r["name"],
                    "value": r["value"], "max": r["max"],
                    "status": r["status"]}
                   for r in conn.execute(
                       "SELECT * FROM clocks ORDER BY id")],
        "factions": [{"id": r["id"], "name": r["name"],
                      "doctrine": r["doctrine"],
                      "standings": json.loads(r["standings"])}
                     for r in conn.execute(
                         "SELECT * FROM factions ORDER BY id")],
        "locations": [{"id": r["id"], "name": r["name"],
                       "kind": r["kind"],
                       "controller_faction_id": r["controller_faction_id"],
                       "status": r["status"],
                       "condition": r["condition"],
                       "mapped": r["mapped"]}
                      for r in conn.execute(
                          "SELECT * FROM locations ORDER BY id")],
        "engines": [{"id": r["id"], "name": r["name"],
                     "shape": r["shape"], "pilot_id": r["pilot_id"],
                     "pilot_name": r["pname"], "bond": r["bond"],
                     "hunger": r["hunger"], "status": r["status"],
                     "location_id": r["location_id"],
                     "molt_trigger": r["molt_trigger"]}
                    for r in conn.execute(
                        "SELECT e.id AS id, e.name AS name, "
                        "e.shape AS shape, e.pilot_id AS pilot_id, "
                        "n.name AS pname, b.bond AS bond, "
                        "e.hunger AS hunger, e.status AS status, "
                        "e.location_id AS location_id, "
                        "e.molt_trigger AS molt_trigger "
                        "FROM engines e "
                        "LEFT JOIN npcs n ON e.pilot_id = n.id "
                        "LEFT JOIN bonds b ON b.engine_id = e.id "
                        "ORDER BY e.id")],
        "npcs": [{"id": r["id"], "name": r["name"],
                  "location_id": r["location_id"],
                  "successor": r["successor"], "age": r["age"]}
                 for r in conn.execute(
                     "SELECT * FROM npcs ORDER BY id")],
        "resources": [{"holder_id": r["holder_id"],
                       "holder_kind": r["holder_kind"],
                       "resource": r["resource"], "qty": r["qty"]}
                      for r in conn.execute(
                          "SELECT * FROM resources "
                          "ORDER BY holder_id, resource")],
        "recent_events": [{"id": r["id"], "tick": r["tick"],
                           "actor_id": r["actor_id"],
                           "action": r["action"],
                           "effect": json.loads(r["effect"])}
                          for r in conn.execute(
                              "SELECT * FROM events "
                              "ORDER BY id DESC LIMIT 20")],
        "generated_at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(view, f, indent=2, sort_keys=True)
    return out_path


def render_world_view(conn, out_path):
    tick = db.get_tick(conn)
    world = db.get_meta(conn, "world_id", "?")
    fork = db.get_meta(conn, "fork_label", "?")
    source = db.get_meta(conn, "source_snapshot", "?")
    era = conn.execute(
        "SELECT name FROM eras WHERE end_tick IS NULL ORDER BY id DESC "
        "LIMIT 1").fetchone()
    era_name = era["name"] if era and era["name"] else "(unnamed — Lore to name)"

    parts = ["<!DOCTYPE html><html><head><meta charset='utf-8'>"
             "<title>World view</title>"
             "<style>body{font-family:sans-serif;max-width:900px;margin:2em auto;"
             "padding:0 1em}table{border-collapse:collapse;width:100%}"
             "td,th{border:1px solid #ccc;padding:4px 8px;text-align:left}"
             "h1{font-size:1.4em}h2{font-size:1.1em;margin-top:1.5em}</style>"
             "</head><body>"]
    parts.append(f"<h1>{html.escape(world)} — {html.escape(fork)}</h1>")
    parts.append(f"<p>Source snapshot: {html.escape(source)} &middot; "
                 f"Tick {tick} (1 tick = 1 day) &middot; Era: "
                 f"{html.escape(era_name)}</p>")

    clocks = [_td(r["name"]) + _td(f"{r['value']}/{r['max']}") +
              _td(r["status"])
              for r in conn.execute(
                  "SELECT * FROM clocks ORDER BY id")]
    parts.append(_section("Clocks", clocks))

    factions = [_td(r["name"]) + _td(r["doctrine"]) +
                _td(json.dumps(json.loads(r["standings"]), sort_keys=True))
                for r in conn.execute(
                    "SELECT * FROM factions ORDER BY id")]
    parts.append(_section("Factions", factions))

    locations = [_td(r["name"]) + _td(r["kind"]) +
                 _td(r["controller_faction_id"] or "-") + _td(r["status"])
                 for r in conn.execute(
                     "SELECT * FROM locations ORDER BY id")]
    parts.append(_section(
        "Territory (controllers and status — the future map reads this)",
        locations))

    pack = []
    for r in conn.execute(
            "SELECT e.name AS ename, e.shape, e.status, e.hunger, "
            "n.name AS pname, b.bond FROM engines e "
            "LEFT JOIN npcs n ON e.pilot_id = n.id "
            "LEFT JOIN bonds b ON b.engine_id = e.id ORDER BY e.id"):
        pack.append(_td(r["ename"]) + _td(r["shape"]) +
                    _td(r["pname"] or "-") + _td(f"Bond {r['bond']}") +
                    _td(f"Hunger {r['hunger']}") + _td(r["status"]))
    parts.append(_section("The Pack — Engines and Bond", pack))

    res = [_td(r["holder_id"]) + _td(r["holder_kind"]) +
           _td(r["resource"]) + _td(r["qty"])
           for r in conn.execute(
               "SELECT * FROM resources ORDER BY holder_id, resource")]
    parts.append(_section("Resources", res))

    evs = []
    for r in conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT 20"):
        effect = json.loads(r["effect"])
        text = "; ".join(
            t for t in (_effect_text(op) for op in effect) if t) or "-"
        evs.append(_td(f"Tick {r['tick']}") + _td(r["actor_id"]) +
                   _td(r["action"]) + _td(text))
    parts.append(_section("Recent events (latest 20)", evs))

    parts.append("</body></html>")
    with open(out_path, "w") as f:
        f.write("\n".join(parts))
    return out_path
