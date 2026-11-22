"""Seed checker tests (tools/check_seed.py)."""

import importlib.util
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_seed", os.path.join(ROOT, "tools", "check_seed.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_seed_mod = _load_checker()


def _minimal_seed(**overrides):
    seed = {
        "clocks": [{"id": "engine_awakening", "value": 1, "max": 6,
                    "status": "running", "on_complete": []}],
        "locations": [{"id": "rust_dunes", "controller": None},
                      {"id": "great_basin", "controller": "great_basin"}],
        "factions": [{"id": "great_basin"}, {"id": "breakers"}],
        "engines": [{"id": "ashfang", "location": "rust_dunes",
                     "pilot": "rin"}],
        "npcs": [{"id": "rin", "location": "rust_dunes",
                  "faction": "great_basin"},
                 {"id": "pike", "location": "rust_dunes",
                  "faction": "great_basin"}],
        "resources": [{"holder": "great_basin", "holder_kind": "faction",
                       "resource": "Salvage", "qty": 4},
                      {"holder": "great_basin", "holder_kind": "faction",
                       "resource": "Feed", "qty": 6}],
        "actions": [],
    }
    seed.update(overrides)
    return seed


def _fortify_like(need_in_trigger=False):
    clock_clause = {"id": "engine_awakening", "kind": "clock",
                    "op": "<", "value": 6}
    action = {
        "id": "fortify",
        "actor_ids": ["rin"],
        "actor_kind": "npc",
        "trigger": {"all": [
            {"actor": "{self}", "kind": "actor_location",
             "location": "great_basin"},
        ]},
        "need": [clock_clause],
        "effect": [{"op": "clock_add", "clock": "engine_awakening",
                    "qty": 1}],
        "weight": 5,
    }
    if need_in_trigger:
        action["trigger"]["all"].append(clock_clause)
        action["need"] = []
    return action


class TestCheckSeed(unittest.TestCase):
    def test_fortify_pattern_flagged(self):
        seed = _minimal_seed(actions=[_fortify_like()])
        findings = check_seed_mod.check_seed(seed, "test")
        self.assertEqual(len(findings), 1)
        self.assertIn("NEED_CLOCK_PRECONDITION", findings[0])
        self.assertIn("fortify", findings[0])

    def test_corrected_action_passes(self):
        seed = _minimal_seed(actions=[_fortify_like(need_in_trigger=True)])
        self.assertEqual(check_seed_mod.check_seed(seed, "test"), [])

    def test_missing_clock_flagged(self):
        action = {
            "id": "trade_concord",
            "actor_ids": ["rin"],
            "actor_kind": "npc",
            "trigger": {"all": [
                {"id": "concord_blockade", "kind": "clock",
                 "op": "<", "value": 6},
            ]},
            "need": [],
            "effect": [],
            "weight": 5,
        }
        seed = _minimal_seed(actions=[action])
        findings = check_seed_mod.check_seed(seed, "test")
        self.assertEqual(len(findings), 1)
        self.assertIn("MISSING_CLOCK", findings[0])
        self.assertIn("concord_blockade", findings[0])

    def test_missing_location_faction_engine_npc_flagged(self):
        action = {
            "id": "bad_refs",
            "actor_ids": ["ghost"],
            "actor_kind": "npc",
            "trigger": {"all": [
                {"actor": "{self}", "kind": "actor_location",
                 "location": "nowhere"},
                {"holder": "ghosts", "holder_kind": "faction",
                 "kind": "resource", "op": ">=", "resource": "Salvage",
                 "value": 1},
                {"engine": "ghost_engine", "kind": "bond",
                 "op": ">=", "value": 1},
            ]},
            "need": [],
            "effect": [{"op": "clock_add", "clock": "ghost_clock",
                        "qty": 1}],
            "weight": 5,
        }
        seed = _minimal_seed(actions=[action])
        findings = check_seed_mod.check_seed(seed, "test")
        kinds = [f.split(": ")[1].split(":")[0] for f in findings]
        for kind in ("MISSING_NPC", "MISSING_LOCATION",
                     "MISSING_FACTION", "MISSING_ENGINE",
                     "MISSING_CLOCK"):
            self.assertIn(kind, kinds, findings)

    def test_placeholders_and_selectors_not_flagged(self):
        action = {
            "id": "repair_engine",
            "actor_ids": ["pike"],
            "actor_kind": "npc",
            "trigger": {"all": [
                {"kind": "engine_present", "location": "{location}",
                 "status_in": ["netted"]},
            ]},
            "need": [],
            "effect": [
                {"entity_kind": "engine",
                 "id": {"location": "{location}", "target":
                        "engine_at_location"},
                 "op": "status_set", "status": "field-patched"},
                {"holder": "{holder}", "holder_kind": "faction",
                 "op": "resource_add", "qty": -1, "resource": "Salvage",
                 "when": {"holder": "{holder}", "holder_kind": "faction",
                          "kind": "resource", "op": ">=",
                          "resource": "Salvage", "value": 1}},
            ],
            "weight": 5,
        }
        seed = _minimal_seed(actions=[action])
        self.assertEqual(check_seed_mod.check_seed(seed, "test"), [])

    def test_real_fork_a_seed(self):
        with open(os.path.join(ROOT, "seed",
                               "fork-a.internal.json")) as f:
            seed = json.load(f)
        findings = check_seed_mod.check_seed(seed, "fork-a")
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("fortify", findings[0])
        self.assertIn("NEED_CLOCK_PRECONDITION", findings[0])

    def test_real_fork_b_seed(self):
        # The repair_engine dead clock_add was dropped 2026-11-22
        # (Bryan: "drop the dead piece"), so Fork B is clean now.
        with open(os.path.join(ROOT, "seed",
                               "fork-b.internal.json")) as f:
            seed = json.load(f)
        self.assertEqual(check_seed_mod.check_seed(seed, "fork-b"), [])


if __name__ == "__main__":
    unittest.main()
