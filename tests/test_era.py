"""Era tests (plan section 10; LR-05 era applied once).

A 400-tick fast-forward crosses one era boundary (tick 365), applies the
legacy rules exactly once, and opens the next era. The fixture's legacy
rules (retire at 60) are the test's own; the Lore seed's legacy rules
(LR-01..LR-05) are tested in test_fork_a.py.
"""

import os
import random
import tempfile
import unittest

from helpers import fresh_fixture_db
from src import tick as tick_mod


class TestEra(unittest.TestCase):
    def test_400_tick_fast_forward_crosses_one_era(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn, _ = fresh_fixture_db(os.path.join(tmp, "a.sqlite"))
            tick_mod.run_ticks(conn, 400, rng=random.Random(131))
            legacy = conn.execute(
                "SELECT COUNT(*) AS n FROM events WHERE action = 'legacy'"
            ).fetchone()["n"]
            self.assertEqual(legacy, 1, "legacy must fire exactly once")
            closed = conn.execute(
                "SELECT name, legacy_applied FROM eras "
                "WHERE end_tick IS NOT NULL").fetchall()
            self.assertEqual(len(closed), 1)
            self.assertEqual(closed[0]["name"], "Year 1")
            self.assertEqual(closed[0]["legacy_applied"], 1)
            open_era = conn.execute(
                "SELECT name FROM eras WHERE end_tick IS NULL").fetchone()
            self.assertEqual(open_era["name"], "Year 2")
            moss = conn.execute(
                "SELECT age, status FROM npcs WHERE id = 'fix-moss'"
            ).fetchone()
            self.assertEqual(moss["age"], 60)
            self.assertEqual(moss["status"], "retired")
            self.assertEqual(tick_mod.verify_invariants(conn), [])
            conn.close()

    def test_muster_clock_completes_and_flips_region(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn, _ = fresh_fixture_db(os.path.join(tmp, "a.sqlite"))
            tick_mod.run_ticks(conn, 400, rng=random.Random(131))
            muster = conn.execute(
                "SELECT value, status FROM clocks WHERE id = 'fix-muster'"
            ).fetchone()
            self.assertEqual(muster["status"], "complete")
            region = conn.execute(
                "SELECT controller_faction_id FROM locations "
                "WHERE id = 'fix-region'").fetchone()
            self.assertEqual(region["controller_faction_id"], "fix-concord")
            conn.close()


if __name__ == "__main__":
    unittest.main()
