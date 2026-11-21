"""World-view JSON export tests (Companion integration, Phase 2 item 4).

The export is the stable JSON the Companion app reads through its
own import action; the engine never writes app.db. Tested against
a scratch fork DB (never the live test DB):
- a fresh fork exports the tick-0 state (4 clocks 0/6, 5 engines
  with Bonds 3/5/3/5/5, seed resources, no events);
- a carried record supplies the scene/tension/trade-off/decision
  the DB does not hold;
- the CLI writes the stable path runs/<world>/world-view.json when
  --out is omitted.
"""

import argparse
import json
import os
import tempfile
import unittest
from unittest import mock

from src import render as render_mod
from src import run as run_mod
from tests.helpers import fresh_fork_db


class TestRenderWorldViewJson(unittest.TestCase):
    def test_fresh_fork_exports_tick_zero_state(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "world-view.json")
            render_mod.render_world_view_json(conn, out)
            with open(out, encoding="utf-8") as f:
                view = json.load(f)
        self.assertEqual(view["world_id"], "ironwild-fork-a")
        self.assertEqual(view["tick"], 0)
        self.assertEqual(len(view["clocks"]), 4)
        self.assertTrue(all(c["value"] == 0 and c["max"] == 6
                            for c in view["clocks"]))
        bonds = {e["id"]: e["bond"] for e in view["engines"]}
        self.assertEqual(bonds, {"sledge": 3, "skytalon": 5,
                                 "razor_back": 3, "goliath": 5,
                                 "strider": 5})
        self.assertEqual(view["recent_events"], [])
        self.assertIsNone(view["last_swept_turn"])
        self.assertIsNone(view["last_swept_version"])
        self.assertEqual(view["pending_decision"], "")
        self.assertIsNone(view["scene"])
        legion_salvage = [r for r in view["resources"]
                          if r["holder_id"] == "ironwild_legion"
                          and r["resource"] == "Salvage"][0]
        self.assertEqual(legion_salvage["qty"], 12)
        conn.close()

    def test_carried_record_supplies_scene_fields(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        carried = {"scene": "Great Basin — Legion Engineering Grounds",
                   "scene_tension": "Low",
                   "active_trade_off": "Elite unit vs welfare.",
                   "pending_decision": "What kind of elite force?"}
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "world-view.json")
            render_mod.render_world_view_json(conn, out, carried=carried)
            with open(out, encoding="utf-8") as f:
                view = json.load(f)
        self.assertEqual(view["scene"],
                         "Great Basin — Legion Engineering Grounds")
        self.assertEqual(view["scene_tension"], "Low")
        self.assertEqual(view["active_trade_off"], "Elite unit vs welfare.")
        self.assertEqual(view["pending_decision"],
                         "What kind of elite force?")
        conn.close()

    def test_cli_writes_stable_path_when_out_omitted(self):
        tmp_db = os.path.join(tempfile.mkdtemp(), "fork.sqlite")
        conn, _ = fresh_fork_db(tmp_db)
        conn.close()
        with tempfile.TemporaryDirectory() as tmp:
            runs = os.path.join(tmp, "runs")
            with mock.patch.dict(os.environ,
                                 {"IRONWILD_RUNS_DIR": runs}):
                args = argparse.Namespace(db=tmp_db, out=None,
                                          format="json", carried=None)
                run_mod.cmd_render(args)
            out = os.path.join(runs, "ironwild-fork-a", "world-view.json")
            self.assertTrue(os.path.exists(out))
            with open(out, encoding="utf-8") as f:
                view = json.load(f)
            self.assertEqual(view["world_id"], "ironwild-fork-a")
            self.assertEqual(view["tick"], 0)


if __name__ == "__main__":
    unittest.main()
