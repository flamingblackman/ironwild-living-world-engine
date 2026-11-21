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
    if "era_closed" in op:
        return f"era closed: {op['era_closed']}"
    return json.dumps(op, sort_keys=True)


def _section(title, rows):
    body = "".join(f"<tr>{r}</tr>" for r in rows)
    return (f"<h2>{html.escape(title)}</h2>"
            f"<table>{body}</table>")


def _td(text):
    return f"<td>{html.escape(str(text))}</td>"


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
        text = "; ".join(_effect_text(op) for op in effect) or "-"
        evs.append(_td(f"Tick {r['tick']}") + _td(r["actor_id"]) +
                   _td(r["action"]) + _td(text))
    parts.append(_section("Recent events (latest 20)", evs))

    parts.append("</body></html>")
    with open(out_path, "w") as f:
        f.write("\n".join(parts))
    return out_path
