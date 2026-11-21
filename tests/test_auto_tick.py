"""Auto-tick tests — the daily runner (Phase 2 item 1)."""

import json
import os
import tempfile
import unittest

from helpers import fresh_fork_db
from src import auto_tick as auto_tick_mod, db, sweep as sweep_mod


def _fork_block(turn=132, unresolved="none"):
    pc = ("Brigus, Seedborn / King of the Great Basin. Wounds: None. "
          "Engines: Gold Sledge, Bulwark, Bond 3/5; Skytalon, Bond 5/5; "
          "Razor-Back, Bond 3/5; Goliath Dreadnought, Bond 5/5; "
          "Surveyor-Strider, Bond 5/5. Pack: Vance, Tull, Kaelen, "
          "Nest-Keeper.")
    return ("[TURN STATE]\n"
            "Universe: Ironwild | State-Version: vFINAL.1 | Turn: %d\n"
            "Clocks: Dust-Baron Retaliation 0/6\n"
            "Scene: Great Basin | SCENE_TENSION: Low | "
            "ACTIVE_TRADE_OFF: none\n"
            "Player character: %s\n"
            "Unresolved Decisions: %s\n"
            "[/TURN STATE]\n" % (turn, pc, unresolved))


class TestAutoTick(unittest.TestCase):
    def setUp(self):
        # Keep test runs out of the real runs/auto/ log dir.
        self._tmp = tempfile.TemporaryDirectory()
        self._runs_dir = os.path.join(self._tmp.name, "auto")
        self._orig_runs_dir = auto_tick_mod.RUNS_DIR
        auto_tick_mod.RUNS_DIR = self._runs_dir

    def tearDown(self):
        auto_tick_mod.RUNS_DIR = self._orig_runs_dir
        self._tmp.cleanup()

    def _flag(self, tmp, open_=False):
        path = os.path.join(tmp, "session.json")
        with open(path, "w") as f:
            json.dump({"session_open": open_,
                       "world_id": "ironwild-fork-a",
                       "opened_at": None, "opened_by": None,
                       "turn": None}, f)
        return path

    def test_ticks_once_and_refuses_same_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "fork.sqlite")
            conn, _ = fresh_fork_db(db_path)
            conn.close()
            flag = self._flag(tmp)
            first = auto_tick_mod.run_auto_tick(
                db_path, today="2026-11-21", flag_path=flag)
            self.assertEqual(first["outcome"], "ticked")
            self.assertEqual(first["tick"], 1)
            self.assertGreater(first["events_after"],
                               first["events_before"])
            self.assertTrue(os.path.exists(os.path.join(
                self._runs_dir, "2026-11-21", "tick.log")))
            second = auto_tick_mod.run_auto_tick(
                db_path, today="2026-11-21", flag_path=flag)
            self.assertEqual(second["outcome"], "refused")
            self.assertIn("already_ticked_today", second["reason"])
            third = auto_tick_mod.run_auto_tick(
                db_path, today="2026-11-22", flag_path=flag)
            self.assertEqual(third["outcome"], "ticked")
            self.assertEqual(third["tick"], 2)

    def test_refuses_when_session_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "fork.sqlite")
            conn, _ = fresh_fork_db(db_path)
            conn.close()
            flag = self._flag(tmp, open_=True)
            result = auto_tick_mod.run_auto_tick(
                db_path, today="2026-11-21", flag_path=flag)
            self.assertEqual(result["outcome"], "refused")
            self.assertIn("session_open", result["reason"])
            self.assertEqual(result["tick"], 0)

    def test_refuses_on_pending_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "fork.sqlite")
            conn, _ = fresh_fork_db(db_path)
            parsed = sweep_mod.parse_state_block(
                _fork_block(unresolved="Choose the road north or south."))
            sweep_mod.apply_sweep(parsed, conn, approved_by="Bryan",
                                  flag_path=self._flag(tmp))
            conn.commit()
            conn.close()
            flag = self._flag(tmp)
            result = auto_tick_mod.run_auto_tick(
                db_path, today="2026-11-21", flag_path=flag)
            self.assertEqual(result["outcome"], "refused")
            self.assertIn("pending_decision", result["reason"])
            # Resolving the decision (a later block with none) lets
            # the world tick again.
            conn = db.connect(db_path)
            parsed = sweep_mod.parse_state_block(_fork_block(turn=133))
            sweep_mod.apply_sweep(parsed, conn, approved_by="Bryan",
                                  flag_path=flag)
            conn.commit()
            conn.close()
            result = auto_tick_mod.run_auto_tick(
                db_path, today="2026-11-21", flag_path=flag)
            self.assertEqual(result["outcome"], "ticked")

    def test_pending_decision_recorded_in_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "fork.sqlite")
            conn, _ = fresh_fork_db(db_path)
            flag = self._flag(tmp)
            parsed = sweep_mod.parse_state_block(
                _fork_block(unresolved="Choose the road north or south."))
            sweep_mod.apply_sweep(parsed, conn, approved_by="Bryan",
                                  flag_path=flag)
            self.assertEqual(
                db.get_meta(conn, "pending_decision"),
                "Choose the road north or south.")
            parsed = sweep_mod.parse_state_block(_fork_block(turn=133))
            sweep_mod.apply_sweep(parsed, conn, approved_by="Bryan",
                                  flag_path=flag)
            self.assertEqual(db.get_meta(conn, "pending_decision"), "")
            conn.close()


if __name__ == "__main__":
    unittest.main()
