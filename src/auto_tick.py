"""Daily auto tick (Phase 2 item 1).

A scheduled runner that ticks the world once per day, headless, with
no narration and no render until the end. One tick is one in-world
day, so one tick per day keeps world time in step with real time.

World: Fork A only, until the live world exists (Bryan resolves Turn
136 and Lore supplies a live seed). The live world starts auto-ticking
only then.

Guards — before every scheduled tick the runner refuses (a refused
tick is a normal outcome, not an error) when:
- a session is open (`state/session.json`), or
- a pending player decision is recorded in the DB (`meta
  pending_decision`, set by the sweep at apply time), or
- the world already ticked today (`meta last_auto_tick_date`).

The pending-decision guard is the approved plan's guard, taken as
written. Its consequence is real: a turn that ends with an open
decision freezes the world until the next turn resolves it. Whether
that is what Bryan wants — or whether the guard should narrow to the
Turn 136 freeze only — is a hub question, reported with the build.
The runner logs the guard state every run either way, so the question
can be answered from the log.

No catch-up ticks: a missed day is a quiet day, and the log says so.
The runner ticks exactly once per invocation, and at most once per
day per world.

RNG: one scheme for every driver (rng_scheme in the DB). Under v1
the runner seeds Random(seed + tick) and the manual `tick` command
re-seeds from rng_seed on every run — two schemes, and the v1
runner's seed+tick collides (seed 5 tick 3 = seed 3 tick 5).
Under v2 the per-actor streams in tick.rng_for govern and the
passed rng is ignored, so the daily tick and the manual tick
produce the same world from the same seed.

The runner never calls an LLM and never touches the live Turn 136
scene. Each run writes `runs/auto/<date>/tick.log` (outcome, tick,
event count, state hash, refusal reason) and, on a successful tick,
`runs/auto/<date>/world-view.html`.
"""

import datetime
import os
import random

from src import db, events, render, session as session_mod, tick as tick_mod

RUNS_DIR = os.path.join(os.path.dirname(__file__), "..", "runs", "auto")


def run_auto_tick(db_path, today=None, flag_path=None):
    """Tick the world once for `today` (ISO date, default today).

    Returns a dict: {outcome, tick, events_before, events_after,
    state_hash, reason}. outcome is "ticked", "refused", or "halted".
    """
    today = today or datetime.date.today().isoformat()
    conn = db.connect(db_path)
    try:
        reason = session_mod.refuse_reason(flag_path) if flag_path else None
        if reason:
            return _refuse(conn, today, "session_open", reason)
        pending = db.get_meta(conn, "pending_decision")
        if pending:
            return _refuse(
                conn, today, "pending_decision",
                "a player decision is pending: %s" % pending[:120])
        if db.get_meta(conn, "last_auto_tick_date") == today:
            return _refuse(conn, today, "already_ticked_today",
                           "the world already ticked on %s" % today)
        tick_before = db.get_tick(conn)
        events_before = events.count_events(conn)
        seed = int(db.get_meta(conn, "rng_seed", 0))
        rng = random.Random(seed + tick_before + 1)
        try:
            final = tick_mod.run_ticks(conn, 1, rng=rng)
        except tick_mod.EngineHalt as exc:
            result = {"outcome": "halted", "tick": db.get_tick(conn),
                      "events_before": events_before,
                      "events_after": events.count_events(conn),
                      "state_hash": db.state_hash(conn),
                      "reason": str(exc)}
            _write_log(today, result)
            return result
        problems = tick_mod.verify_invariants(conn)
        db.record_snapshot(conn, final)
        db.set_meta(conn, "last_auto_tick_date", today)
        conn.commit()
        result = {"outcome": "ticked", "tick": final,
                  "events_before": events_before,
                  "events_after": events.count_events(conn),
                  "state_hash": db.state_hash(conn),
                  "reason": ("; ".join(problems) if problems else None),
                  "problems": problems}
        _write_log(today, result)
        render.render_world_view(
            conn, os.path.join(RUNS_DIR, today, "world-view.html"))
        return result
    finally:
        conn.close()


def _refuse(conn, today, code, reason):
    result = {"outcome": "refused", "tick": db.get_tick(conn),
              "events_before": events.count_events(conn),
              "events_after": events.count_events(conn),
              "state_hash": db.state_hash(conn),
              "reason": "%s: %s" % (code, reason)}
    _write_log(today, result)
    return result


def _write_log(today, result):
    day_dir = os.path.join(RUNS_DIR, today)
    os.makedirs(day_dir, exist_ok=True)
    with open(os.path.join(day_dir, "tick.log"), "a") as f:
        f.write("%s outcome=%s tick=%s events=%s->%s state=%s%s\n"
                % (today, result["outcome"], result["tick"],
                   result["events_before"], result["events_after"],
                   result["state_hash"][:12],
                   (" reason=" + result["reason"])
                   if result.get("reason") else ""))
