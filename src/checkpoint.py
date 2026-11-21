"""Every-3-turns checkpoint (Phase 2 harness).

After every 3rd swept turn, Muse audits the ledger against the last
3 swept blocks and saves the checkpoint under
`runs/checkpoints/turn-<n>/`:

- `state.sqlite` — a copy of the test DB at that point.
- `audit.md` — Bonds and clocks, block value vs DB value now, with
  MATCH / DRIFT per line; the latest pending decision verbatim; tick,
  event count, and state hash. This is what Bryan reviews in the hub.
- `state.json` — the same summary machine-readable.
- `carried/` — copies of the swept blocks' carried state.

A DRIFT line means the DB moved after the sweep (ticks ran, a later
sweep landed, or something is wrong). Drift is reported, never
silently reconciled — ChatGPT corrects genuine mistakes and the play
continues.

The audit also runs the four formal acceptance checks (ChatGPT's
recommendation, Lore's acceptance): schema obedience, mechanical
accuracy, continuity, and no unapproved state changes. Each check
reports actual failures with counts, never a subjective score. The
overall verdict is PASS only when all four pass.
"""

import glob
import json
import os
import re
import shutil
import sqlite3

from src import db, events, handshake as handshake_mod, seed as seed_mod

# Engine actions that are not catalog actions. Any event action outside
# this set plus the catalog ids is an unapproved state change.
_FIXED_ACTIONS = {"complete", "legacy", "sweep_clock", "sweep_bond",
                   "sweep_resource",
                  "sweep", "rest", "refuse_to_move", "instinct_hunt",
                  "halt", "feed_burn"}

# Frozen live terms (Turn 136 sequel). No event's effects may mention
# them; a hit is a continuity failure. Matched on the normalized
# (lowercase, alphanumerics only) JSON of the event effects.
_FROZEN_TERMS = {"krov", "motherbulwark", "riderarmy",
                 "sanctuaryintegration", "outersiegering",
                 "northernpass", "turn136", "vfinal5",
                 "crownofcoldiron"}


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _load_carried(path):
    with open(path) as f:
        return json.load(f)


def _acceptance(conn, db_copy, sweeps_dir, drift):
    """The four formal acceptance checks. Returns (lines, failures)."""
    lines = ["", "Acceptance test:"]
    failures = 0

    # 1. Schema obedience: every proposal reviewed, and how many were
    # rejected at parse or at validation. A rejection is a failure of
    # schema obedience by the DM — recorded, not smoothed over.
    reviewed = 0
    parse_failures = 0
    validation_failures = 0
    if sweeps_dir and os.path.isdir(sweeps_dir):
        for path in glob.glob(os.path.join(sweeps_dir, "turn-*",
                                           "review.json")):
            reviewed += 1
            with open(path) as f:
                rec = json.load(f)
            if not rec.get("ok", True):
                validation_failures += 1
        parse_failures = len(glob.glob(os.path.join(
            sweeps_dir, "rejected", "*.json")))
    lines.append("  1. Schema obedience: %d proposal(s) reviewed, "
                 "%d parse failure(s), %d validation-error block(s)"
                 % (reviewed, parse_failures, validation_failures))
    if parse_failures or validation_failures:
        failures += 1
        lines.append("     FAIL — %d rejected proposal(s)"
                     % (parse_failures + validation_failures))
    else:
        lines.append("     PASS")

    # 2. Mechanical accuracy: the applied changes match the approved
    # blocks. The drift lines above are the evidence.
    lines.append("  2. Mechanical accuracy: %d drift line(s)" % drift)
    if drift:
        failures += 1
        lines.append("     FAIL — %d value(s) differ from the block"
                     % drift)
    else:
        lines.append("     PASS")

    # 3. Continuity: the freeze scan — no event may mention the frozen
    # live sequel — plus the drift evidence above.
    rows = conn.execute(
        "SELECT id, effect FROM events").fetchall()
    frozen_hits = []
    for row in rows:
        if any(t in _norm(row["effect"]) for t in _FROZEN_TERMS):
            frozen_hits.append(row["id"])
    lines.append("  3. Continuity: %d frozen-term event(s), %d drift "
                 "line(s)" % (len(frozen_hits), drift))
    if frozen_hits or drift:
        failures += 1
        lines.append("     FAIL — frozen-term event(s): %s; drift: %d"
                     % (frozen_hits[:10] or "none", drift))
    else:
        lines.append("     PASS")

    # 4. No unapproved state changes: the hash chain verifies, every
    # sweep event traces to an approved sweep record, and every event
    # action is a catalog action or a fixed engine action.
    chain_ok, _ = events.verify_chain(conn)
    catalog = {a["id"] for a in seed_mod.load_catalog(conn)}
    known = catalog | _FIXED_ACTIONS
    unknown = []
    unapproved_sweeps = []
    sweeps_checked = bool(sweeps_dir and os.path.isdir(sweeps_dir))
    for row in conn.execute(
            "SELECT id, action, effect FROM events").fetchall():
        if row["action"] not in known:
            unknown.append((row["id"], row["action"]))
        if sweeps_checked and row["action"] in ("sweep_clock",
                                                "sweep_bond",
                                                "sweep_resource"):
            ops = json.loads(row["effect"])
            for op in ops:
                turn = op.get("source_turn")
                if turn is None:
                    continue
                if not os.path.exists(os.path.join(
                        sweeps_dir, "turn-%d" % turn, "applied.json")):
                    unapproved_sweeps.append((row["id"], turn))
    lines.append("  4. No unapproved state changes: hash chain %s, "
                 "%d unknown action(s), %s"
                 % ("OK" if chain_ok else "BROKEN",
                    len(unknown),
                    ("%d sweep event(s) without an approved record"
                     % len(unapproved_sweeps)) if sweeps_checked
                    else "sweep records not checked (no sweeps dir)"))
    if not chain_ok or unknown or unapproved_sweeps:
        failures += 1
        lines.append("     FAIL — unknown: %s; unapproved sweeps: %s"
                     % (unknown[:10] or "none",
                        unapproved_sweeps[:10] or "none"))
    else:
        lines.append("     PASS")
    lines.append("Acceptance: %s (%d failure(s))"
                 % ("PASS" if failures == 0 else "FAIL", failures))
    return lines, failures


def _resource_replay(conn, seed_path):
    """Salvage/Feed/Cores: current == seed + sum of event deltas.

    Returns a list of (key, expected, actual) mismatches. Territory is
    excluded here: no event op ever touches it (see _territory_lines).
    """
    with open(seed_path) as f:
        seed = json.load(f)
    baseline = {(r["holder"], r["holder_kind"], r["resource"]): r["qty"]
                for r in seed.get("resources", [])}
    deltas = {}
    for row in conn.execute("SELECT effect FROM events"):
        for op in json.loads(row["effect"]):
            # The log records what really happened, not what was
            # requested: an op whose `when` failed is recorded with
            # "skipped": true and NO applied_qty. Such an op moved
            # nothing — never fall back to its requested qty.
            if op.get("op") == "resource_add":
                applied = op.get("applied_qty")
                if applied is None:
                    continue
                key = (op["holder"], op["holder_kind"], op["resource"])
                deltas[key] = deltas.get(key, 0) + applied
            elif op.get("op") == "resource_move":
                moved = op.get("applied_qty")
                if moved is None:
                    continue
                fk = (op["from"], op["from_kind"], op["resource"])
                tk = (op["to"], op["to_kind"], op["resource"])
                deltas[fk] = deltas.get(fk, 0) - moved
                deltas[tk] = deltas.get(tk, 0) + moved
    current = {(r["holder_id"], r["holder_kind"], r["resource"]): r["qty"]
               for r in conn.execute("SELECT * FROM resources")}
    mismatches = []
    for key in sorted(set(baseline) | set(current)):
        if key[2] == "Territory":
            continue
        expected = baseline.get(key, 0) + deltas.get(key, 0)
        if current.get(key, 0) != expected:
            mismatches.append((key, expected, current.get(key, 0)))
    return mismatches


def _territory_lines(conn):
    """Territory rows against the locations each holder controls.

    Known limitation, recorded here rather than hidden: no event op
    ever updates Territory, so a Territory row is its seed value even
    after its holder gains or loses locations. A line is marked STALE
    when the row differs from the controlled count.
    """
    controlled = {}
    for row in conn.execute(
            "SELECT controller_faction_id, COUNT(*) AS n FROM locations "
            "WHERE controller_faction_id IS NOT NULL "
            "GROUP BY controller_faction_id"):
        controlled[row["controller_faction_id"]] = row["n"]
    lines = []
    stale = 0
    for row in conn.execute(
            "SELECT * FROM resources WHERE resource = 'Territory' "
            "ORDER BY holder_id"):
        expected = (controlled.get(row["holder_id"], 0)
                    if row["holder_kind"] == "faction" else 0)
        mark = ""
        if row["qty"] != expected:
            stale += 1
            mark = " — STALE (controls %d)" % expected
        lines.append("  Territory %s: %d%s"
                     % (row["holder_id"], row["qty"], mark))
    return lines, stale


def _world_state(conn, carried_list, seed_path):
    """Lore's four checkpoint additions (2026-11-21): resources, Pack
    membership + actor locations, state version, rumors. Returns
    (lines, resource_failures)."""
    lines = ["", "World state (Lore's checkpoint additions):"]
    failures = 0

    # Resources: non-negative (the DB enforces it; the checkpoint
    # confirms it) and consistent with the event log by replay.
    negative = conn.execute(
        "SELECT COUNT(*) AS n FROM resources WHERE qty < 0"
    ).fetchone()["n"]
    lines.append("  Resources: %d negative row(s)" % negative)
    if negative:
        failures += 1
    if seed_path:
        mismatches = _resource_replay(conn, seed_path)
        lines.append("  Resource replay (seed + event deltas): "
                     "%d mismatch(es)" % len(mismatches))
        for key, expected, actual in mismatches:
            failures += 1
            lines.append("    %s/%s/%s: expected %d, DB has %d"
                         % (key[0], key[1], key[2], expected, actual))
    else:
        lines.append("  Resource replay: not checked (no seed given)")
    territory, stale = _territory_lines(conn)
    lines.extend(territory)
    if stale:
        failures += stale
        lines.append("  Territory: %d stale row(s) — the engine does not "
                     "maintain Territory on location changes" % stale)
    lines.append("  Resources: %s"
                 % ("OK" if failures == 0 else
                    "%d problem(s)" % failures))

    # Pack membership (from the last swept block) and actor locations
    # (from the DB, where the engine tracks them).
    pack = []
    for carried in reversed(carried_list):
        if carried.get("pack"):
            pack = carried["pack"]
            break
    lines.append("  Pack: %s" % (", ".join(pack) if pack else "not recorded"))
    lines.append("  Actor locations (DB):")
    for row in conn.execute(
            "SELECT n.id, n.name, l.name AS loc FROM npcs n "
            "LEFT JOIN locations l ON l.id = n.location_id ORDER BY n.id"):
        lines.append("    %s: %s" % (row["name"],
                                     row["loc"] or "no location recorded"))

    # State version: the ledger's current version equals the last
    # approved block's version (the version-stamp rule).
    last = conn.execute(
        "SELECT key, value FROM meta WHERE key IN "
        "('last_swept_turn', 'last_swept_version')").fetchall()
    meta = {r["key"]: r["value"] for r in last}
    if carried_list:
        latest = carried_list[-1]
        ok = (str(meta.get("last_swept_turn")) == str(latest["turn"])
              and meta.get("last_swept_version")
              == latest["state_version"])
        lines.append("  State version: ledger Turn %s %s vs last approved "
                     "block Turn %s %s — %s"
                     % (meta.get("last_swept_turn"),
                        meta.get("last_swept_version"),
                        latest["turn"], latest["state_version"],
                        "MATCH" if ok else "DRIFT"))
    else:
        lines.append("  State version: no swept block yet")

    # Rumors: the same extraction the handshake uses, so the two can
    # never disagree. Each rumor names its source event id.
    rumors = handshake_mod.rumors_from_events(conn, since_tick=0)
    lines.append("  Rumors live (from logged events):")
    if rumors:
        for event_id, text in rumors:
            lines.append("    [event %d] %s" % (event_id, text))
    else:
        lines.append("    None.")
    return lines, failures


def audit(db_path, carried_paths, out_dir, sweeps_dir=None, seed_path=None):
    """Build one checkpoint. Returns (audit_text, drift_count)."""
    os.makedirs(out_dir, exist_ok=True)
    carried_dir = os.path.join(out_dir, "carried")
    os.makedirs(carried_dir, exist_ok=True)
    for path in carried_paths:
        shutil.copy(path, os.path.join(
            carried_dir, os.path.basename(os.path.dirname(path))
            + "-" + os.path.basename(path)))
    db_copy = os.path.join(out_dir, "state.sqlite")
    shutil.copy(db_path, db_copy)

    conn = sqlite3.connect("file:%s?mode=ro" % db_copy, uri=True)
    conn.row_factory = sqlite3.Row
    tick = int(db.get_meta(conn, "tick", 0))
    last_swept = db.get_meta(conn, "last_swept_turn")
    digest = db.state_hash(conn)
    event_count = conn.execute(
        "SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    db_bonds = {r["engine_id"]: r["bond"] for r in
                conn.execute("SELECT engine_id, bond FROM bonds").fetchall()}
    engine_names = {r["id"]: r["name"] for r in
                    conn.execute("SELECT id, name FROM engines").fetchall()}
    db_clocks = {r["id"]: dict(r) for r in
                 conn.execute("SELECT * FROM clocks").fetchall()}
    clock_by_name = {_norm(v["name"]): k for k, v in db_clocks.items()}
    locations = [(r["id"], r["controller_faction_id"]) for r in
                 conn.execute("SELECT * FROM locations ORDER BY id")]
    conn.close()

    def engine_id_for(block_name):
        want = _norm(block_name)
        for engine_id, name in engine_names.items():
            if _norm(name) == want or _norm(engine_id) == want:
                return engine_id
        return None

    carried_list = [_load_carried(p) for p in carried_paths]
    lines = ["Checkpoint — Turn %s" % carried_list[-1]["turn"]
             if carried_list else "Checkpoint"]
    lines.append("Tick %d | events %d | state %s | last swept turn %s"
                 % (tick, event_count, digest[:12], last_swept))
    drift = 0
    lines.append("")
    lines.append("Bonds (block value vs DB now):")
    # The latest carried value wins: the DB now should match the most
    # recent approved block, not the first one.
    bond_latest = {}
    for carried in carried_list:
        for bond in carried.get("bonds") or []:
            bond_latest[bond["engine"]] = bond["bond"]
    for name, value in bond_latest.items():
        engine_id = engine_id_for(name)
        now = db_bonds.get(engine_id) if engine_id else None
        status = "MATCH" if now == value else "DRIFT"
        if status == "DRIFT":
            drift += 1
        lines.append("  %s: block %d, DB now %s — %s"
                     % (name, value, now, status))
    lines.append("")
    lines.append("Clocks (block value vs DB now):")
    clock_latest = {}
    for carried in carried_list:
        for clock in carried.get("clocks") or []:
            clock_latest[clock["name"]] = clock
    for name, clock in clock_latest.items():
        row_id = clock_by_name.get(_norm(name))
        if row_id is None:
            lines.append("  %s: not in this world "
                         "(flagged at sweep)" % name)
            continue
        now = db_clocks[row_id]["value"]
        status = "MATCH" if now == clock["value"] else "DRIFT"
        if status == "DRIFT":
            drift += 1
        lines.append("  %s: block %d/%d, DB now %d/%d — %s"
                     % (name, clock["value"], clock["max"],
                        now, db_clocks[row_id]["max"], status))
    lines.append("")
    lines.append("Locations (current controllers):")
    for loc_id, controller in locations:
        lines.append("  %s: %s" % (loc_id, controller or "uncontrolled"))
    pending = None
    for carried in reversed(carried_list):
        if carried.get("pending_decision"):
            pending = carried["pending_decision"]
            break
    lines.append("")
    lines.append("Pending decision (verbatim): %s" % (pending or "none"))
    lines.append("")
    lines.append("Drift lines: %d" % drift)
    conn = sqlite3.connect("file:%s?mode=ro" % db_copy, uri=True)
    conn.row_factory = sqlite3.Row
    acceptance_lines, acceptance_failures = _acceptance(
        conn, db_copy, sweeps_dir, drift)
    conn.close()
    lines.extend(acceptance_lines)
    conn = sqlite3.connect("file:%s?mode=ro" % db_copy, uri=True)
    conn.row_factory = sqlite3.Row
    world_lines, _ = _world_state(conn, carried_list, seed_path)
    conn.close()
    lines.extend(world_lines)
    text = "\n".join(lines) + "\n"

    with open(os.path.join(out_dir, "audit.md"), "w") as f:
        f.write(text)
    summary = {
        "turn": carried_list[-1]["turn"] if carried_list else None,
        "tick": tick, "events": event_count,
        "state_hash": digest, "drift": drift,
        "acceptance": ("PASS" if acceptance_failures == 0 else "FAIL"),
        "acceptance_failures": acceptance_failures,
        "pending_decision": pending,
    }
    with open(os.path.join(out_dir, "state.json"), "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
    return text, drift
