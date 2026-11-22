"""Tests for Step 1 slice 2: one RNG scheme (hash seed, actor, tick)."""

import copy
import json
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import db  # noqa: E402
from src import seed as seed_mod  # noqa: E402
from src import tick as tick_mod  # noqa: E402
from tests.helpers import (fresh_fixture_db, fresh_fork_b_db,  # noqa: E402
                           fresh_fork_db)

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixture_seed.json")

# Golden hashes recorded on the old code (v1), before the change.
V1_FORK_A_30 = "09ecd8f5f3881aa8831fab4715009470261a3adc2990a2ca04c4e93a312c9790"
V1_FIXTURE_400 = "e998132eeb3166d1d7984aac7d0dc4a92e510b3cdae91cae74bb23f95924c566"
# Fork B golden, re-recorded 2026-11-22 after the APPROVED seed diffs
# (trade_concord clock concord_blockade -> caravan_route; scavenge
# need added). The old value was
# 72ed813c751d87abcc2d52bef1327e7bfd346ae5e1e2189eea8ef5adede43d5c.
# The replay is deterministic (two runs, identical hashes and logs);
# the new behavior is the fix working: the caravan_master trades on
# ticks 1-2 and the Breaker chief scavenges on tick 2.
# Re-recorded AGAIN 2026-11-22 after Bryan dropped the dead
# repair_engine clock_add (great_basin_recovery). The 3-tick event
# log is unchanged (0 repairs in 3 ticks); the hash moved only
# because state_hash covers the catalog in meta. Old value was
# 7fc067a928c9f57abdda0089c2485fa681daed7fb607a7c60538cbed962b523d.
V1_FORK_B_3 = "f4f293a79ec517aad6b4e4630e31fbceb4479723cc2361b3d15ff9b0bb743651"


def _draws(rng, n=20):
    return [rng.choice(["a", "b", "c", "d"]) for _ in range(n)]


def _event_log(conn):
    return [(r["tick"], r["actor_id"], r["action"])
            for r in conn.execute(
                "SELECT tick, actor_id, action FROM events ORDER BY id")]


def _seed_from_dict(path, seed_dict):
    conn = db.connect(path)
    db.init_schema(conn)
    seed_mod.load_seed(conn, seed_dict)
    conn.commit()
    return conn


class Slice2TestCase(unittest.TestCase):
    def test_per_actor_stream_is_stable_and_independent(self):
        self.assertEqual(
            _draws(tick_mod.rng_for(1, "rin", 5)),
            _draws(tick_mod.rng_for(1, "rin", 5)))
        self.assertNotEqual(
            _draws(tick_mod.rng_for(1, "rin", 5)),
            _draws(tick_mod.rng_for(1, "pike", 5)))
        self.assertNotEqual(
            _draws(tick_mod.rng_for(1, "rin", 5)),
            _draws(tick_mod.rng_for(1, "rin", 6)))
        # The old seed+tick collision: seed 5 tick 3 == seed 3 tick 5.
        self.assertNotEqual(
            _draws(tick_mod.rng_for(5, "rin", 3)),
            _draws(tick_mod.rng_for(3, "rin", 5)))

    def test_chunked_equals_continuous(self):
        logs = []
        hashes = []
        with tempfile.TemporaryDirectory() as tmp:
            for i, chunks in enumerate([(10,), (5, 5), (1,) * 10]):
                conn, _ = fresh_fixture_db(
                    os.path.join(tmp, "chunk-%d.sqlite" % i))
                for n in chunks:
                    tick_mod.run_ticks(conn, n)
                logs.append(_event_log(conn))
                hashes.append(db.state_hash(conn))
                self.assertEqual(db.get_tick(conn), 10)
                conn.close()
        self.assertEqual(logs[0], logs[1])
        self.assertEqual(logs[0], logs[2])
        self.assertEqual(hashes[0], hashes[1])
        self.assertEqual(hashes[0], hashes[2])

    def test_adding_an_npc_changes_no_one_else(self):
        with open(FIXTURE_PATH) as f:
            base = json.load(f)
        with open(FIXTURE_PATH) as f:
            grown = json.load(f)
        # A new NPC that sorts first by id, with two tied no-op
        # actions: it draws on the tie but changes nothing.
        grown["npcs"].append({
            "age": 30, "capabilities": ["idle_tie"],
            "faction": "fix-concord", "goals": [], "id": "aaa_new",
            "location": "fix-den", "name": "Fixture New"})
        for suffix in ("a", "b"):
            grown["actions"].append({
                "actor_kind": "npc", "capability": "idle_tie",
                "effect": [], "goal_tags": [],
                "id": "idle_%s" % suffix, "need": [],
                "trigger": [{"kind": "always"}], "weight": 5})
        with tempfile.TemporaryDirectory() as tmp:
            conn_a = _seed_from_dict(
                os.path.join(tmp, "a.sqlite"), copy.deepcopy(base))
            conn_b = _seed_from_dict(
                os.path.join(tmp, "b.sqlite"), grown)
            tick_mod.run_ticks(conn_a, 1)
            tick_mod.run_ticks(conn_b, 1)
            picks_a = [(a, act) for _t, a, act in _event_log(conn_a)
                       if a != "aaa_new"]
            picks_b = [(a, act) for _t, a, act in _event_log(conn_b)
                       if a != "aaa_new"]
            newbie = [act for _t, a, act in _event_log(conn_b)
                      if a == "aaa_new"]
            conn_a.close()
            conn_b.close()
        # The new NPC did act (it drew on its tie) ...
        self.assertEqual(len(newbie), 1)
        self.assertIn(newbie[0], ("idle_a", "idle_b"))
        # ... and nobody else's pick changed.
        self.assertEqual(picks_a, picks_b)

    def test_same_seed_same_world_across_drivers(self):
        logs = []
        hashes = []
        with tempfile.TemporaryDirectory() as tmp:
            conn, _ = fresh_fixture_db(os.path.join(tmp, "a.sqlite"))
            tick_mod.run_ticks(conn, 10, rng=random.Random(999))
            logs.append(_event_log(conn))
            hashes.append(db.state_hash(conn))
            conn.close()
            conn, _ = fresh_fixture_db(os.path.join(tmp, "b.sqlite"))
            tick_mod.run_ticks(conn, 10)
            logs.append(_event_log(conn))
            hashes.append(db.state_hash(conn))
            conn.close()
        self.assertEqual(logs[0], logs[1])
        self.assertEqual(hashes[0], hashes[1])

    def test_new_db_defaults_to_v2_and_seed_can_pin_v1(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn, _ = fresh_fixture_db(os.path.join(tmp, "a.sqlite"))
            self.assertEqual(db.get_meta(conn, "rng_scheme"), "v2")
            conn.close()
            with open(FIXTURE_PATH) as f:
                seed = json.load(f)
            seed["rng_scheme"] = "v1"
            conn = _seed_from_dict(os.path.join(tmp, "b.sqlite"), seed)
            self.assertEqual(db.get_meta(conn, "rng_scheme"), "v1")
            conn.close()

    def test_v1_replay_identical(self):
        # A DB with no rng_scheme key (the exact situation of the
        # live Fork A / Fork B DBs) replays bit-for-bit under v1.
        with tempfile.TemporaryDirectory() as tmp:
            conn, _ = fresh_fork_db(os.path.join(tmp, "a.sqlite"))
            conn.execute(
                "DELETE FROM meta WHERE key = 'rng_scheme'")
            conn.commit()
            tick_mod.run_ticks(conn, 30, rng=random.Random(131))
            self.assertEqual(db.state_hash(conn), V1_FORK_A_30)
            conn.close()
            conn, _ = fresh_fixture_db(os.path.join(tmp, "b.sqlite"))
            conn.execute(
                "DELETE FROM meta WHERE key = 'rng_scheme'")
            conn.commit()
            tick_mod.run_ticks(conn, 400, rng=random.Random(131))
            self.assertEqual(db.state_hash(conn), V1_FIXTURE_400)
            conn.close()
            conn, _ = fresh_fork_b_db(os.path.join(tmp, "c.sqlite"))
            conn.execute(
                "DELETE FROM meta WHERE key = 'rng_scheme'")
            conn.commit()
            tick_mod.run_ticks(conn, 3)
            self.assertEqual(db.state_hash(conn), V1_FORK_B_3)
            conn.close()


if __name__ == "__main__":
    unittest.main()
