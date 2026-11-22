"""Tests for Step 1 slice 1: BEGIN IMMEDIATE per tick/sweep,
applied_turns, UNIQUE prev_hash, halt rolls back the tick."""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import apply_adapter as adapter_mod  # noqa: E402
from src import db, events  # noqa: E402
from src import proposals as proposals_mod  # noqa: E402
from src import sweep as sweep_mod  # noqa: E402
from src import tick as tick_mod  # noqa: E402
from tests.helpers import fresh_fork_b_db  # noqa: E402
from tests.test_apply_adapter import TURN_1  # noqa: E402


class Slice1TestCase(unittest.TestCase):
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

    def _tick(self):
        conn = self._conn()
        try:
            return db.get_tick(conn)
        finally:
            conn.close()

    def _event_count(self):
        conn = self._conn()
        try:
            return events.count_events(conn)
        finally:
            conn.close()

    def test_second_writer_blocks_tick(self):
        # A second connection holding an immediate transaction makes
        # run_ticks fail loudly instead of interleaving.
        holder = db.connect(self.db_path)
        holder.execute("BEGIN IMMEDIATE")
        try:
            conn = self._conn()
            conn.execute("PRAGMA busy_timeout = 100")
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    tick_mod.run_ticks(conn, 1)
            finally:
                conn.close()
        finally:
            holder.rollback()
            holder.close()
        self.assertEqual(self._tick(), 0)
        self.assertEqual(self._event_count(), 0)

    def test_tick_atomic_on_non_halt_error(self):
        def _boom(conn, tick, rng, catalog, legacy, era_length,
                  has_engine_actions, **kwargs):
            events.append_event(conn, tick, "test", "marker",
                                None, None, [{"op": "note", "text": "x"}])
            db.set_meta(conn, "marker", "x")
            raise RuntimeError("boom")

        conn = self._conn()
        try:
            with mock.patch("src.tick._run_one_tick",
                            side_effect=_boom):
                with self.assertRaises(RuntimeError):
                    tick_mod.run_ticks(conn, 1)
            self.assertEqual(db.get_tick(conn), 0)
            self.assertEqual(events.count_events(conn), 0)
            self.assertIsNone(db.get_meta(conn, "marker"))
        finally:
            conn.close()

    def test_halt_rolls_back_tick_and_writes_only_a_halt_record(self):
        def _halt(conn, tick, rng, catalog, legacy, era_length,
                  has_engine_actions, **kwargs):
            events.append_event(conn, tick, "test", "marker",
                                None, None, [{"op": "note", "text": "x"}])
            db.set_meta(conn, "marker", "x")
            raise tick_mod.EngineHalt("test halt")

        conn = self._conn()
        try:
            with mock.patch("src.tick._run_one_tick",
                            side_effect=_halt):
                with self.assertRaises(tick_mod.EngineHalt):
                    tick_mod.run_ticks(conn, 1)
            # The tick number did not advance and the partial work
            # is gone; exactly one halt record exists.
            self.assertEqual(db.get_tick(conn), 0)
            self.assertIsNone(db.get_meta(conn, "marker"))
            rows = conn.execute(
                "SELECT tick, actor_id, action, effect FROM events"
                ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["action"], "halt")
            self.assertEqual(rows[0]["actor_id"], "engine")
            self.assertEqual(rows[0]["tick"], 0)
            self.assertIn("halt at tick 1: test halt",
                          rows[0]["effect"])
            # A retry re-runs the SAME tick (not a new one).
            tick_mod.run_ticks(conn, 1)
            self.assertEqual(db.get_tick(conn), 1)
        finally:
            conn.close()

    def test_halt_on_second_tick_of_three(self):
        def _halt_on_two(conn, tick, rng, catalog, legacy,
                         era_length, has_engine_actions, **kwargs):
            events.append_event(
                conn, tick, "test", "marker_%d" % tick, None, None,
                [{"op": "note", "text": "x"}])
            if tick == 2:
                raise tick_mod.EngineHalt("halt on two")

        conn = self._conn()
        try:
            with mock.patch("src.tick._run_one_tick",
                            side_effect=_halt_on_two):
                with self.assertRaises(tick_mod.EngineHalt):
                    tick_mod.run_ticks(conn, 3)
            # One tick completed; the halted tick's work is gone.
            self.assertEqual(db.get_tick(conn), 1)
            actions = [r["action"] for r in conn.execute(
                "SELECT action FROM events ORDER BY id").fetchall()]
            self.assertIn("marker_1", actions)
            self.assertNotIn("marker_2", actions)
            self.assertIn("halt", actions)
            halt = conn.execute(
                "SELECT tick FROM events WHERE action = 'halt'"
                ).fetchone()
            self.assertEqual(halt["tick"], 1)
        finally:
            conn.close()

    def test_applied_turns_row_written_in_same_transaction(self):
        conn = self._conn()
        try:
            result = adapter_mod.apply_local_block(
                TURN_1, conn, flag_path=self.flag_path)
        finally:
            conn.close()
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM applied_turns WHERE turn = 1"
                ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["content_hash"],
                             proposals_mod.content_hash(TURN_1))
            self.assertEqual(row["state_version"], "ForkB-v1.0")
            self.assertEqual(row["approver"], "Bryan")
            self.assertEqual(row["source"], "local-file")
            self.assertEqual(row["proposal_id"],
                             result["proposal_binding"]["proposal_id"])
            self.assertEqual(row["applied_at"],
                             result["proposal_binding"]["applied_at"])
        finally:
            conn.close()

    def test_applied_turns_blocks_reapply_after_registry_reset(self):
        conn = self._conn()
        try:
            result = adapter_mod.apply_local_block(
                TURN_1, conn, flag_path=self.flag_path)
        finally:
            conn.close()
        # Simulate a registry loss: the entry goes back to reviewed.
        registry = proposals_mod.load_registry()
        pid = result["proposal_binding"]["proposal_id"]
        registry[pid]["status"] = "reviewed"
        registry[pid].pop("applied_at", None)
        proposals_mod.save_registry(registry)
        conn = self._conn()
        try:
            with self.assertRaises(sweep_mod.SweepError) as ctx:
                adapter_mod.apply_local_block(
                    TURN_1, conn, flag_path=self.flag_path)
            self.assertIn("already applied", str(ctx.exception))
        finally:
            conn.close()
        self.assertEqual(self._tick(), 0)

    def test_unique_prev_hash_index(self):
        conn = self._conn()
        try:
            tick_mod.run_ticks(conn, 3)
            db.init_schema(conn)
            index = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='index' "
                "AND name='idx_events_prev_hash'").fetchone()[0]
            self.assertEqual(index, 1)
            prev = conn.execute(
                "SELECT prev_hash FROM events ORDER BY id LIMIT 1"
                ).fetchone()["prev_hash"]
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO events (tick, actor_id, action, effect, "
                    "prev_hash, event_hash) VALUES (99, 'test', 'x', "
                    "'[]', ?, 'deadbeef')", (prev,))
        finally:
            conn.close()

    def test_migrate_idempotent_and_safe(self):
        conn = self._conn()
        try:
            tick_mod.run_ticks(conn, 5)
            before_events = events.count_events(conn)
            before_hash = db.state_hash(conn)
            db.init_schema(conn)
            db.init_schema(conn)
            self.assertEqual(events.count_events(conn), before_events)
            self.assertEqual(db.state_hash(conn), before_hash)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM applied_turns"
                             ).fetchone()[0], 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
