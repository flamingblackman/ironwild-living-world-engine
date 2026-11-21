"""The tick loop. Rules first, LLM never.

One tick (1 in-world day), in fixed order:
  0. Clear last tick's flags. Apply the Feed burn (Engine Team's rate, from
     the seed's meta; logged only when Feed is actually consumed).
  1. Molted engines return to active.
  2. Every living engine's Hunger +1.
  3. Instinct: engines that can act (active / field-patched) at/above their
     Hunger threshold hunt alone (Feed +2 to their pilot's faction, or to
     the Pack when the Engine answers to the Pack collectively; Hunger set
     to 4). Exhausted engines do not go Instinct. The engine does not act
     again this tick.
  4. Every active NPC scores its legal actions and executes the best.
     No legal action -> a rest event.
  5. Engines act only if the catalog has engine actions (Fork A has none:
     the Pack's Engines are acted on, they do not act). When the catalog
     does have them, every engine that can act and did not go Instinct
     scores and executes; Bond 0 with no legal action logs refuse_to_move.
  6. Clock completions fire.
  7. Era boundary (tick % era_length == 0): legacy rules fire once.
  8. Snapshot every 10 ticks.

Determinism: a single random.Random seeded from the seed's rng_seed is
consumed in actor order. Same seed + same seed data -> same world.

Halts: an action carrying "halt_if" raises EngineHalt when its condition
holds (the engine stops and asks Lore instead of improvising). The halt
propagates out of run_ticks; the CLI reports it and exits non-zero.
"""

import json
import random

from . import actions
from . import clocks
from . import db
from . import eras
from . import events
from . import scoring
from . import seed as seed_mod
from . import targets

EngineHalt = eras.EngineHalt

ACTING_ENGINE_STATUSES = ("active", "field-patched")


def _placeholders(conn, actor):
    """Build the {self}/{pilot}/{bonded_engine}/{location}/{holder}/
    {faction} map for an actor."""
    mapping = {"self": actor["id"]}
    if actor["kind"] == "engine":
        row = conn.execute(
            "SELECT pilot_id, location_id FROM engines WHERE id = ?",
            (actor["id"],)
        ).fetchone()
        pilot = row["pilot_id"] if row else ""
        mapping["pilot"] = pilot or ""
        mapping["location"] = row["location_id"] if row else ""
        if pilot:
            f = conn.execute(
                "SELECT faction_id FROM npcs WHERE id = ?", (pilot,)
            ).fetchone()
            mapping["faction"] = f["faction_id"] if f else ""
            mapping["holder"] = mapping["faction"]
        else:
            mapping["faction"] = ""
            mapping["holder"] = "pack"
    else:
        row = conn.execute(
            "SELECT location_id, faction_id FROM npcs WHERE id = ?",
            (actor["id"],)
        ).fetchone()
        mapping["location"] = row["location_id"] if row else ""
        mapping["faction"] = row["faction_id"] if row else ""
        mapping["holder"] = mapping["faction"]
        brow = conn.execute(
            "SELECT engine_id FROM bonds WHERE pilot_id = ? LIMIT 1",
            (actor["id"],)
        ).fetchone()
        mapping["bonded_engine"] = brow["engine_id"] if brow else ""
    return mapping


def _substitute(obj, mapping):
    if isinstance(obj, str):
        for key, value in mapping.items():
            obj = obj.replace("{" + key + "}", value or "")
        return obj
    if isinstance(obj, list):
        return [_substitute(item, mapping) for item in obj]
    if isinstance(obj, dict):
        return {k: _substitute(v, mapping) for k, v in obj.items()}
    return obj


def _pick_action(rng, scored):
    """Pick the best action; break score ties with the seeded RNG."""
    if not scored:
        return None, None
    top = scored[0][0]
    tied = [action for score, action in scored if score == top]
    chosen = rng.choice(tied) if len(tied) > 1 else tied[0]
    runner_up = None
    rest = [s for s in scored if s[1]["id"] != chosen["id"]]
    if rest:
        runner_up = f"{rest[0][1]['id']}:{rest[0][0]}"
    return chosen, runner_up


def _act(conn, tick, rng, actor, catalog):
    mapping = _placeholders(conn, actor)
    catalog = _substitute(catalog, mapping)
    scored = scoring.score_actions(conn, actor, catalog)
    chosen, runner_up = _pick_action(rng, scored)
    if chosen is None:
        if actor["kind"] == "engine":
            bond = conn.execute(
                "SELECT bond FROM bonds WHERE engine_id = ?",
                (actor["id"],)).fetchone()
            if bond and bond["bond"] == 0:
                events.append_event(conn, tick, actor["id"],
                                    "refuse_to_move", None, None, [])
                return "refuse_to_move"
        events.append_event(conn, tick, actor["id"], "rest", None, None,
                            [{"op": "rest"}])
        return "rest"
    halt_if = chosen.get("halt_if")
    if halt_if is not None:
        from . import conditions
        if conditions.condition_holds(conn, halt_if):
            raise EngineHalt(chosen.get(
                "halt_message",
                f"action {chosen['id']} halted; Lore must decide."))
    effects = targets.resolve_targets(conn, chosen.get("effect") or [])
    applied = actions.apply_effects(
        conn, effects, tick=tick,
        allow_bond_increase=(chosen["id"] == "dream_share"))
    events.append_event(conn, tick, actor["id"], chosen["id"],
                        scored[0][0] if scored else None, runner_up, applied)
    return chosen["id"]


def _feed_burn(conn, tick):
    """The city and the Pack consume Feed every tick (Engine Team's rate,
    set in the seed's meta; Lore sets no canon burn rate). Logged only when
    Feed is actually consumed."""
    burn = json.loads(db.get_meta(conn, "feed_burn", "[]"))
    if not burn:
        return
    from . import resources
    applied = []
    for item in burn:
        used = resources.add_qty(conn, item["holder"], item["holder_kind"],
                                 "Feed", -item["qty"])
        if used < 0:
            applied.append({"op": "resource_add", "holder": item["holder"],
                            "holder_kind": item["holder_kind"],
                            "resource": "Feed", "qty": item["qty"],
                            "applied_qty": used})
    if applied:
        events.append_event(conn, tick, "city", "feed_burn", None, None,
                            applied)


def run_ticks(conn, n, rng=None, catalog=None, legacy=None, era_length=365):
    """Run n ticks. Returns the final tick number."""
    if rng is None:
        rng = random.Random(int(db.get_meta(conn, "rng_seed", 0)))
    if catalog is None:
        catalog = seed_mod.load_catalog(conn)
    if legacy is None:
        legacy = seed_mod.load_legacy(conn)
    era_length = int(db.get_meta(conn, "era_length", era_length))
    has_engine_actions = any(
        a.get("actor_kind") == "engine" for a in catalog)

    for _ in range(n):
        tick = db.get_tick(conn) + 1
        db.set_tick(conn, tick)

        try:
            _run_one_tick(conn, tick, rng, catalog, legacy, era_length,
                          has_engine_actions)
        except EngineHalt as exc:
            # The halt itself is logged, then the partial tick is committed
            # so the log shows what led to the stop. The halt propagates:
            # the run ends here and Lore must decide.
            events.append_event(conn, tick, "engine", "halt", None, None,
                                [{"op": "note", "text": str(exc)}])
            conn.commit()
            raise
        conn.commit()
    return db.get_tick(conn)


def _run_one_tick(conn, tick, rng, catalog, legacy, era_length,
                  has_engine_actions):
    """One tick of work, factored out so a halt can commit the partial log."""
    # 0. Clear last tick's flags; apply the Feed burn.
    conn.execute("DELETE FROM tick_flags WHERE tick < ?", (tick,))
    _feed_burn(conn, tick)

    # 1. Molted engines return to active.
    conn.execute("UPDATE engines SET status = 'active' "
                 "WHERE status = 'molted'")

    # 2. Hunger grows on every living engine.
    conn.execute("UPDATE engines SET hunger = MIN(10, hunger + 1) "
                 "WHERE status != 'dead'")

    # 3. Instinct: engines that can act, at threshold, hunt alone.
    instinct_engines = set()
    for eng in conn.execute(
            "SELECT id, pilot_id, hunger, hunger_threshold FROM engines "
            "WHERE status IN ('active', 'field-patched') "
            "AND hunger >= hunger_threshold ORDER BY id"
            ).fetchall():
        if eng["pilot_id"]:
            f = conn.execute(
                "SELECT faction_id FROM npcs WHERE id = ?",
                (eng["pilot_id"],)).fetchone()
            feed_holder = f["faction_id"] if f else "pack"
            feed_kind = "faction" if f and f["faction_id"] else "pack"
        else:
            feed_holder, feed_kind = "pack", "pack"
        applied = actions.apply_effects(conn, [
            {"op": "resource_add", "holder": feed_holder,
             "holder_kind": feed_kind, "resource": "Feed", "qty": 2},
            {"op": "hunger_set", "engine": eng["id"], "value": 4},
        ], tick=tick)
        events.append_event(conn, tick, eng["id"], "instinct_hunt",
                            None, None, applied)
        instinct_engines.add(eng["id"])

    # 4. NPCs act, in id order.
    for npc in conn.execute(
            "SELECT id FROM npcs WHERE status LIKE 'active%' "
            "ORDER BY id"
            ).fetchall():
        _act(conn, tick, rng, {"id": npc["id"], "kind": "npc"}, catalog)

    # 5. Engines act, only if the catalog has engine actions.
    if has_engine_actions:
        for eng in conn.execute(
                "SELECT id FROM engines WHERE status IN "
                "('active', 'field-patched') ORDER BY id"
                ).fetchall():
            if eng["id"] in instinct_engines:
                continue
            _act(conn, tick, rng, {"id": eng["id"], "kind": "engine"},
                 catalog)

    # 6. Clock completions.
    clocks.check_completions(conn, tick)

    # 7. Era boundary.
    if tick % era_length == 0:
        eras.apply_legacy(conn, tick, legacy)

    # 8. Snapshot every 10 ticks.
    if tick % 10 == 0:
        db.record_snapshot(conn, tick)


def verify_invariants(conn):
    """Check the rules that must hold after every tick.

    Returns a list of violation strings (empty means clean).
    """
    problems = []
    for row in conn.execute("SELECT * FROM resources WHERE qty < 0"):
        problems.append(f"negative resource: {dict(row)}")
    for row in conn.execute("SELECT * FROM bonds WHERE bond < 0 OR bond > 5"):
        problems.append(f"bond out of range: {dict(row)}")
    for row in conn.execute(
            "SELECT * FROM clocks WHERE value < 0 OR value > max"):
        problems.append(f"clock out of range: {dict(row)}")
    for row in conn.execute(
            "SELECT * FROM engines WHERE hunger < 0 OR hunger > 10"):
        problems.append(f"hunger out of range: {dict(row)}")
    ok, bad = events.verify_chain(conn)
    if not ok:
        problems.append(f"event hash chain broken at event {bad}")
    return problems
