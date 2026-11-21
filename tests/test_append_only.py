"""Append-only tests (plan section 10; DC-13 locations never deleted).

The event log grows only: database triggers refuse UPDATE/DELETE, and the
hash chain detects tampering even if the triggers are bypassed.
"""

import os
import random
import sqlite3
import tempfile
import unittest

from helpers import fresh_fixture_db
from src import events, tick as tick_mod


class TestAppendOnly(unittest.TestCase):
    def test_events_cannot_be_updated_or_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn, _ = fresh_fixture_db(os.path.join(tmp, "a.sqlite"))
            tick_mod.run_ticks(conn, 10, rng=random.Random(131))
            before = events.count_events(conn)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE events SET action = 'forged' WHERE id = 1")
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM events WHERE id = 1")
            self.assertEqual(events.count_events(conn), before)
            ok, bad = events.verify_chain(conn)
            self.assertTrue(ok, f"hash chain broken at {bad}")
            conn.close()

    def test_hash_chain_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn, _ = fresh_fixture_db(os.path.join(tmp, "a.sqlite"))
            tick_mod.run_ticks(conn, 5, rng=random.Random(131))
            # Bypass the triggers by dropping them, then tamper, then check.
            conn.execute("DROP TRIGGER events_no_update")
            conn.execute("UPDATE events SET action = 'forged' WHERE id = 1")
            conn.commit()
            ok, bad = events.verify_chain(conn)
            self.assertFalse(ok)
            self.assertEqual(bad, 1)
            conn.close()

    def test_locations_never_deleted(self):
        # DC-13: locations are never deleted; controller/status change only
        # via events, with old and new values recorded.
        with tempfile.TemporaryDirectory() as tmp:
            conn, seed_data = fresh_fixture_db(os.path.join(tmp, "a.sqlite"))
            before = conn.execute(
                "SELECT COUNT(*) AS n FROM locations").fetchone()["n"]
            tick_mod.run_ticks(conn, 30, rng=random.Random(131))
            after = conn.execute(
                "SELECT COUNT(*) AS n FROM locations").fetchone()["n"]
            self.assertEqual(before, after)
            self.assertEqual(after, len(seed_data["locations"]))
            conn.close()


if __name__ == "__main__":
    unittest.main()
