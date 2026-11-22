"""Determinism tests (plan section 10; DC-15 fork label).

Same seed + same seed data -> byte-identical event log and state hash.
"""

import os
import random
import tempfile
import unittest

from helpers import event_log, fresh_fixture_db
from src import db, tick as tick_mod


class TestDeterminism(unittest.TestCase):
    def test_same_seed_same_world(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn_a, _ = fresh_fixture_db(os.path.join(tmp, "a.sqlite"))
            tick_mod.run_ticks(conn_a, 30, rng=random.Random(131))
            log_a = event_log(conn_a)
            hash_a = db.state_hash(conn_a)
            conn_a.close()

            conn_b, _ = fresh_fixture_db(os.path.join(tmp, "b.sqlite"))
            tick_mod.run_ticks(conn_b, 30, rng=random.Random(131))
            log_b = event_log(conn_b)
            hash_b = db.state_hash(conn_b)
            conn_b.close()

        self.assertEqual(log_a, log_b, "event logs differ between runs")
        self.assertEqual(hash_a, hash_b, "state hashes differ between runs")

    def test_different_seed_different_world(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn_a, _ = fresh_fixture_db(os.path.join(tmp, "a.sqlite"))
            tick_mod.run_ticks(conn_a, 30)
            hash_a = db.state_hash(conn_a)
            conn_a.close()
            conn_b, _ = fresh_fixture_db(os.path.join(tmp, "b.sqlite"))
            # Under v2 the seed is the DB's rng_seed meta, not a
            # passed Random: a different seed must diverge.
            db.set_meta(conn_b, "rng_seed", 999)
            conn_b.commit()
            tick_mod.run_ticks(conn_b, 30)
            hash_b = db.state_hash(conn_b)
            conn_b.close()
        # Different seeds must be able to diverge (ties break differently).
        # This guards against the RNG never being consulted.
        self.assertNotEqual(hash_a, hash_b)

    def test_fork_label_on_outputs(self):
        # DC-15: the fork label appears on every output.
        with tempfile.TemporaryDirectory() as tmp:
            conn, seed_data = fresh_fixture_db(
                os.path.join(tmp, "a.sqlite"))
            self.assertEqual(db.get_meta(conn, "fork_label"),
                             seed_data["fork_label"])
            conn.close()


if __name__ == "__main__":
    unittest.main()
