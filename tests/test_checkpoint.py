"""Checkpoint tests — the every-3-turns audit (Phase 2 harness)."""

import json
import os
import random
import tempfile
import unittest

from helpers import INTERNAL_SEED_PATH, fresh_fork_db
from src import checkpoint as checkpoint_mod, db, events, sweep as sweep_mod
from src import tick as tick_mod


def _fork_block(turn=132, version="vFINAL.1",
                clocks="Dust-Baron Retaliation 2/6", sledge_bond=4):
    pc = ("Brigus, Seedborn / King of the Great Basin. Wounds: None. "
          "Engines: Gold Sledge, Bulwark, Bond %d/5; Skytalon, Bond 5/5; "
          "Razor-Back, Bond 3/5; Goliath Dreadnought, Bond 5/5; "
          "Surveyor-Strider, Bond 5/5. Pack: Vance, Tull, Kaelen, "
          "Nest-Keeper." % sledge_bond)
    return ("[TURN STATE]\n"
            "Universe: Ironwild | State-Version: %s | Turn: %d\n"
            "Clocks: %s\n"
            "Scene: Great Basin | SCENE_TENSION: Low | "
            "ACTIVE_TRADE_OFF: none\n"
            "Player character: %s\n"
            "Unresolved Decisions: none\n"
            "[/TURN STATE]\n"
            % (version, turn, clocks, pc))


class TestCheckpoint(unittest.TestCase):
    def test_audit_matches_then_drifts(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "fork.sqlite")
            conn, _ = fresh_fork_db(db_path)
            parsed = sweep_mod.parse_state_block(_fork_block())
            flag = os.path.join(tmp, "session.json")
            result = sweep_mod.apply_sweep(parsed, conn, approved_by="Bryan",
                                           flag_path=flag)
            conn.commit()
            carried_path = os.path.join(tmp, "carried.json")
            with open(carried_path, "w") as f:
                json.dump(result["carried"], f)
            out = os.path.join(tmp, "checkpoint")
            text, drift = checkpoint_mod.audit(db_path, [carried_path], out)
            self.assertEqual(drift, 0)
            self.assertIn("Gold Sledge: block 4, DB now 4 — MATCH", text)
            self.assertIn("Dust-Baron Retaliation: block 2/6, DB now 2/6"
                          " — MATCH", text)
            self.assertIn("Pending decision (verbatim): none", text)
            self.assertIn("Acceptance: PASS (0 failure(s))", text)
            # Simulate the DB moving after the sweep: a later tick
            # drops Sledge back to 3. The next audit must flag it.
            conn.execute("UPDATE bonds SET bond = 3 "
                         "WHERE engine_id = 'sledge'")
            conn.commit()
            conn.close()
            text, drift = checkpoint_mod.audit(db_path, [carried_path], out)
            self.assertEqual(drift, 1)
            self.assertIn("Gold Sledge: block 4, DB now 3 — DRIFT", text)
            self.assertIn("Acceptance: FAIL (2 failure(s))", text)
            self.assertTrue(os.path.exists(
                os.path.join(out, "state.sqlite")))
            self.assertTrue(os.path.exists(
                os.path.join(out, "state.json")))
            with open(os.path.join(out, "state.json")) as f:
                summary = json.load(f)
            self.assertEqual(summary["drift"], 1)
            self.assertEqual(summary["acceptance"], "FAIL")
            # The checkpoint DB copy keeps a valid hash chain.
            from src import db as db_mod
            copy = db_mod.connect(os.path.join(out, "state.sqlite"))
            ok, _ = events.verify_chain(copy)
            self.assertTrue(ok)
            copy.close()

    def test_pending_decision_comes_from_latest_turn(self):
        # A null pending decision in the latest turn means the
        # decision was answered (Turn 134), not missing: the audit
        # must say "none", not fall back to an older answered
        # question (Turn 133's elite-force decision).
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "fork.sqlite")
            conn, _ = fresh_fork_db(db_path)
            flag = os.path.join(tmp, "session.json")
            pc = ("Brigus, Seedborn / King of the Great Basin. "
                  "Wounds: None. Engines: Gold Sledge, Bulwark, "
                  "Bond 4/5; Skytalon, Bond 5/5; Razor-Back, Bond 3/5; "
                  "Goliath Dreadnought, Bond 5/5; Surveyor-Strider, "
                  "Bond 5/5. Pack: Vance, Tull, Kaelen, Nest-Keeper.")
            block1 = ("[TURN STATE]\n"
                      "Universe: Ironwild | State-Version: ForkA-vFINAL.1 "
                      "| Turn: 132\n"
                      "Clocks: Dust-Baron Retaliation 2/6\n"
                      "Scene: Great Basin | SCENE_TENSION: Low | "
                      "ACTIVE_TRADE_OFF: none\n"
                      "Player character: %s\n"
                      "Unresolved Decisions: \"What kind of elite force "
                      "should the engineers develop?\"\n"
                      "[/TURN STATE]\n" % pc)
            parsed1 = sweep_mod.parse_state_block(block1)
            result1 = sweep_mod.apply_sweep(parsed1, conn,
                                            approved_by="Bryan",
                                            flag_path=flag)
            conn.commit()
            carried1 = os.path.join(tmp, "carried-132.json")
            with open(carried1, "w") as f:
                json.dump(result1["carried"], f)
            block2 = _fork_block(turn=133, version="ForkA-vFINAL.2")
            parsed2 = sweep_mod.parse_state_block(block2)
            result2 = sweep_mod.apply_sweep(parsed2, conn,
                                            approved_by="Bryan",
                                            flag_path=flag)
            conn.commit()
            carried2 = os.path.join(tmp, "carried-133.json")
            with open(carried2, "w") as f:
                json.dump(result2["carried"], f)
            conn.close()
            out = os.path.join(tmp, "checkpoint")
            text, drift = checkpoint_mod.audit(db_path,
                                               [carried1, carried2], out)
            self.assertIn("Pending decision (verbatim): none", text)
            self.assertNotIn("What kind of elite force", text)

    def test_acceptance_fails_on_tampered_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "fork.sqlite")
            conn, _ = fresh_fork_db(db_path)
            # An event with an action no catalog or engine step makes,
            # and an event whose effects mention the frozen sequel.
            events.append_event(conn, 1, "sweep", "teleport", None, None,
                                [{"op": "note", "text": "x"}])
            events.append_event(conn, 1, "brigus", "hunt", None, None,
                                [{"op": "note",
                                  "text": "Krov approaches"}])
            conn.commit()
            conn.close()
            out = os.path.join(tmp, "checkpoint")
            text, drift = checkpoint_mod.audit(db_path, [], out)
            self.assertIn("Acceptance: FAIL", text)
            self.assertIn("1 unknown action(s)", text)
            self.assertIn("1 frozen-term event(s)", text)

    def test_world_state_resources_replay(self):
        # Salvage/Feed/Cores in the DB equal the seed plus the event
        # deltas, after real ticks.
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "fork.sqlite")
            conn, _ = fresh_fork_db(db_path)
            tick_mod.run_ticks(conn, 10, rng=random.Random(131))
            conn.commit()
            conn.close()
            out = os.path.join(tmp, "checkpoint")
            text, _ = checkpoint_mod.audit(
                db_path, [], out, seed_path=INTERNAL_SEED_PATH)
            self.assertIn("Resource replay (seed + event deltas): "
                          "0 mismatch(es)", text)
            self.assertIn("0 negative row(s)", text)

    def test_world_state_territory_stale_when_location_flips(self):
        # Territory is a seed value the engine never maintains: flip a
        # location's controller by hand and the checkpoint must show
        # the staleness, not hide it.
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "fork.sqlite")
            conn, _ = fresh_fork_db(db_path)
            conn.execute("UPDATE locations SET controller_faction_id = "
                         "'ironwild_legion' WHERE id = 'rust_dunes'")
            conn.commit()
            conn.close()
            out = os.path.join(tmp, "checkpoint")
            text, _ = checkpoint_mod.audit(
                db_path, [], out, seed_path=INTERNAL_SEED_PATH)
            # Legion holds 2 in the seed but controls 3 now.
            self.assertIn("Territory ironwild_legion: 2 — STALE "
                          "(controls 3)", text)

    def test_world_state_version_pack_locations_rumors(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "fork.sqlite")
            conn, _ = fresh_fork_db(db_path)
            parsed = sweep_mod.parse_state_block(_fork_block())
            flag = os.path.join(tmp, "session.json")
            result = sweep_mod.apply_sweep(parsed, conn, approved_by="Bryan",
                                           flag_path=flag)
            events.append_event(
                conn, 1, "caravan_master", "trade_concord", None, None,
                [{"op": "resource_move", "from": "ironwild_legion",
                  "from_kind": "faction", "to": "caravan_concord",
                  "to_kind": "faction", "resource": "Feed", "qty": 2}])
            conn.commit()
            carried_path = os.path.join(tmp, "carried.json")
            with open(carried_path, "w") as f:
                json.dump(result["carried"], f)
            conn.close()
            out = os.path.join(tmp, "checkpoint")
            text, _ = checkpoint_mod.audit(db_path, [carried_path], out)
            self.assertIn("State version: ledger Turn 132 vFINAL.1 vs "
                          "last approved block Turn 132 vFINAL.1 — MATCH",
                          text)
            self.assertIn("Pack: Vance, Tull, Kaelen, Nest-Keeper", text)
            self.assertIn("Brigus", text)
            self.assertIn("Great Basin", text)
            self.assertIn("the caravan hears trade is moving again",
                          text)
            self.assertRegex(text, r"\[event \d+\] Rumor \(unverified\):")


if __name__ == "__main__":
    unittest.main()
