"""Tests for the one-command turn wrapper (src/turn.py)."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import db, proposals as proposals_mod  # noqa: E402
from src import sweep as sweep_mod  # noqa: E402
from src import tick as tick_mod  # noqa: E402
from src import turn as turn_mod  # noqa: E402
from tests.helpers import fresh_fork_b_db  # noqa: E402
from tests.test_apply_adapter import TURN_1, TURN_2  # noqa: E402

# Turn 2 as a pure carry-over of Turn 1 (same scene, same PC line
# modulo the Bond the tick restores, same pending decision).
TURN_2_CARRY = TURN_1.replace(
    "ForkB-v1.0 | Turn: 1", "ForkB-v1.1 | Turn: 2").replace(
    "Bond 1/5", "Bond 2/5")

TURN_3 = TURN_1.replace(
    "ForkB-v1.0 | Turn: 1", "ForkB-v1.2 | Turn: 3").replace(
    "Rust Dunes — Half-Buried Wreck Field",
    "Rust Dunes — Open Hatch and Descending Stairwell").replace(
    "SCENE_TENSION: Low", "SCENE_TENSION: Rising")


class TurnTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_dir = proposals_mod.PROPOSALS_DIR
        self._orig_reg = proposals_mod.REGISTRY_PATH
        proposals_mod.PROPOSALS_DIR = os.path.join(self.tmp, "proposals")
        proposals_mod.REGISTRY_PATH = os.path.join(
            self.tmp, "proposals", "registry.json")
        self._orig_runs = os.environ.get("IRONWILD_RUNS_DIR")
        self.runs_dir = os.path.join(self.tmp, "runs")
        os.environ["IRONWILD_RUNS_DIR"] = self.runs_dir
        self.db_path = os.path.join(self.tmp, "test.sqlite")
        conn, _seed = fresh_fork_b_db(self.db_path)
        # The wrapper tests verify wrapper mechanics against the
        # recorded v1 tick outcomes (Bond 2/5, the net); the RNG
        # scheme itself is covered by test_step1_slice2.
        db.set_meta(conn, "rng_scheme", "v1")
        conn.commit()
        conn.close()
        self.flag_path = os.path.join(self.tmp, "session.json")
        with open(self.flag_path, "w") as f:
            json.dump({"session_open": False,
                       "world_id": "ironwild-fork-b"}, f)

    def tearDown(self):
        proposals_mod.PROPOSALS_DIR = self._orig_dir
        proposals_mod.REGISTRY_PATH = self._orig_reg
        if self._orig_runs is None:
            os.environ.pop("IRONWILD_RUNS_DIR", None)
        else:
            os.environ["IRONWILD_RUNS_DIR"] = self._orig_runs

    def _conn(self):
        return db.connect(self.db_path)

    def _state_hash(self):
        conn = self._conn()
        try:
            return db.state_hash(conn)
        finally:
            conn.close()

    def _last_swept(self):
        conn = self._conn()
        try:
            return db.get_meta(conn, "last_swept_turn")
        finally:
            conn.close()

    def _tick(self):
        conn = self._conn()
        try:
            return db.get_tick(conn)
        finally:
            conn.close()

    def _apply_turn_1(self):
        return turn_mod.run_turn(
            self.db_path, TURN_1, name="turn-1.txt", yes=True,
            flag_path=self.flag_path)

    def _drop_net(self):
        """Mirror Bryan's live net drop: Ashfang broke free."""
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE engines SET status='newly awakened and battered' "
                "WHERE id='ashfang'")
            conn.commit()
        finally:
            conn.close()

    def test_dry_run_writes_nothing(self):
        before = self._state_hash()
        record = turn_mod.run_turn(
            self.db_path, TURN_1, dry_run=True, flag_path=self.flag_path)
        self.assertEqual(record["tier"], "REVIEW")
        self.assertTrue(record["dry_run"])
        self.assertEqual(self._state_hash(), before)
        self.assertFalse(os.path.exists(self.runs_dir))
        self.assertEqual(proposals_mod.load_registry(), {})

    def test_review_waits_for_confirmation(self):
        with mock.patch("builtins.input", return_value="n"):
            with self.assertRaises(turn_mod.TurnError):
                turn_mod.run_turn(
                    self.db_path, TURN_1, flag_path=self.flag_path)
        self.assertIsNone(self._last_swept())
        self.assertFalse(os.path.exists(
            os.path.join(self.runs_dir, "backups")))
        with mock.patch("builtins.input", return_value="y"):
            record = turn_mod.run_turn(
                self.db_path, TURN_1, flag_path=self.flag_path)
        self.assertEqual(record["turn"], 1)
        self.assertEqual(self._last_swept(), "1")
        self.assertEqual(self._tick(), 3)

    def test_auto_applies_carry_over(self):
        record1 = self._apply_turn_1()
        self.assertEqual(record1["tier"], "REVIEW")
        self.assertEqual(self._tick(), 3)
        self._drop_net()
        record2 = turn_mod.run_turn(
            self.db_path, TURN_2_CARRY, name="turn-2.txt",
            flag_path=self.flag_path)
        self.assertEqual(record2["tier"], "AUTO")
        self.assertEqual(record2["turn"], 2)
        self.assertEqual(self._last_swept(), "2")
        self.assertEqual(self._tick(), 6)
        hs_path = os.path.join(
            self.runs_dir, "fork-b", "handshakes", "turn-3.txt")
        self.assertTrue(os.path.exists(hs_path))
        with open(hs_path) as f:
            self.assertIn("ForkB-v1.2", f.read())

    def test_hold_never_applies(self):
        bad = TURN_1.replace("Ashfang is Bond 1/5", "Zorg is Bond 1/5")
        with self.assertRaises(turn_mod.TurnError):
            turn_mod.run_turn(
                self.db_path, bad, yes=True, flag_path=self.flag_path)
        self.assertIsNone(self._last_swept())
        self.assertFalse(os.path.exists(
            os.path.join(self.runs_dir, "backups")))

    def test_out_of_order_refused(self):
        with self.assertRaises(turn_mod.TurnError) as ctx:
            turn_mod.run_turn(
                self.db_path, TURN_2, yes=True, flag_path=self.flag_path)
        self.assertIn("expected Turn 1, got Turn 2", str(ctx.exception))
        self.assertIsNone(self._last_swept())

    def test_duplicate_refused(self):
        self._apply_turn_1()
        with self.assertRaises(turn_mod.TurnError) as ctx:
            turn_mod.run_turn(
                self.db_path, TURN_1, yes=True, flag_path=self.flag_path)
        self.assertIn("already applied", str(ctx.exception))

    def test_backup_exists_before_apply_and_sidecar_matches(self):
        before = self._state_hash()
        record = self._apply_turn_1()
        backup_path = record["backup_path"]
        self.assertTrue(os.path.exists(backup_path))
        with open(backup_path + ".json") as f:
            sidecar = json.load(f)
        self.assertEqual(sidecar["state_hash"], before)
        self.assertEqual(sidecar["tick"], 0)
        self.assertEqual(sidecar["turn"], 1)

    def test_rollback_restores_exact_state_hash(self):
        before = self._state_hash()
        self._apply_turn_1()
        self.assertNotEqual(self._state_hash(), before)
        result = turn_mod.run_rollback(self.db_path, yes=True)
        self.assertEqual(result["state_hash"], before)
        self.assertEqual(result["tick"], 0)
        self.assertEqual(self._last_swept(), None)
        # The same block can be applied again after the reset.
        self._apply_turn_1()
        self.assertEqual(self._last_swept(), "1")

    def test_halt_stops_cleanly_without_a_second_tick(self):
        with mock.patch("src.tick.run_ticks",
                        side_effect=tick_mod.EngineHalt("test halt")) \
                as patched:
            with self.assertRaises(turn_mod.TurnError) as ctx:
                self._apply_turn_1()
        self.assertIn("halted", str(ctx.exception))
        self.assertEqual(patched.call_count, 1)
        # The apply stands, but no handshake was generated.
        self.assertEqual(self._last_swept(), "1")
        self.assertFalse(os.path.exists(os.path.join(
            self.runs_dir, "fork-b", "handshakes", "turn-2.txt")))
        record_path = os.path.join(
            self.runs_dir, "fork-b", "turns", "turn-1.json")
        with open(record_path) as f:
            record = json.load(f)
        self.assertEqual(record["tick_halted"], "test halt")

    def test_session_flag_blocks(self):
        with open(self.flag_path, "w") as f:
            json.dump({"session_open": True,
                       "world_id": "ironwild-fork-b", "turn": 1,
                       "opened_at": "2026-11-22",
                       "opened_by": "hub"}, f)
        with self.assertRaises(turn_mod.TurnError) as ctx:
            turn_mod.run_turn(
                self.db_path, TURN_1, yes=True, flag_path=self.flag_path)
        self.assertIn("session is open", str(ctx.exception))
        self.assertIsNone(self._last_swept())

    def test_handshake_file_written_with_next_turn_number(self):
        self._apply_turn_1()
        hs_path = os.path.join(
            self.runs_dir, "fork-b", "handshakes", "turn-2.txt")
        self.assertTrue(os.path.exists(hs_path))
        with open(hs_path) as f:
            text = f.read()
        self.assertIn("ForkB-v1.1", text)
        self.assertIn("Turn 2", text)

    def test_queue_lists_waiting_in_order(self):
        conn = self._conn()
        try:
            from src import apply_adapter as adapter_mod
            adapter_mod.register_local_block(
                TURN_3, conn, name="turn-3.txt")
            adapter_mod.register_local_block(
                TURN_2, conn, name="turn-2.txt")
        finally:
            conn.close()
        result = turn_mod.run_queue(self.db_path)
        turns = [row["turn"] for row in result["proposals"]]
        self.assertEqual(turns, [2, 3])
        self.assertTrue(all(row["current_revision"]
                            for row in result["proposals"]))


if __name__ == "__main__":
    unittest.main()
