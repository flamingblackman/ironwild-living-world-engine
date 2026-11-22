"""Step 0 audit simulation (no live state touched).

Seeds a FRESH world from seed/<seed-file> (default
fork-a.internal.json; pass e.g. fork-b.internal.json as argv[2]),
runs N continuous ticks in one run_ticks call (default 1000), then
analyzes the event log for the audit items that need evidence, not
opinion. A fresh seed defaults to rng_scheme v2, so the passed rng
is ignored under v2 (the per-actor streams govern); the report
records the fork and the scheme actually used.
  8  raid quantification (creation from nothing on clamp)
  11 patrol vs raid ordering and blocked-note truth
  12 dead content (clocks, Territory/Cores, concord_camp flag, evacuate)
  13 storyline exhaustion tick
  14 skipped ops in the log (esp. raid blocked-notes beside applied gains)
Writes runs/audit-step0/report.json and prints a human summary.
"""

import collections
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import db, seed as seed_mod, tick as tick_mod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
SEED_FILE = sys.argv[2] if len(sys.argv) > 2 else "fork-a.internal.json"
FORK = SEED_FILE.replace(".internal.json", "")
# Fork A keeps its original output dir (the recorded reports live
# there); other forks get a subdir so nothing is overwritten.
OUT = os.path.join(ROOT, "runs", "audit-step0")
if FORK != "fork-a":
    OUT = os.path.join(OUT, FORK)
DB = os.path.join(OUT, "sim-%d.sqlite" % N)
REPORT = os.path.join(OUT, "report-%d.json" % N)


def main():
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(DB):
        os.remove(DB)
    with open(os.path.join(ROOT, "seed", SEED_FILE)) as f:
        seed_data = json.load(f)
    conn = db.connect(DB)
    db.init_schema(conn)
    seed_mod.load_seed(conn, seed_data)
    init_res = {(r["holder_id"], r["holder_kind"], r["resource"]): r["qty"]
                for r in conn.execute("SELECT * FROM resources")}
    init_clocks = {r["id"]: (r["value"], r["status"])
                   for r in conn.execute("SELECT * FROM clocks")}
    init_locs = {r["id"]: (r["controller_faction_id"], r["status"],
                           r["mapped"])
                 for r in conn.execute("SELECT * FROM locations")}
    rng = random.Random(int(db.get_meta(conn, "rng_seed", 0)))
    tick_mod.run_ticks(conn, N, rng=rng)
    problems = tick_mod.verify_invariants(conn)

    rows = conn.execute(
        "SELECT id, tick, actor_id, action, score, runner_up, effect "
        "FROM events ORDER BY id").fetchall()
    evs = []
    for r in rows:
        evs.append({"id": r["id"], "tick": r["tick"],
                    "actor": r["actor_id"], "action": r["action"],
                    "effect": json.loads(r["effect"])})

    rep = {"fork": FORK, "ticks": N, "events": len(evs),
           "rng_scheme": db.get_meta(conn, "rng_scheme", "v1"),
           "invariants": problems,
           "final_tick": db.get_tick(conn)}
    rep["action_counts"] = dict(collections.Counter(
        e["action"] for e in evs))

    # --- 8: raids ---
    raids = [e for e in evs if e["action"] in ("raid_captain", "raid_chief")]
    raid_rows = []
    created_salvage = 0
    fully_clamped = 0
    partially_clamped = 0
    for e in raids:
        feed_applied = None
        salv_applied = None
        notes = []
        for op in e["effect"]:
            if op.get("op") == "resource_add" and op.get("resource") == "Feed":
                feed_applied = op.get("applied_qty")
            if op.get("op") == "resource_add" and op.get("resource") == "Salvage":
                salv_applied = op.get("applied_qty")
            if op.get("op") == "note":
                notes.append({"text": op.get("text"),
                              "skipped": bool(op.get("skipped"))})
        # creation = salvage gained while feed taken < 2 (clamped)
        taken = abs(feed_applied) if feed_applied is not None else 0
        gained = salv_applied if salv_applied is not None else 0
        if feed_applied == 0:
            fully_clamped += 1
        elif feed_applied == -1:
            partially_clamped += 1
        if gained > taken:
            created_salvage += gained - taken
        raid_rows.append({"event": e["id"], "tick": e["tick"],
                          "action": e["action"], "feed_applied": feed_applied,
                          "salv_applied": salv_applied, "notes": notes})
    rep["raids"] = {"count": len(raids),
                    "fully_clamped_feed0": fully_clamped,
                    "partially_clamped_feed1": partially_clamped,
                    "salvage_created_from_nothing": created_salvage,
                    "rows": raid_rows}

    # --- 11: patrol vs raid ---
    patrols = [e for e in evs if e["action"] == "patrol"]
    blocked_notes_applied = 0
    blocked_notes_skipped = 0
    for e in evs:
        for op in e["effect"]:
            if op.get("op") == "note" and "raid blocked" in (op.get("text") or ""):
                if op.get("skipped"):
                    blocked_notes_skipped += 1
                else:
                    blocked_notes_applied += 1
    # ticks where both a raid and a patrol fired: show event order
    raid_patrol_ticks = []
    by_tick = collections.defaultdict(list)
    for e in evs:
        by_tick[e["tick"]].append(e)
    for t, tes in sorted(by_tick.items()):
        acts = [e["action"] for e in tes]
        if any(a in ("raid_captain", "raid_chief") for a in acts) \
                and "patrol" in acts:
            raid_patrol_ticks.append({
                "tick": t,
                "raid_event": next(e["id"] for e in tes
                                   if e["action"] in ("raid_captain", "raid_chief")),
                "patrol_event": next(e["id"] for e in tes
                                     if e["action"] == "patrol")})
    rep["patrol"] = {"patrol_events": len(patrols),
                     "blocked_notes_applied": blocked_notes_applied,
                     "blocked_notes_skipped": blocked_notes_skipped,
                     "ticks_with_raid_and_patrol": raid_patrol_ticks}

    # --- 12: dead content ---
    fin_clocks = {r["id"]: (r["value"], r["status"])
                  for r in conn.execute("SELECT * FROM clocks")}
    fin_res = {(r["holder_id"], r["holder_kind"], r["resource"]): r["qty"]
               for r in conn.execute("SELECT * FROM resources")}
    terr_cores_changed = {k: (init_res.get(k), fin_res.get(k))
                          for k in init_res
                          if k[2] in ("Territory", "Cores")
                          and init_res.get(k) != fin_res.get(k)}
    rep["dead_content"] = {
        "clocks_initial": {k: list(v) for k, v in init_clocks.items()},
        "clocks_final": {k: list(v) for k, v in fin_clocks.items()},
        "territory_cores_changed": terr_cores_changed,
        "evacuate_events": sum(1 for e in evs if e["action"] == "evacuate"),
        "pack_merge_events": sum(1 for e in evs if e["action"] == "pack_merge"),
    }

    # --- 13: storyline exhaustion ---
    last_clock_advance = 0
    last_completion = 0
    last_controller_change = 0
    last_raid_gain = 0
    last_status_change = 0
    last_claim = 0
    for e in evs:
        if e["action"] == "complete":
            last_completion = max(last_completion, e["tick"])
        for op in e["effect"]:
            if op.get("skipped"):
                continue
            if op.get("op") == "clock_add" and (op.get("applied_qty") or 0) > 0:
                last_clock_advance = max(last_clock_advance, e["tick"])
            if op.get("op") == "location_set" and "controller" in op:
                old = op.get("old_controller")
                if old != op.get("controller"):
                    last_controller_change = max(last_controller_change, e["tick"])
            if op.get("op") == "resource_add" and op.get("resource") == "Salvage" \
                    and (op.get("applied_qty") or 0) > 0 \
                    and e["action"] in ("raid_captain", "raid_chief"):
                last_raid_gain = max(last_raid_gain, e["tick"])
            if op.get("op") == "status_set" and op.get("old_status") != op.get("status"):
                last_status_change = max(last_status_change, e["tick"])
        if e["action"].startswith("claim"):
            last_claim = max(last_claim, e["tick"])
    storyline = {"last_clock_advance": last_clock_advance,
                 "last_clock_completion": last_completion,
                 "last_controller_change": last_controller_change,
                 "last_raid_gain": last_raid_gain,
                 "last_status_change": last_status_change,
                 "last_claim": last_claim}
    storyline["exhaustion_tick"] = max(storyline.values())
    rep["storyline"] = storyline

    # --- 14: skipped ops ---
    skipped = []
    for e in evs:
        for op in e["effect"]:
            if op.get("skipped"):
                skipped.append({"event": e["id"], "tick": e["tick"],
                                "action": e["action"],
                                "op": op.get("op"),
                                "text": op.get("text"),
                                "reason": op.get("reason")})
    rep["skipped_ops"] = {"count": len(skipped), "rows": skipped[:40]}
    # raid events where applied gains coexist with a skipped blocked note
    mixed = 0
    for e in raids:
        has_gain = any(op.get("op") == "resource_add"
                       and (op.get("applied_qty") or 0) != 0
                       and not op.get("skipped") for op in e["effect"])
        has_skipped_note = any(op.get("op") == "note"
                               and op.get("skipped") for op in e["effect"])
        if has_gain and has_skipped_note:
            mixed += 1
    rep["skipped_ops"]["raid_events_with_gain_and_skipped_note"] = mixed

    # final locations for the fortification question
    fin_locs = {r["id"]: (r["controller_faction_id"], r["status"],
                          r["mapped"])
                for r in conn.execute("SELECT * FROM locations")}
    rep["locations_final"] = {k: list(v) for k, v in fin_locs.items()}
    rep["locations_initial"] = {k: list(v) for k, v in init_locs.items()}

    # --- 16: significant events per 100 ticks + action lifetimes ---
    # Significant = a clock advance (applied>0), a clock completion, a
    # location controller change, a raid Salvage gain, an engine status
    # change, or an effective claim. Routine economy (hunt, trade, rest,
    # feed, tend, patrol, no-op fortify) does not count.
    def _significant(e):
        if e["action"] == "complete":
            return True
        for op in e["effect"]:
            if op.get("skipped"):
                continue
            if op.get("op") == "clock_add" and (op.get("applied_qty") or 0) > 0:
                return True
            if op.get("op") == "location_set" and "controller" in op \
                    and op.get("old_controller") != op.get("controller"):
                return True
            if op.get("op") == "resource_add" and op.get("resource") == "Salvage" \
                    and (op.get("applied_qty") or 0) > 0 \
                    and e["action"] in ("raid_captain", "raid_chief"):
                return True
            if op.get("op") == "status_set" and op.get("old_status") != op.get("status"):
                return True
        return False
    buckets = []
    for start in range(0, N, 100):
        window = [e for e in evs if start < e["tick"] <= start + 100]
        buckets.append({"ticks": "%d-%d" % (start + 1, start + 100),
                        "events": len(window),
                        "significant": sum(1 for e in window if _significant(e))})
    rep["significant_per_100"] = buckets
    last_fired = {}
    for e in evs:
        last_fired[e["action"]] = max(last_fired.get(e["action"], 0), e["tick"])
    seed_actions = [a["id"] for a in seed_data.get("actions", [])]
    rep["action_lifetimes"] = {
        "never_fired": [a for a in seed_actions if a not in last_fired],
        "last_fired_tick": last_fired,
        "fired_in_last_100": sorted(a for a, t in last_fired.items()
                                     if t > N - 100),
        "stopped_firing": sorted((a, t) for a, t in last_fired.items()
                                 if t <= N - 100),
    }
    rep["clocks_completed"] = [
        {"tick": e["tick"], "clock": e["actor"]}
        for e in evs if e["action"] == "complete"]

    with open(REPORT, "w") as f:
        json.dump(rep, f, indent=2, sort_keys=True)
    conn.close()
    print(json.dumps({k: rep[k] for k in
                      ("ticks", "events", "invariants", "final_tick",
                       "action_counts", "storyline")}, indent=2))
    print("RAIDS:", json.dumps({k: v for k, v in rep["raids"].items()
                                if k != "rows"}))
    print("PATROL:", json.dumps({k: v for k, v in rep["patrol"].items()
                                 if k != "ticks_with_raid_and_patrol"}),
          "raid+patrol ticks:", len(rep["patrol"]["ticks_with_raid_and_patrol"]))
    print("SKIPPED OPS:", rep["skipped_ops"]["count"],
          "| raid gain+skipped-note events:",
          rep["skipped_ops"]["raid_events_with_gain_and_skipped_note"])
    print("SIGNIFICANT PER 100:", json.dumps(rep["significant_per_100"]))
    print("NEVER FIRED:", rep["action_lifetimes"]["never_fired"])
    print("CLOCKS COMPLETED:", json.dumps(rep["clocks_completed"]))
    print("report written to", REPORT)


if __name__ == "__main__":
    main()
