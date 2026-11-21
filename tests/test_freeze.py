"""Freeze tests (plan section 10; DC-03, DC-04).

The fork starts at Turn 131 vFINAL. No Turn 136 / Crown of Cold Iron data,
no Krov ambush decision, no sequel clock, actor, or location may appear in
the seed or the DB. The check is on STATE, not strings: the Lore seed
names the excluded items on purpose (freeze declaration, exclusion list,
drift rules), so a raw string search is not the test.
"""

import json
import os
import tempfile
import unittest

from helpers import FIXTURE_PATH, fresh_fixture_db
from src import db, seed as seed_mod


class TestFreeze(unittest.TestCase):
    def test_fixture_source_is_turn_131_not_136(self):
        with open(FIXTURE_PATH) as f:
            text = f.read()
        seed_data = json.loads(text)
        self.assertIn("Turn 131", seed_data["source_snapshot"])
        self.assertNotIn("Turn 136", seed_data["source_snapshot"])
        self.assertNotIn("Krov", text)

    def test_seed_loader_refuses_turn_136(self):
        with open(FIXTURE_PATH) as f:
            seed_data = json.load(f)
        seed_data["source_snapshot"] = "Turn 136 vFINAL.5 (Krov ambush)"
        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(os.path.join(tmp, "a.sqlite"))
            db.init_schema(conn)
            with self.assertRaises(ValueError):
                seed_mod.load_seed(conn, seed_data)
            conn.close()

    def test_no_sequel_state_in_fixture_db(self):
        # DC-04, state-based: no sequel clock, actor, or location id in
        # any state table.
        with tempfile.TemporaryDirectory() as tmp:
            conn, _ = fresh_fixture_db(os.path.join(tmp, "a.sqlite"))
            self.assertEqual(
                db.get_meta(conn, "source_snapshot").split(" mechanics")[0],
                "Turn 131 vFINAL")
            clocks = [r["id"] for r in conn.execute("SELECT id FROM clocks")]
            self.assertNotIn("rider_army_mustering", clocks)
            conn.close()


if __name__ == "__main__":
    unittest.main()
