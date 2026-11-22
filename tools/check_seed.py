"""Seed checker (no live state touched).

Usage: python3 tools/check_seed.py [seed.json ...]
Default: seed/fork-a.internal.json seed/fork-b.internal.json.

Findings (each is a defect or a likely defect in the seed):
  NEED_CLOCK_PRECONDITION: a `need` clause on clock X while the
    action's effect has a clock_add on the same clock X. The need is
    load-bearing for a zero-effect outcome: once the clock completes,
    the action still fires and burns its costs for nothing (Fork A
    fortify fired 454 times after great_basin_recovery completed,
    each burning 1 Salvage). Move the clause into `trigger`.
  MISSING_<KIND>: a trigger / need / effect reference to an id the
    seed does not define (clock, location, faction, engine, npc,
    resource). A missing clock makes the clause False, so the action
    is never legal (Fork B trade_concord's concord_blockade: 0 fires
    in 1,000 ticks).
Placeholders ({location}, {holder}, {self}) are substituted at
runtime and are never flagged. Effect-op `when` clauses are checked
the same way as trigger / need clauses. Clock on_complete effect
lists are checked too.

Exit 0 when clean, 1 when any finding is reported.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SEEDS = [os.path.join(ROOT, "seed", "fork-a.internal.json"),
                 os.path.join(ROOT, "seed", "fork-b.internal.json")]

# entity_kind -> seed section holding those ids
_ENTITY_TABLES = {"npc": "npcs", "engine": "engines",
                  "location": "locations"}


def _is_placeholder(value):
    return isinstance(value, str) and value.startswith("{") \
        and value.endswith("}")


def _check_condition(cond, ids, findings, where):
    """Recurse a trigger / need / when value, flagging bad references."""
    if isinstance(cond, list):
        for item in cond:
            _check_condition(item, ids, findings, where)
        return
    if not isinstance(cond, dict):
        return
    if "all" in cond:
        _check_condition(cond["all"], ids, findings, where)
    if "any" in cond:
        _check_condition(cond["any"], ids, findings, where)
    if "not" in cond:
        _check_condition(cond["not"], ids, findings, where)
    kind = cond.get("kind")
    if kind == "clock":
        clock_id = cond.get("id")
        if clock_id and not _is_placeholder(clock_id) \
                and clock_id not in ids["clocks"]:
            findings.append(
                "%s: MISSING_CLOCK: clock %r is not defined"
                % (where, clock_id))
    elif kind == "resource":
        holder = cond.get("holder")
        if cond.get("holder_kind") == "faction" and holder \
                and not _is_placeholder(holder) \
                and holder not in ids["factions"]:
            findings.append(
                "%s: MISSING_FACTION: holder %r is not defined"
                % (where, holder))
        resource = cond.get("resource")
        if resource and resource not in ids["resources"]:
            findings.append(
                "%s: MISSING_RESOURCE: resource %r is not defined"
                % (where, resource))
    elif kind in ("bond", "hunger"):
        engine = cond.get("engine")
        if engine and not _is_placeholder(engine) \
                and engine not in ids["engines"]:
            findings.append(
                "%s: MISSING_ENGINE: engine %r is not defined"
                % (where, engine))
    elif kind == "status":
        entity = cond.get("id")
        table = _ENTITY_TABLES.get(cond.get("entity_kind"))
        if entity and table and not _is_placeholder(entity) \
                and entity not in ids[table]:
            findings.append(
                "%s: MISSING_%s: id %r is not defined"
                % (where, cond.get("entity_kind", "").upper(), entity))
    elif kind in ("engine_present", "location_is"):
        location = cond.get("location")
        if location and not _is_placeholder(location) \
                and location not in ids["locations"]:
            findings.append(
                "%s: MISSING_LOCATION: location %r is not defined"
                % (where, location))
    elif kind == "actor_location":
        actor = cond.get("actor")
        if actor and actor != "{self}" and not _is_placeholder(actor) \
                and actor not in ids["npcs"]:
            findings.append(
                "%s: MISSING_NPC: actor %r is not defined"
                % (where, actor))
        location = cond.get("location")
        if location and not _is_placeholder(location) \
                and location not in ids["locations"]:
            findings.append(
                "%s: MISSING_LOCATION: location %r is not defined"
                % (where, location))
    elif kind == "engines_ready":
        location = cond.get("location")
        if location and not _is_placeholder(location) \
                and location not in ids["locations"]:
            findings.append(
                "%s: MISSING_LOCATION: location %r is not defined"
                % (where, location))


def _check_holder(holder, holder_kind, ids, findings, where):
    if holder_kind == "faction" and holder \
            and not _is_placeholder(holder) \
            and holder not in ids["factions"]:
        findings.append(
            "%s: MISSING_FACTION: holder %r is not defined"
            % (where, holder))


def _check_effect_op(op, ids, findings, where):
    if not isinstance(op, dict):
        return
    kind = op.get("op")
    if kind == "resource_add":
        _check_holder(op.get("holder"), op.get("holder_kind"),
                      ids, findings, where)
        resource = op.get("resource")
        if resource and resource not in ids["resources"]:
            findings.append(
                "%s: MISSING_RESOURCE: resource %r is not defined"
                % (where, resource))
    elif kind == "resource_move":
        _check_holder(op.get("from"), op.get("from_kind"),
                      ids, findings, where)
        _check_holder(op.get("to"), op.get("to_kind"),
                      ids, findings, where)
        resource = op.get("resource")
        if resource and resource not in ids["resources"]:
            findings.append(
                "%s: MISSING_RESOURCE: resource %r is not defined"
                % (where, resource))
    elif kind == "clock_add":
        clock_id = op.get("clock")
        if clock_id and not _is_placeholder(clock_id) \
                and clock_id not in ids["clocks"]:
            findings.append(
                "%s: MISSING_CLOCK: clock %r is not defined"
                % (where, clock_id))
    elif kind == "location_set":
        location = op.get("location")
        if isinstance(location, str) and not _is_placeholder(location) \
                and location not in ids["locations"]:
            findings.append(
                "%s: MISSING_LOCATION: location %r is not defined"
                % (where, location))
        controller = op.get("controller")
        if isinstance(controller, str) \
                and not _is_placeholder(controller) \
                and controller not in ids["factions"]:
            findings.append(
                "%s: MISSING_FACTION: controller %r is not defined"
                % (where, controller))
    elif kind == "status_set":
        entity = op.get("id")
        table = _ENTITY_TABLES.get(op.get("entity_kind"))
        if isinstance(entity, str) and table \
                and not _is_placeholder(entity) \
                and entity not in ids[table]:
            findings.append(
                "%s: MISSING_%s: id %r is not defined"
                % (where, op.get("entity_kind", "").upper(), entity))
    elif kind == "move":
        entity = op.get("id")
        table = _ENTITY_TABLES.get(op.get("entity_kind"))
        if isinstance(entity, str) and table \
                and not _is_placeholder(entity) \
                and entity not in ids[table]:
            findings.append(
                "%s: MISSING_%s: id %r is not defined"
                % (where, op.get("entity_kind", "").upper(), entity))
        location = op.get("location")
        if isinstance(location, str) and not _is_placeholder(location) \
                and location not in ids["locations"]:
            findings.append(
                "%s: MISSING_LOCATION: location %r is not defined"
                % (where, location))
    elif kind in ("bond_add", "molt_trigger_set"):
        engine = op.get("engine")
        if isinstance(engine, str) and not _is_placeholder(engine) \
                and engine not in ids["engines"]:
            findings.append(
                "%s: MISSING_ENGINE: engine %r is not defined"
                % (where, engine))
    elif kind == "standing_set":
        for key in ("faction", "other"):
            faction = op.get(key)
            if faction and not _is_placeholder(faction) \
                    and faction not in ids["factions"]:
                findings.append(
                    "%s: MISSING_FACTION: %s %r is not defined"
                    % (where, key, faction))
    if "when" in op:
        _check_condition(op["when"], ids, findings, where)


def _clock_ids_in_condition(cond):
    """Clock ids referenced anywhere inside a condition value."""
    found = set()
    if isinstance(cond, list):
        for item in cond:
            found |= _clock_ids_in_condition(item)
    elif isinstance(cond, dict):
        if cond.get("kind") == "clock" and cond.get("id"):
            found.add(cond["id"])
        for key in ("all", "any", "not"):
            if key in cond:
                found |= _clock_ids_in_condition(cond[key])
    return found


def check_seed(seed_data, seed_name="seed"):
    """Return a list of finding strings for one parsed seed dict."""
    ids = {
        "clocks": {c["id"] for c in seed_data.get("clocks", [])},
        "locations": {loc["id"] for loc in seed_data.get("locations", [])},
        "factions": {f["id"] for f in seed_data.get("factions", [])},
        "engines": {e["id"] for e in seed_data.get("engines", [])},
        "npcs": {n["id"] for n in seed_data.get("npcs", [])},
        "resources": {r["resource"]
                      for r in seed_data.get("resources", [])},
    }
    findings = []

    for clock in seed_data.get("clocks", []):
        where = "%s:clock:%s" % (seed_name, clock.get("id"))
        for op in clock.get("on_complete", []) or []:
            _check_effect_op(op, ids, findings, where)

    for npc in seed_data.get("npcs", []):
        location = npc.get("location")
        if location and not _is_placeholder(location) \
                and location not in ids["locations"]:
            findings.append(
                "%s:npc:%s: MISSING_LOCATION: location %r is not defined"
                % (seed_name, npc.get("id"), location))
        faction = npc.get("faction")
        if faction and not _is_placeholder(faction) \
                and faction not in ids["factions"]:
            findings.append(
                "%s:npc:%s: MISSING_FACTION: faction %r is not defined"
                % (seed_name, npc.get("id"), faction))

    for engine in seed_data.get("engines", []):
        location = engine.get("location")
        if location and not _is_placeholder(location) \
                and location not in ids["locations"]:
            findings.append(
                "%s:engine:%s: MISSING_LOCATION: location %r is not defined"
                % (seed_name, engine.get("id"), location))
        pilot = engine.get("pilot")
        if pilot and not _is_placeholder(pilot) \
                and pilot not in ids["npcs"]:
            findings.append(
                "%s:engine:%s: MISSING_NPC: pilot %r is not defined"
                % (seed_name, engine.get("id"), pilot))

    for loc in seed_data.get("locations", []):
        controller = loc.get("controller")
        if controller and not _is_placeholder(controller) \
                and controller not in ids["factions"]:
            findings.append(
                "%s:location:%s: MISSING_FACTION: controller %r "
                "is not defined"
                % (seed_name, loc.get("id"), controller))

    for action in seed_data.get("actions", []):
        where = "%s:action:%s" % (seed_name, action.get("id"))
        for actor_id in action.get("actor_ids", []) or []:
            if actor_id and not _is_placeholder(actor_id) \
                    and actor_id not in ids["npcs"]:
                findings.append(
                    "%s: MISSING_NPC: actor %r is not defined"
                    % (where, actor_id))
        _check_condition(action.get("trigger"), ids, findings, where)
        _check_condition(action.get("need"), ids, findings, where)
        effect = action.get("effect", []) or []
        for op in effect:
            _check_effect_op(op, ids, findings, where)
        # NEED_CLOCK_PRECONDITION: a need clause on clock X while the
        # effect advances the same clock X. Once X completes, the
        # action still fires and burns its costs for nothing.
        need_clocks = _clock_ids_in_condition(action.get("need"))
        effect_clocks = {op.get("clock") for op in effect
                         if isinstance(op, dict)
                         and op.get("op") == "clock_add"
                         and op.get("clock")}
        for clock_id in sorted(need_clocks & effect_clocks):
            findings.append(
                "%s: NEED_CLOCK_PRECONDITION: need references clock "
                "%r and the effect advances the same clock; move the "
                "clause into trigger" % (where, clock_id))

    return findings


def main(argv=None):
    paths = list(argv) if argv else DEFAULT_SEEDS
    all_findings = []
    for path in paths:
        with open(path) as f:
            seed_data = json.load(f)
        findings = check_seed(seed_data, os.path.basename(path))
        for finding in findings:
            print(finding)
        all_findings.extend(findings)
    if all_findings:
        print("%d finding(s)" % len(all_findings))
        return 1
    print("clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
