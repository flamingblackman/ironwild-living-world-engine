"""Lore seed adapter: translate the Lore Team's prose seed (fork-a.json)
into the engine's internal machine seed.

The Lore catalog is written in prose (actor lists, trigger sentences,
effect paragraphs). This adapter is the ONLY place prose becomes machine
clauses and effect ops. It never invents canon: every interpretation is
recorded in ADAPTER_NOTES and in seed/fork-a.adapter-notes.md, so Lore can
challenge any of it. If a rule cannot be translated faithfully, the adapter
raises instead of guessing.

Usage:
  python3 -m src.lore_seed --in seed/fork-a.json \
      --out seed/fork-a.internal.json --notes seed/fork-a.adapter-notes.md
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NOTES = []


def note(text):
    NOTES.append(text)


# ---------------------------------------------------------------------------
# Validation: the fork must not contain what the freeze and drift rules forbid.
# ---------------------------------------------------------------------------

FORBIDDEN = [
    (r"krov", "Krov / Turn 136 scene"),
    (r"turn 136", "Turn 136"),
    (r"rift-king", "Rift-King (dead; must not return)"),
    (r"den boss", "Den Boss (dead; must not return)"),
    (r"deepmaw migration", "Deepmaw migration destination (open mystery)"),
    (r"first seed core", "Seed Core origins (open mystery)"),
    (r"seed core origin", "Seed Core origins (open mystery)"),
]

SEQUEL_CLOCK_NAMES = {
    "Rider Army Mustering",
    "Sanctuary Integration",
    "Mother-Bulwark Rescue",
    "Outer Siege-Ring",
    "Northern Pass Approach",
}


def validate(lore):
    meta = lore["meta"]
    if "Turn 131" not in meta["source_snapshot"]:
        raise ValueError("seed source must be Turn 131 vFINAL")
    if "Turn 136" in meta["source_snapshot"] or "Krov" in meta["source_snapshot"]:
        raise ValueError("seed source must never be Turn 136 / Krov (freeze)")
    for clock in lore["clocks"]:
        if clock["name"] in SEQUEL_CLOCK_NAMES:
            raise ValueError(f"sequel clock in fork: {clock['name']}")
    # Only the executable state is scanned: actions, clocks, era, actors,
    # engines, bonds, locations, resources, factions. The snapshot is
    # provenance (it records resolved clocks and carried drift flags by
    # name); the manifest's exclusion list and drift rules name the
    # forbidden items on purpose and are not state either.
    blob = json.dumps({k: v for k, v in lore.items()
                       if k in ("actions", "clocks", "era", "actors",
                                "engines", "bonds", "locations", "resources",
                                "factions")})
    for pattern, label in FORBIDDEN:
        if re.search(pattern, blob, re.IGNORECASE):
            raise ValueError(f"forbidden content in seed state: {label}")
    note("Validation passed: source is Turn 131 vFINAL; no sequel clock, "
         "no Krov, no Rift-King, no Den Boss, no open-mystery answer in "
         "the state sections. (The freeze declaration, exclusion list, "
         "and drift rules name these items on purpose; they are not state.)")


# ---------------------------------------------------------------------------
# Condition helpers
# ---------------------------------------------------------------------------

def res(holder, holder_kind, resource, op, value):
    return {"kind": "resource", "holder": holder, "holder_kind": holder_kind,
            "resource": resource, "op": op, "value": value}


def clk(clock_id, op, value):
    return {"kind": "clock", "id": clock_id, "op": op, "value": value}


def not_cond(cond):
    return {"not": cond}


def fortified(location):
    return {"kind": "status", "entity_kind": "location", "id": location,
            "value": "fortified"}


def patrolled(location):
    return {"kind": "flag", "flag": f"patrolled:{location}", "present": True}


def raid_open(location):
    """A raid lands only when the target is neither fortified nor patrolled."""
    return {"all": [not_cond(fortified(location)),
                    not_cond(patrolled(location))]}


# ---------------------------------------------------------------------------
# Action translations (seed prose -> machine catalog)
# ---------------------------------------------------------------------------

PACK_ACTORS = ["brigus", "vance", "tull", "kaelen", "nest_keeper"]
ALL_ACTORS = PACK_ACTORS + ["caravan_master", "high_baron",
                            "dust_baron_captain", "breaker_poacher_chief",
                            "legion_captain"]


def _base(action_id, actor_ids):
    return {"id": action_id, "actor_kind": "npc", "actor_ids": actor_ids,
            "weight": 5, "goal_tags": [], "trigger": [{"kind": "always"}],
            "need": [], "effect": []}


def _hunt():
    a = _base("hunt", PACK_ACTORS)
    a["trigger"] = {"any": [
        [{"kind": "engine_present", "location": "{location}",
          "min_hunger": 3}],
        [{"kind": "location_is", "location": "{location}",
          "loc_kind": "wreck", "mapped": True}],
    ]}
    a["need"] = [res("pack", "pack", "Feed", "<", 3)]
    a["effect"] = [
        {"op": "resource_add", "holder": "pack", "holder_kind": "pack",
         "resource": "Feed", "qty": 2},
        {"op": "hunger_add",
         "engine": {"target": "engine_at_location",
                    "location": "{location}", "prefer": "highest_hunger",
                    "min_hunger": 0},
         "qty": -2},
    ]
    note("hunt (v1.5, Bryan's call, combined fix options 1 + 3): the "
         "hunt feeds the Pack — Feed +2 goes to the pack holder, not "
         "the actor's faction. v1.0-v1.4 routed it to the actor's holder "
         "(the Legion for four hunters, the Nest-Keepers for the "
         "Nest-Keeper), which starved the Pack's Feed pool and left "
         "Dream Share's Bond branch unable to fire. The need follows "
         "the pool it fills: the hunt scores higher while Pack Feed is "
         "below 3. The hunting Engine is the neediest Engine at the "
         "actor's location (shared pool; no pilot beyond Brigus-Sledge). "
         "If no Engine is present, the hunger op is skipped and only "
         "the Feed gain lands. Trigger is the seed's OR: an Engine at "
         "Hunger >= 3, or the actor's location is a mapped wreck. "
         "NOTE — Instinct hunts (tick step 3) still feed the pilot's "
         "faction per the plan's rule (Sledge's Instinct hunts feed the "
         "Legion); the seed changed the hunt action only, so the engine "
         "does not reroute Instinct on its own. Lore may decide that in "
         "a later seed; the rerun measures how much Legion Feed still "
         "comes from Instinct.")
    return a


def _feed_engine():
    a = _base("feed_engine", PACK_ACTORS)
    a["trigger"] = {"all": [
        res("{holder}", "faction", "Feed", ">=", 1),
        {"kind": "engine_present", "location": "{location}",
         "min_hunger": 1},
    ]}
    a["need"] = [{"kind": "engine_present", "location": "{location}",
                  "min_hunger": 4}]
    a["effect"] = [
        {"op": "resource_add", "holder": "{holder}", "holder_kind": "faction",
         "resource": "Feed", "qty": -1},
        {"op": "hunger_add",
         "engine": {"target": "engine_at_location",
                    "location": "{location}", "prefer": "highest_hunger",
                    "min_hunger": 1},
         "qty": -2},
    ]
    note("feed_engine: 'Holder' is the actor's faction (Legion for Pack "
         "actors, Nest-Keepers for the Nest-Keeper). No Bond change, per "
         "the seed (DC-06: Bond never increases).")
    return a


def _repair_engine():
    a = _base("repair_engine", ["vance"])
    a["trigger"] = {"all": [
        {"kind": "engine_present", "location": "{location}",
         "status_in": ["netted", "exhausted", "damaged"]},
        {"any": [res("ironwild_legion", "faction", "Salvage", ">=", 1),
                 res("pack", "pack", "Salvage", ">=", 1)]},
    ]}
    a["need"] = [{"kind": "engine_present", "location": "{location}",
                  "status_in": ["netted"]}]
    a["effect"] = [
        {"op": "resource_add", "holder": "ironwild_legion",
         "holder_kind": "faction", "resource": "Salvage", "qty": -1,
         "when": res("ironwild_legion", "faction", "Salvage", ">=", 1)},
        {"op": "resource_add", "holder": "pack", "holder_kind": "pack",
         "resource": "Salvage", "qty": -1,
         "when": {"all": [res("ironwild_legion", "faction", "Salvage",
                              "<", 1),
                          res("pack", "pack", "Salvage", ">=", 1)]}},
        {"op": "status_set", "entity_kind": "engine",
         "id": {"target": "engine_at_location", "location": "{location}",
                "prefer": "status_order",
                "status_in": ["netted", "exhausted", "damaged"]},
         "status": "field-patched"},
        {"op": "clock_add", "clock": "great_basin_recovery", "qty": 1,
         "when": {"kind": "actor_location", "actor": "{self}",
                  "location": "great_basin"}},
    ]
    note("repair_engine: Salvage is paid by the Legion first, the Pack "
         "only when the Legion holds none. The repaired Engine is the "
         "worst-status one at Vance's location (netted first, then "
         "exhausted, then damaged). It also ticks the Recovery clock, "
         "because the clock's trigger names repair_engine in Great Basin.")
    return a


def _scout_wreck():
    a = _base("scout_wreck", ["tull", "vance", "nest_keeper",
                              "dust_baron_captain", "breaker_poacher_chief"])
    a["trigger"] = [{"kind": "unmapped_exists"}]
    a["need"] = [res("{holder}", "faction", "Salvage", "<", 3)]
    a["effect"] = [
        {"op": "location_set",
         "location": {"target": "unmapped_location"}, "mapped": 1},
        {"op": "resource_add", "holder": "{holder}", "holder_kind": "faction",
         "resource": "Salvage", "qty": 1},
    ]
    note("scout_wreck: the mapped location is the lowest-id unmapped one "
         "(Leviathan's Ribs before Northern Trench).")
    return a


def _trade():
    out = []
    a = _base("trade_concord", ["caravan_master"])
    a["trigger"] = {"all": [
        clk("concord_blockade", "<", 6),
        res("caravan_concord", "faction", "Feed", ">=", 2),
        res("ironwild_legion", "faction", "Salvage", ">=", 2),
    ]}
    a["need"] = [res("{holder}", "faction", "Salvage", "<", 3)]
    a["effect"] = [
        {"op": "resource_move", "from": "caravan_concord",
         "from_kind": "faction", "to": "ironwild_legion",
         "to_kind": "faction", "resource": "Feed", "qty": 2},
        {"op": "resource_move", "from": "ironwild_legion",
         "from_kind": "faction", "to": "caravan_concord",
         "to_kind": "faction", "resource": "Salvage", "qty": 2},
    ]
    out.append(a)
    b = _base("trade_kaelen", ["kaelen"])
    b["trigger"] = {"all": [
        clk("concord_blockade", "<", 6),
        res("ironwild_legion", "faction", "Feed", ">=", 2),
        res("caravan_concord", "faction", "Salvage", ">=", 2),
    ]}
    b["need"] = [res("{holder}", "faction", "Salvage", "<", 3)]
    b["effect"] = [
        {"op": "resource_move", "from": "ironwild_legion",
         "from_kind": "faction", "to": "caravan_concord",
         "to_kind": "faction", "resource": "Feed", "qty": 2},
        {"op": "resource_move", "from": "caravan_concord",
         "from_kind": "faction", "to": "ironwild_legion",
         "to_kind": "faction", "resource": "Salvage", "qty": 2},
    ]
    out.append(b)
    note("trade: one seed action, two machine actions, because the "
         "counterparty differs by actor (Master trades with the Legion, "
         "Kaelen with the Concord). The Blockade clock below 6 is the "
         "road-open check; when it completes, trade stops by itself.")
    return out


def _raid_captain():
    a = _base("raid_captain", ["dust_baron_captain"])
    a["trigger"] = [clk("dust_baron_retaliation", "<", 6)]
    a["need"] = [res("dust_baron_remnants", "faction", "Salvage", "<", 3)]
    a["effect"] = [
        {"op": "resource_add", "holder": "ironwild_legion",
         "holder_kind": "faction", "resource": "Feed", "qty": -2,
         "when": raid_open("great_basin")},
        {"op": "resource_add", "holder": "dust_baron_remnants",
         "holder_kind": "faction", "resource": "Salvage", "qty": 2,
         "when": raid_open("great_basin")},
        {"op": "clock_add", "clock": "dust_baron_retaliation", "qty": 1,
         "when": raid_open("great_basin")},
        {"op": "flag_set", "flag": "raid_in_progress:great_basin"},
        {"op": "note", "text": "raid blocked: Great Basin fortified",
         "when": fortified("great_basin")},
        {"op": "note", "text": "raid blocked: Great Basin patrolled",
         "when": patrolled("great_basin")},
    ]
    note("raid (Captain): the target is Great Basin / the Legion. The "
         "raid is always attempted; fortified or patrolled means it lands "
         "as a logged blocked attempt with no quantities changed (the "
         "patrol effect promises the blocked log). The Retaliation clock "
         "ticks only when a raid LANDS.")
    return a


def _raid_chief():
    a = _base("raid_chief", ["breaker_poacher_chief"])
    a["trigger"] = [{"kind": "always"}]
    a["need"] = [res("breakers", "faction", "Salvage", "<", 3)]
    a["effect"] = [
        {"op": "resource_add", "holder": "ironwild_legion",
         "holder_kind": "faction", "resource": "Feed", "qty": -2,
         "when": raid_open("great_basin")},
        {"op": "resource_add", "holder": "breakers",
         "holder_kind": "faction", "resource": "Salvage", "qty": 2,
         "when": raid_open("great_basin")},
        {"op": "flag_set", "flag": "raid_in_progress:great_basin"},
        {"op": "note", "text": "raid blocked: Great Basin fortified",
         "when": fortified("great_basin")},
        {"op": "note", "text": "raid blocked: Great Basin patrolled",
         "when": patrolled("great_basin")},
    ]
    note("raid (Chief): BRYAN'S CALL, 2026-11-20 23:31 EST via the hub — "
         "the Chief's raid target is Great Basin, like the Captain's, "
         "not Concord Camp. The raid takes Legion Feed and Breakers "
         "Salvage, and sets the Great Basin raid flag. No clock ticks "
         "on a Chief raid (the Retaliation clock is the Captain's). "
         "The evacuate halt can still fire if any raid ever flags "
         "Concord Camp itself.")
    return a


def _net_ambush():
    a = _base("net_ambush", ["breaker_poacher_chief"])
    a["trigger"] = [{"kind": "engine_present", "location": "{location}"}]
    a["need"] = []
    a["effect"] = [
        {"op": "status_set", "entity_kind": "engine",
         "id": {"target": "engine_at_location", "location": "{location}",
                "prefer": "id"},
         "status": "netted"},
    ]
    note("net_ambush: trigger is an Engine at the Chief's location "
         "(Chalk Canyons). The seed's 'or on the road' branch has no "
         "location row to check, so only the Chalk Canyons branch is "
         "machine-checkable. No Engine starts there and none moves in "
         "Phase 1, so this action is dormant until a later seed moves an "
         "Engine. Netted persists until freed by a Pack Merge or repair.")
    return a


def _pack_merge():
    a = _base("pack_merge", ["brigus"])
    a["trigger"] = {"all": [
        {"kind": "engines_ready", "location": "{location}",
         "min_bond": 3, "count": 2},
        {"any": [
            [{"kind": "engine_present", "location": "{location}",
              "status_in": ["netted"]}],
            [{"kind": "flag", "flag": "raid_in_progress:great_basin",
              "present": True}],
            [{"kind": "flag", "flag": "raid_in_progress:concord_camp",
              "present": True}],
        ]},
    ]}
    a["need"] = [{"kind": "engine_present", "location": "{location}",
                  "status_in": ["netted"]}]
    a["effect"] = [
        {"op": "pack_merge_burn", "location": "{location}",
         "min_bond": 3, "qty": -2},
        {"op": "free_netted", "location": "{location}"},
        {"op": "note", "text": "trap destroyed / threat broken"},
    ]
    note("pack_merge: the pair is the two highest-Bond Engines at Brigus's "
         "location (Bond >= 3), each burned -2. A pair merged to Bond 1 "
         "cannot merge again until Dream Share restores it (DC-18, v1.4, "
         "Bryan's call, option C). The threat branch is a netted Engine "
         "or a raid flagged earlier in the same tick. Actor order means "
         "Brigus can answer a Chief raid the same tick; a Captain raid "
         "lands after his turn, so it is answered only via a netted "
         "Engine or not at all that tick. The merged form lasts 1 tick "
         "and has no further mechanical effect in the seed.")
    return a


def _dream_share():
    # v1.5 (Bryan's call, combined fix options 1 + 3): a scored action,
    # not a rest hook. Brigus chooses it as his action for the tick.
    a = _base("dream_share", ["brigus"])
    a["trigger"] = {"all": [
        {"kind": "engine_present", "location": "{location}"},
        {"any": [
            {"kind": "unmapped_exists"},
            {"all": [
                {"kind": "any_bond", "op": "<", "value": 5},
                res("pack", "pack", "Feed", ">=", 2),
            ]},
        ]},
    ]}
    a["need"] = [{"kind": "any_bond", "op": "<", "value": 5}]
    bond_when = {"all": [
        {"not": {"kind": "unmapped_exists"}},
        {"kind": "any_bond", "op": "<", "value": 5},
        res("pack", "pack", "Feed", ">=", 2),
    ]}
    a["effect"] = [
        {"op": "location_set",
         "location": {"target": "unmapped_location"}, "mapped": 1,
         "when": {"kind": "unmapped_exists"}},
        {"op": "note", "text": "dream reveals an unmapped place",
         "when": {"kind": "unmapped_exists"}},
        {"op": "bond_add",
         "engine": {"target": "lowest_bond_engine", "max_bond": 5},
         "qty": 1, "when": bond_when},
        {"op": "resource_add", "holder": "pack", "holder_kind": "pack",
         "resource": "Feed", "qty": -2, "when": bond_when},
        {"op": "note", "text": "dream restores +1 Bond (Pack Feed -2)",
         "when": bond_when},
    ]
    note("dream_share (v1.5, Bryan's call, combined fix options 1 + 3): "
         "a scored action, not a rest hook — Brigus chooses it as his "
         "action for the tick, scored by its material effect. Trigger is "
         "the seed's: Brigus is present with an Engine, and (an unmapped "
         "location exists, or an Engine's Bond is below 5 and the Pack "
         "holds 2+ Feed). The two branches are `when` ops evaluated "
         "against pre-action state, so exactly one fires: map first (an "
         "unmapped location becomes mapped, no cost), otherwise the "
         "lowest-Bond Engine (ties to Sledge) regains +1 and the Pack "
         "loses 2 Feed, never above 5. The need (a Bond below 5) scores "
         "the action higher when a restore is actually wanted; the map "
         "branch is still legal at weight 5. The post-rest hook is "
         "retired; the Bond guard stays Dream-Share-only (DC-18/DC-19) "
         "and only the dream_share action passes allow_bond_increase.")
    return a


def _fortify():
    a = _base("fortify", ["legion_captain", "kaelen"])
    a["trigger"] = {"all": [
        {"kind": "actor_location", "actor": "{self}",
         "location": "great_basin"},
        {"any": [res("ironwild_legion", "faction", "Salvage", ">=", 1),
                 res("pack", "pack", "Salvage", ">=", 1)]},
    ]}
    a["need"] = [clk("great_basin_recovery", "<", 6)]
    a["effect"] = [
        {"op": "resource_add", "holder": "ironwild_legion",
         "holder_kind": "faction", "resource": "Salvage", "qty": -1,
         "when": res("ironwild_legion", "faction", "Salvage", ">=", 1)},
        {"op": "resource_add", "holder": "pack", "holder_kind": "pack",
         "resource": "Salvage", "qty": -1,
         "when": {"all": [res("ironwild_legion", "faction", "Salvage",
                              "<", 1),
                          res("pack", "pack", "Salvage", ">=", 1)]}},
        {"op": "clock_add", "clock": "great_basin_recovery", "qty": 1},
    ]
    note("fortify: Salvage is paid by the Legion first, the Pack only when "
         "the Legion holds none. Fortify does NOT mark the city fortified "
         "by itself; the Recovery clock's completion does that (status "
         "becomes 'fortified'), so raids can still land until then.")
    return a


def _patrol():
    a = _base("patrol", ["legion_captain", "tull"])
    a["trigger"] = [{"kind": "always"}]
    a["need"] = []
    a["effect"] = [
        {"op": "flag_set", "flag": "patrolled:{location}"},
    ]
    note("patrol: marks the actor's location patrolled for this tick; the "
         "flag clears at the next tick. Raids on it that tick are logged "
         "as blocked.")
    return a


def _tend_den():
    a = _base("tend_den", ["nest_keeper"])
    a["trigger"] = [{"kind": "actor_location", "actor": "{self}",
                     "location": "chalk_canyons"}]
    a["need"] = [res("nest_keepers", "faction", "Feed", "<", 5)]
    a["effect"] = [
        {"op": "resource_add", "holder": "nest_keepers",
         "holder_kind": "faction", "resource": "Feed", "qty": 1},
        {"op": "note", "text": "den maintained"},
    ]
    return a


def _bargain():
    a = _base("bargain", ["high_baron"])
    a["trigger"] = [{"kind": "status_in", "entity_kind": "npc",
                     "id": "{self}",
                     "values": ["active, under guard", "active, watched"]}]
    a["need"] = []
    a["effect"] = [
        {"op": "status_set", "entity_kind": "npc", "id": "{self}",
         "status": "active, watched",
         "when": {"kind": "status", "entity_kind": "npc", "id": "{self}",
                  "value": "active, under guard"}},
        {"op": "status_set", "entity_kind": "npc", "id": "{self}",
         "status": "active",
         "when": {"kind": "status", "entity_kind": "npc", "id": "{self}",
                  "value": "active, watched"}},
        {"op": "move", "entity_kind": "npc", "id": "{self}",
         "location": "rust_dunes",
         "when": {"kind": "status", "entity_kind": "npc", "id": "{self}",
                  "value": "active, watched"}},
    ]
    note("bargain: the guard loosens one step per bargain (guarded -> "
         "watched -> free + leaves for Rust Dunes). The whens are all "
         "evaluated against the pre-action state, so one bargain can never "
         "jump two steps. His fate is NOT resolved by this (DC-08): the "
         "movement is a fork event only, never a blood-oath, execution, "
         "or release as a canon fact.")
    return a


def _evacuate():
    a = _base("evacuate", ["caravan_master"])
    a["trigger"] = [{"kind": "flag",
                     "flag": "raid_in_progress:{location}",
                     "present": True}]
    a["need"] = []
    a["halt_if"] = {"kind": "actor_location", "actor": "{self}",
                    "location": "concord_camp"}
    a["halt_message"] = ("Evacuate: the attacked location IS Concord Camp, "
                         "the safe location. Lore must name a fallback; "
                         "the engine stops instead of improvising.")
    a["effect"] = [
        {"op": "move", "entity_kind": "npc", "id": "{self}",
         "location": "concord_camp"},
    ]
    note("evacuate: fires when a raid is in progress at the caravan's "
         "location. The caravan's Feed lives on the faction holder, so it "
         "travels with the move by itself (no resource op needed). If the "
         "attacked location is Concord Camp itself, the engine HALTS and "
         "asks Lore (the seed's own stop rule).")
    return a


def _rest():
    a = _base("rest", ALL_ACTORS)
    a["weight"] = 0
    a["effect"] = [{"op": "rest"}]
    return a


# ---------------------------------------------------------------------------
# v1.3 quiet-world fix actions (fork-supplied, DC-17)
# ---------------------------------------------------------------------------

def _forage():
    a = _base("forage", ["legion_captain"])
    a["trigger"] = [res("ironwild_legion", "faction", "Feed", "<", 4)]
    a["effect"] = [
        {"op": "resource_add", "holder": "ironwild_legion",
         "holder_kind": "faction", "resource": "Feed", "qty": 2},
    ]
    note("forage (v1.3, fork-supplied): the Legion Captain only, and only "
         "while the Legion's Feed is below 4. +2 Feed. A floor, not a "
         "flood: the trigger is the low-Feed check itself.")
    return a


def _scavenge():
    # One seed action, three machine actions: the trigger's Salvage holder
    # is the actor's faction, and triggers carry fixed holders, so each
    # holder gets its own action (same split as trade and raid).
    out = []
    for action_id, actor_ids, holder in [
            ("scavenge_legion",
             ["legion_captain", "vance", "tull"], "ironwild_legion"),
            ("scavenge_dust_baron",
             ["dust_baron_captain"], "dust_baron_remnants"),
            ("scavenge_breakers",
             ["breaker_poacher_chief"], "breakers")]:
        a = _base(action_id, actor_ids)
        a["trigger"] = {"all": [
            res(holder, "faction", "Salvage", "<", 4),
            {"kind": "mapped_location_exists", "loc_kind": "wreck"},
        ]}
        a["effect"] = [
            {"op": "resource_add", "holder": holder,
             "holder_kind": "faction", "resource": "Salvage", "qty": 1},
        ]
        out.append(a)
    note("scavenge (v1.3, fork-supplied): the actor's holder gains +1 "
         "Salvage, only while that holder's Salvage is below 4 and a "
         "mapped wreck exists (Salt Flats). Split in three by holder, "
         "like trade and raid. A floor, not a flood.")
    return out


def _claim():
    # One seed action, four machine actions: the trigger's Salvage holder
    # and the new controller are both the actor's faction.
    out = []
    for action_id, actor_ids, faction in [
            ("claim_legion", ["legion_captain"], "ironwild_legion"),
            ("claim_dust_baron", ["dust_baron_captain"],
             "dust_baron_remnants"),
            ("claim_breakers", ["breaker_poacher_chief"], "breakers"),
            ("claim_nest_keepers", ["nest_keeper"], "nest_keepers")]:
        a = _base(action_id, actor_ids)
        a["trigger"] = {"all": [
            {"kind": "mapped_location_exists", "controlled": False},
            res(faction, "faction", "Salvage", ">=", 1),
        ]}
        a["effect"] = [
            {"op": "location_set",
             "location": {"target": "uncontrolled_mapped_location"},
             "controller": faction},
            {"op": "resource_add", "holder": faction,
             "holder_kind": "faction", "resource": "Salvage", "qty": -1},
        ]
        out.append(a)
    note("claim (v1.3, fork-supplied): the lowest-id uncontrolled mapped "
         "location's controller becomes the actor's faction, at a cost of "
         "1 Salvage. The selector only ever returns uncontrolled ground, "
         "so a controlled location can never be claimed (DC-17); taking "
         "one needs a siege/conquest rule, which does not exist in this "
         "fork. Split in four by faction, like trade and raid.")
    return out


# ---------------------------------------------------------------------------
# Clock completion effects (prose -> ops)
# ---------------------------------------------------------------------------

def _clock_effects(lore):
    out = {}
    for clock in lore["clocks"]:
        cid = clock["id"]
        if cid == "dust_baron_retaliation":
            out[cid] = [
                {"op": "resource_add", "holder": "ironwild_legion",
                 "holder_kind": "faction", "resource": "Feed", "qty": -2},
                {"op": "note", "text": "Dust-Baron captains strike Great "
                 "Basin in force (clock completion)"},
            ]
        elif cid == "concord_blockade":
            out[cid] = [
                {"op": "standing_set", "faction": "caravan_concord",
                 "other": "ironwild_legion", "value": "hostile"},
                {"op": "note", "text": "The road closes entirely; trade "
                 "with the Concord is blocked until Lore addresses it"},
            ]
        elif cid == "legion_cohesion":
            out[cid] = [
                {"op": "resource_add", "holder": "ironwild_legion",
                 "holder_kind": "faction", "resource": "Feed", "qty": -2},
                {"op": "resource_add", "holder": "dust_baron_remnants",
                 "holder_kind": "faction", "resource": "Salvage", "qty": 2},
                {"op": "note", "text": "A company of absorbed mercenaries "
                 "deserts (clock completion)"},
            ]
        elif cid == "great_basin_recovery":
            out[cid] = [
                {"op": "location_set", "location": "great_basin",
                 "status": "fortified"},
                {"op": "note", "text": "Great Basin fully re-fortified; "
                 "raids against it cannot land while fortified"},
            ]
        else:
            raise ValueError(f"unknown clock in seed: {cid}")
    note("Clock completions translated as written. The Blockade and "
         "Cohesion clocks have NO advancing action in the Phase 1 catalog "
         "(nothing in the seed tightens the gate or makes the mercenaries "
         "chafe), so they stay 0/6 running; their completion effects are "
         "implemented anyway for a later seed.")
    return out


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

def translate(lore):
    validate(lore)
    meta = lore["meta"]
    clock_effects = _clock_effects(lore)

    actions = [
        _hunt(), _feed_engine(), _repair_engine(), _scout_wreck(),
        *_trade(), _raid_captain(), _raid_chief(), _net_ambush(),
        _pack_merge(), _dream_share(), _fortify(), _patrol(), _tend_den(),
        _bargain(), _evacuate(), _rest(), _forage(), *_scavenge(),
        *_claim(),
    ]
    note(f"Catalog: {len(lore['actions'])} seed actions -> "
         f"{len(actions)} machine actions (trade split in two by "
         "counterparty, raid split in two by actor, scavenge split in "
         "three by holder, claim split in four by faction; dream_share "
         "is a scored action since v1.5, no hook).")

    note("Weights: the seed sets no action priorities, so every action "
         "weighs 5 (rest 0). Need clauses do the goal-directing. Lore may "
         "supply priorities in a later seed; the engine will use them.")
    note("Goals: the seed states goals as sentences, not tags, so actions "
         "carry no goal_tags. Legality comes from the seed's actor lists "
         "plus triggers. The seed's capability lists are stored on the "
         "actors but do NOT gate Phase 1 actions: no actor carries a "
         "hunt/feed_engine capability, yet every Pack actor is listed for "
         "hunt and feed_engine, so gating on capabilities would starve "
         "the Pack.")
    note("'Holder' is the actor's faction (Legion for Pack actors, "
         "Nest-Keepers for the Nest-Keeper, Concord for the Caravan "
         "Master). The Pack holder (Feed 6, Salvage 4) is used only by "
         "the Feed burn and the Legion-or-Pack Salvage fallbacks.")
    note("Bond recovery (v1.4, DC-18, Bryan's call, option C; v1.5 "
         "makes Dream Share a scored action, DC-19): Bond increases ONLY "
         "through Dream Share, +1 to one Engine per Dream Share at a "
         "cost of 2 Feed from the Pack, never above 5. The action has "
         "two branches, map first: an unmapped location exists -> one "
         "becomes mapped, no cost; otherwise the lowest-Bond Engine "
         "(ties to Sledge) regains +1 and the Pack loses 2 Feed. The "
         "action is legal only when a branch can act (an unmapped "
         "location exists, or an Engine is below 5 and the Pack holds "
         "2+ Feed), so it never fires as a no-op. Seedborns stay "
         "extremely rare: Brigus is the only Seedborn in Fork A; no "
         "other Seedborn is added.")
    note("Combined fix (v1.5, DC-19, Bryan's call, options 1 + 3): hunt "
         "Feed goes to the Pack, not the actor's holder, so the Pack's "
         "Feed pool now has an income; Dream Share is a scored action, "
         "not a rest hook, so Brigus can choose it while other actions "
         "are legal. Bond branch rules are unchanged from v1.4.")
    note("Feed burn (Engine Team's rate; the seed delegates it and sets no "
         "canon rate): the city (Ironwild Legion) burns 1 Feed/tick and "
         "the Pack burns 1 Feed/tick, from tick 1, clamped at zero, "
         "logged only when Feed is actually consumed. Lore or Bryan may "
         "change the rate; the engine invents no starvation effect.")
    note("Engines: all five start at Great Basin (the Pack's location; "
         "the seed gives Engines no location). Status 'exhausted' at "
         "tick 0. Exhausted Engines do not act and do not go Instinct; "
         "repair_engine makes them field-patched. Pilot-less Engines "
         "answer to the Pack collectively; their Bonds are stored with a "
         "null pilot and the engine never assigns one.")
    note("Era 2 is unnamed in the seed (null). The engine stores NULL and "
         "never invents a name for it.")
    note("Legacy: LR-01 ages only NPCs with an established age (none in "
         "this seed, so no aging numbers change and no retirement fires). "
         "LR-02 molts only Engines with an earned, unspent Molt trigger "
         "(none at tick 0; no Phase 1 action earns one). LR-03 succession "
         "moves Bonds and holdings to the named successor (Vance -> Tull) "
         "and HALTS if the dead name none. LR-04 records the Cores pool "
         "at the boundary (no cores are created by the boundary). LR-05 "
         "marks the era applied exactly once.")

    internal = {
        "world_id": meta["world_id"],
        "fork_label": meta["fork_label"],
        "source_snapshot": meta["source_snapshot"],
        "rng_seed": meta["rng_seed"],
        "era_length": meta["era_length_ticks"],
        "legacy": {
            "era_names": [lore["era"]["era_1"]["name"],
                          lore["era"]["era_2"]["name"]],
            "retire_age": None,
        },
        "feed_burn": [
            {"holder": "ironwild_legion", "holder_kind": "faction",
             "qty": 1},
            {"holder": "pack", "holder_kind": "pack", "qty": 1},
        ],
        "bond_recovery": "dream_share_only",
        "factions": [
            {"id": f["id"], "name": f["name"],
             "doctrine": f.get("doctrine", ""),
             "standings": f.get("standing", {})}
            for f in lore["factions"]
        ],
        "locations": [
            {"id": loc["id"], "name": loc["name"], "kind": loc["kind"],
             "controller": loc.get("controller_faction_id"),
             "status": loc.get("status", "standing"),
             "mapped": loc.get("mapped", True),
             "condition": loc.get("condition")}
            for loc in lore["locations"]
        ],
        "npcs": [
            {"id": a["id"], "name": a["name"],
             "faction": a.get("faction_id"),
             "location": a.get("location_id"), "age": None,
             "status": a.get("status", "active"),
             "goals": [a["goal"]] if a.get("goal") else [],
             "capabilities": a.get("capabilities", []),
             "successor": a.get("successor")}
            for a in lore["actors"]
        ],
        "engines": [
            {"id": e["id"], "name": e["name"], "shape": e["shape"],
             "pilot": e.get("pilot_id"), "location": "great_basin",
             "hunger": e.get("hunger", 0),
             "hunger_type": e["hunger_type"],
             "hunger_threshold": e.get("hunger_threshold", 5),
             "molt_trigger": 0, "status": e.get("status", "active")}
            for e in lore["engines"]
        ],
        "bonds": [
            {"engine": b["engine_id"], "pilot": b.get("pilot_id"),
             "bond": b["bond"]}
            for b in lore["bonds"]
        ],
        "resources": [
            {"holder": r["holder_id"], "holder_kind": r["holder_kind"],
             "resource": r["resource"], "qty": r["qty"]}
            for r in lore["resources"]
        ],
        "clocks": [
            {"id": c["id"], "name": c["name"], "value": c.get("value", 0),
             "max": c["max"], "status": c.get("status", "running"),
             "on_complete": clock_effects[c["id"]]}
            for c in lore["clocks"]
        ],
        "actions": actions,
    }
    return internal


def render_notes(lore):
    lines = [
        "# Fork A adapter notes — Lore seed to machine seed",
        "",
        f"Source: `seed/fork-a.json` v{lore['meta'].get('seed_version')} "
        f"({lore['meta'].get('seed_date')}), supplied by "
        f"{lore['meta'].get('supplied_by')}.",
        f"Fork: {lore['meta']['fork_label']}. Source snapshot: "
        f"{lore['meta']['source_snapshot']}.",
        "",
        "Every decision below is an interpretation the Engine Team made "
        "while translating prose into machine clauses. Lore may challenge "
        "any of them; the engine changes the adapter, never the seed.",
        "",
    ]
    for i, text in enumerate(NOTES, 1):
        lines.append(f"{i}. {text}")
        lines.append("")
    lines.append("## Gaps the adapter did not fill (engine stops instead)")
    lines.append("")
    lines.append("- No advancing action exists for the Concord Blockade or "
                 "Legion Cohesion clocks; they stay 0/6 running in Phase 1.")
    lines.append("- net_ambush cannot fire in Phase 1 (no Engine is ever "
                 "in Chalk Canyons).")
    lines.append("- No Phase 1 action earns a Molt trigger, kills an NPC, "
                 "or finds a dormant Seed Core; LR-02/LR-03/LR-04 exist "
                 "as machinery, not as live paths.")
    lines.append("- If the Caravan Master must evacuate Concord Camp "
                 "itself, or an NPC dies with no named successor, the "
                 "engine halts and asks Lore.")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Lore seed adapter")
    parser.add_argument("--in", dest="inp", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--notes", required=True)
    args = parser.parse_args()
    with open(args.inp) as f:
        lore = json.load(f)
    internal = translate(lore)
    with open(args.out, "w") as f:
        json.dump(internal, f, indent=1, sort_keys=True)
    with open(args.notes, "w") as f:
        f.write(render_notes(lore))
    print(f"translated {args.inp} -> {args.out} "
          f"({len(internal['actions'])} machine actions)")
    print(f"adapter notes -> {args.notes}")


if __name__ == "__main__":
    main()
