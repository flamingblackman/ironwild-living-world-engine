"""Tests for the shared apply adapter (src/apply_adapter.py).

The gate (turn order + duplicate) lives here and is called by every
apply path: the Drive path, the local-file path, and the manual
sweep path. These tests pin that sharing.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import apply_adapter as adapter_mod  # noqa: E402
from src import db, proposals as proposals_mod  # noqa: E402
from src import sweep as sweep_mod  # noqa: E402
from tests.helpers import fresh_fork_b_db  # noqa: E402

TURN_1 = """[TURN STATE]
Universe: Ironwild | State-Version: ForkB-v1.0 | Turn: 1
Clocks: Engine Awakening 1/6, Dust-Baron Retaliation 0/6, Caravan Route 0/6
Scene: Rust Dunes — Half-Buried Wreck Field | SCENE_TENSION: Low | ACTIVE_TRADE_OFF: The Engine is awake and bonded, but it is battered and the dunes are Breaker territory; getting it home means crossing poacher ground.
Player character: Rin, Seedborn, scavenger of the Great Basin. Wounds: None. Status: newly bonded, standing in the Rust Dunes with Ashfang, a wolf Bulwark that just woke for them. Ashfang is Rin's only Engine; Ashfang is Bond 1/5, newly awakened and battered, equipped with a scrap-claw and a neural Sentient Seat (not a saddle-harness). Rin rides via the neural Sentient Seat. Pack: Rin and Pike, two people and one wolf. Pike is Rin's fellow scavenger, present in the Rust Dunes. Faction: Great Basin.
Unresolved Decisions: What does Rin do with the awakened Engine — bring it home to the Great Basin, hide it from the Breakers, or follow where it wants to go?
[/TURN STATE]
"""

TURN_2 = TURN_1.replace("ForkB-v1.0 | Turn: 1", "ForkB-v1.1 | Turn: 2")


class AdapterTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_dir = proposals_mod.PROPOSALS_DIR
        self._orig_reg = proposals_mod.REGISTRY_PATH
        proposals_mod.PROPOSALS_DIR = os.path.join(self.tmp, "proposals")
        proposals_mod.REGISTRY_PATH = os.path.join(
            self.tmp, "proposals", "registry.json")
        self.db_path = os.path.join(self.tmp, "test.sqlite")
        conn, _seed = fresh_fork_b_db(self.db_path)
        conn.commit()
        conn.close()
        self.flag_path = os.path.join(self.tmp, "session.json")
        with open(self.flag_path, "w") as f:
            json.dump({"session_open": False,
                       "world_id": "ironwild-fork-b"}, f)

    def tearDown(self):
        proposals_mod.PROPOSALS_DIR = self._orig_dir
        proposals_mod.REGISTRY_PATH = self._orig_reg

    def _conn(self):
        return db.connect(self.db_path)

    def _last_swept(self):
        conn = self._conn()
        try:
            return db.get_meta(conn, "last_swept_turn")
        finally:
            conn.close()

    def test_gate_next_turn_passes(self):
        conn = self._conn()
        try:
            parsed = sweep_mod.parse_state_block(TURN_1)
            self.assertEqual(
                adapter_mod.check_apply_gate(parsed, conn), 1)
        finally:
            conn.close()

    def test_gate_out_of_order_refused(self):
        conn = self._conn()
        try:
            parsed = sweep_mod.parse_state_block(TURN_2)
            with self.assertRaises(sweep_mod.SweepError) as ctx:
                adapter_mod.check_apply_gate(parsed, conn)
            self.assertIn("expected Turn 1, got Turn 2", str(ctx.exception))
        finally:
            conn.close()

    def test_gate_duplicate_refused(self):
        conn = self._conn()
        try:
            adapter_mod.apply_local_block(
                TURN_1, conn, flag_path=self.flag_path)
        finally:
            conn.close()
        conn = self._conn()
        try:
            parsed = sweep_mod.parse_state_block(TURN_1)
            with self.assertRaises(sweep_mod.SweepError) as ctx:
                adapter_mod.check_apply_gate(
                    parsed, conn,
                    proposals_mod.content_hash(TURN_1))
            self.assertIn("already applied", str(ctx.exception))
        finally:
            conn.close()

    def test_apply_local_block_lands_and_binds(self):
        conn = self._conn()
        try:
            result = adapter_mod.apply_local_block(
                TURN_1, conn, flag_path=self.flag_path)
        finally:
            conn.close()
        self.assertEqual(result["turn"], 1)
        self.assertEqual(result["proposal_binding"]["source"], "local-file")
        self.assertEqual(
            result["proposal_binding"]["content_hash"],
            proposals_mod.content_hash(TURN_1))
        self.assertEqual(self._last_swept(), "1")
        registry = proposals_mod.load_registry()
        entry = registry[result["proposal_binding"]["proposal_id"]]
        self.assertEqual(entry["status"], "applied")

    def test_apply_local_refuses_tampered_stored_file(self):
        conn = self._conn()
        try:
            entry = adapter_mod.register_local_block(
                TURN_1, conn, name="turn-1.txt")
            with open(os.path.join(
                    proposals_mod._proposal_dir(entry["proposal_id"]),
                    "proposal.txt"), "w") as f:
                f.write(TURN_1.replace("Bond 1/5", "Bond 5/5"))
            with self.assertRaises(sweep_mod.SweepError):
                adapter_mod.apply_registered(
                    entry["proposal_id"], conn,
                    flag_path=self.flag_path)
        finally:
            conn.close()
        self.assertIsNone(self._last_swept())

    def test_apply_local_refuses_non_bryan_approver(self):
        conn = self._conn()
        try:
            with self.assertRaises(sweep_mod.SweepError):
                adapter_mod.apply_local_block(
                    TURN_1, conn, approved_by="Case",
                    flag_path=self.flag_path)
        finally:
            conn.close()
        self.assertIsNone(self._last_swept())

    def test_apply_local_refuses_when_session_open(self):
        with open(self.flag_path, "w") as f:
            json.dump({"session_open": True,
                       "world_id": "ironwild-fork-b", "turn": 1,
                       "opened_at": "2026-11-22",
                       "opened_by": "hub"}, f)
        conn = self._conn()
        try:
            with self.assertRaises(sweep_mod.SweepError):
                adapter_mod.apply_local_block(
                    TURN_1, conn, flag_path=self.flag_path)
        finally:
            conn.close()
        self.assertIsNone(self._last_swept())

    def test_apply_local_refuses_validation_errors(self):
        bad = TURN_1.replace("Ashfang is Bond 1/5",
                             "Zorg is Bond 1/5")
        conn = self._conn()
        try:
            with self.assertRaises(sweep_mod.SweepError):
                adapter_mod.apply_local_block(
                    bad, conn, flag_path=self.flag_path)
        finally:
            conn.close()
        self.assertIsNone(self._last_swept())

    def test_drive_path_gate_refuses_out_of_order(self):
        # The Drive path gets the same gate: a Turn 2 proposal on a
        # fresh DB (last swept: none, expected Turn 1) refuses.
        conn = self._conn()
        try:
            entry = proposals_mod.intake_file(
                "drive-test-2", "turn-2.txt", TURN_2, conn)
            self.assertEqual(entry["status"], "reviewed")
            with mock.patch("src.drive_io.download_text",
                            return_value=TURN_2):
                with self.assertRaises(sweep_mod.SweepError) as ctx:
                    proposals_mod.apply_proposal(
                        entry["proposal_id"], conn, "Bryan")
            self.assertIn("expected Turn 1, got Turn 2",
                          str(ctx.exception))
        finally:
            conn.close()
        self.assertIsNone(self._last_swept())


if __name__ == "__main__":
    unittest.main()
