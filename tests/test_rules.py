"""Rules tests (plan section 10; DC-01, DC-02, DC-05, DC-06, DC-07, DC-08,
DC-09, DC-10, DC-11, DC-12, DC-14, DC-16).

Bond 0 refuses to move, Hunger/Instinct fires, clocks complete and pay out,
raids flip territory, invariants hold. Canon files are byte-identical before
and after every run.
"""

import hashlib
import os
import random
import tempfile
import unittest

from helpers import CANON_FILES, fresh_fixture_db
from src import tick as tick_mod


class TestRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn, _ = fresh_fixture_db(os.path.join(self.tmp.name, "a.sqlite"))

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_bond_zero_engine_refuses_to_move(self):
        # Tick 1: Rust Serpent (Bond 0, Hunger 8) goes Instinct.
        # Tick 2: Hunger 5, no legal action, Bond 0 -> refuse_to_move.
        tick_mod.run_ticks(self.conn, 2, rng=random.Random(131))
        rows = self.conn.execute(
            "SELECT * FROM events WHERE actor_id = 'fix-serpent' "
            "ORDER BY id").fetchall()
        actions = [(r["tick"], r["action"]) for r in rows]
        self.assertIn((1, "instinct_hunt"), actions)
        self.assertIn((2, "refuse_to_move"), actions)

    def test_hunger_instinct_fires_and_resets(self):
        tick_mod.run_ticks(self.conn, 1, rng=random.Random(131))
        hunger = self.conn.execute(
            "SELECT hunger FROM engines WHERE id = 'fix-serpent'"
        ).fetchone()["hunger"]
        self.assertEqual(hunger, 4)
        # Instinct feeds the pilot's faction (the holder model), not the
        # pilot NPC: the serpent's pilot Vex belongs to the Breakers.
        feed = self.conn.execute(
            "SELECT qty FROM resources WHERE holder_id = 'fix-breakers' "
            "AND holder_kind = 'faction' AND resource = 'Feed'").fetchone()
        self.assertIsNotNone(feed)
        self.assertEqual(feed["qty"], 2)

    def test_scout_clock_completes_and_pays_cores(self):
        tick_mod.run_ticks(self.conn, 1, rng=random.Random(131))
        clock = self.conn.execute(
            "SELECT value, status FROM clocks WHERE id = 'fix-scout'"
        ).fetchone()
        self.assertEqual(clock["status"], "complete")
        self.assertEqual(clock["value"], 3)
        cores = self.conn.execute(
            "SELECT qty FROM resources WHERE holder_id = 'fix-concord' "
            "AND resource = 'Cores'").fetchone()
        self.assertEqual(cores["qty"], 1)

    def test_raid_flips_territory(self):
        tick_mod.run_ticks(self.conn, 1, rng=random.Random(131))
        wreck = self.conn.execute(
            "SELECT controller_faction_id FROM locations "
            "WHERE id = 'fix-wreck'").fetchone()
        self.assertEqual(wreck["controller_faction_id"], "fix-breakers")

    def test_invariants_hold_after_30_ticks(self):
        tick_mod.run_ticks(self.conn, 30, rng=random.Random(131))
        self.assertEqual(tick_mod.verify_invariants(self.conn), [])


class TestNoCanonWrites(unittest.TestCase):
    def test_canon_files_unchanged_by_a_run(self):
        def digest():
            out = {}
            for path in CANON_FILES:
                with open(path, "rb") as f:
                    out[path] = hashlib.sha256(f.read()).hexdigest()
            return out

        with tempfile.TemporaryDirectory() as tmp:
            before = digest()
            conn, _ = fresh_fixture_db(os.path.join(tmp, "a.sqlite"))
            tick_mod.run_ticks(conn, 30, rng=random.Random(131))
            conn.close()
        self.assertEqual(digest(), before)


if __name__ == "__main__":
    unittest.main()
