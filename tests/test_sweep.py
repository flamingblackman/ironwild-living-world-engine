"""Sweep tests — the V2 [TURN STATE] parser, validator, diff, and
approval-gated apply (Phase 2 harness).

Sample blocks A/B/C are copied verbatim from Lore's Phase 2 inputs
(living-world-engine/lore-phase-2-inputs.md, section 1).
"""

import json
import os
import tempfile
import unittest

from helpers import fresh_fork_db
from src import db, events, sweep as sweep_mod

SAMPLE_A = """[TURN STATE]
Universe: Ironwild | State-Version: vFINAL (v3.00.2) | Turn: 131
Clocks: Rift-King Battle resolved (Rift-King annihilated in the Salt Flats) | Deepmaw Migration diverted by the Acoustic Lure | Concord War N/A | Famine N/A
Scene: Salt Flats (final battle) / Great Basin (post-victory) | SCENE_TENSION: Low | ACTIVE_TRADE_OFF: none
Player character: Brigus, Seedborn / King of the Great Basin. Wounds: None. Status: exhausted after the Feral God merge, victorious. King is a Beacon. Engines: Gold Sledge, black-and-gold gorilla Bulwark, Bond 3/5, Titanium-Cestus (Diamond-Claw melted Turn 126), Sentient Seat (neural, NOT a saddle-harness); Skytalon, ADULT Shadow-Owl, Bond 5/5, Adult Molt triggered Turn 129 after defeating the Grave-Echo blindly, no longer juvenile, no longer hard-light winged; Razor-Back, Bond 3/5 (dropped 5 to 3 in the Turn 128 Pack Merge with Sledge); Goliath Dreadnought, Bond 5/5, pre-war machine, left mortar pod destroyed Turn 112, never reappears; Surveyor-Strider, Bond 5/5, observation and fire-control platform. All Engines exhausted, battered. Pack: Vance, Tull, Queen Kaelen, Nest-Keeper. Ironwild Legion 600 strong, including absorbed Dust-Baron mercenaries.
Unresolved Decisions: none
[/TURN STATE]
"""

SAMPLE_B = """[TURN STATE]
Universe: Ironwild | State-Version: vFINAL.5 | Turn: 136
Clocks: Rider Army Mustering 5/6 | Sanctuary Integration 6/6 (Complete) | Mother-Bulwark Rescue 2/4 | Outer Siege-Ring 4/6 | Northern Pass Approach 6/6 (Detonated)
Scene: Southern Aegis Gatehouse, Aegis Citadel of the Great Basin | SCENE_TENSION: Catastrophic | ACTIVE_TRADE_OFF: Krov ambush response, Option 3 staged with Vance's artillery lock confirmed
Player character: Brigus, Seedborn / King of the Great Basin. Wounds: None. Status: exhausted after the Feral God merge, victorious, now defending the Aegis Citadel. Engines: Gold Sledge, black-and-gold gorilla Bulwark, Bond 3/5, Titanium-Cestus (Diamond-Claw melted Turn 126), Sentient Seat (neural, NOT a saddle-harness); Skytalon, ADULT Shadow-Owl, Bond 5/5, sleek radar-absorbent silent chassis, echolocation, mono-molecular feather-blades, no longer juvenile, no longer hard-light winged; Razor-Back, Bond 3/5, exhausted from the Pack Merge; Goliath Dreadnought, Bond 5/5, pre-war machine; Surveyor-Strider, Bond 5/5. Pack: Vance, Tull, Queen Kaelen, Nest-Keeper. Faction: Ironwild Legion. Vance location: Surveyor-Strider observation / fire-control gantry, locked into its pre-war tactical terminal, targeting synced to the wall's seismic grid, lock on Krov's secondary mortar battery.
Unresolved Decisions: Choose how Brigus responds to War-Skinner Krov's ambush on the wild Mother-Bulwark (carrying 3 Seed Cores) outside the Southern Aegis Gate (Option 3 staged with Vance's artillery lock confirmed on Surveyor-Strider). Options: Execute Option 3 and fire Vance's artillery barrage / Execute Option 3 and hold Vance's fire for the Tortoise / Add Skytalon to sever the harpoon cables during Option 3. Text also allows switching to Option 1 or 2, or a modified command.
[/TURN STATE]
"""

SAMPLE_C = """[TURN STATE]
Universe: Ironwild | State-Version: vFINAL.7 | Turn: 138
Clocks: Rider Army Mustering 5/6 | Sanctuary Integration 6/6 (Complete) | Mother-Bulwark Rescue 3/4 | Outer Siege-Ring 4/6 | Northern Pass Approach 6/6 (Detonated)
Scene: Southern Aegis Gatehouse, Aegis Citadel of the Great Basin | SCENE_TENSION: Catastrophic | ACTIVE_TRADE_OFF: secure the injured Mother-Bulwark inside the Citadel
Player character: Brigus, Seedborn / King of the Great Basin. Wounds: None. Status: exhausted after the Feral God merge, victorious, now defending the Aegis Citadel. Engines: Gold Sledge, black-and-gold gorilla Bulwark, Bond 3/5, Titanium-Cestus (Diamond-Claw melted Turn 126), Sentient Seat (neural, NOT a saddle-harness), shielded the Mother-Bulwark; Skytalon, ADULT Shadow-Owl, Bond 5/5, sleek radar-absorbent silent chassis, echolocation, mono-molecular feather-blades, severed all three harpoon cables; Razor-Back, Bond 3/5, exhausted from the Pack Merge; Goliath Dreadnought, Bond 5/5, pre-war machine; Surveyor-Strider, Bond 5/5. Pack: Vance, Tull, Queen Kaelen, Nest-Keeper. Faction: Ironwild Legion. Mother-Bulwark free, 3 Seed Cores protected, injured (damaged forelimb), not yet inside the Citadel.
Unresolved Decisions: Secure the injured Mother-Bulwark inside the Citadel.
[/TURN STATE]
"""


def _block(turn, version, clocks, pc, unresolved="none",
           tension="Low", scene="Great Basin"):
    return ("[TURN STATE]\n"
            "Universe: Ironwild | State-Version: %s | Turn: %d\n"
            "Clocks: %s\n"
            "Scene: %s | SCENE_TENSION: %s | ACTIVE_TRADE_OFF: none\n"
            "Player character: %s\n"
            "Unresolved Decisions: %s\n"
            "[/TURN STATE]\n"
            % (version, turn, clocks, scene, tension, pc, unresolved))


def _fork_block(turn=132, version="vFINAL.1",
                clocks="Dust-Baron Retaliation 0/6",
                sledge_bond=3):
    pc = ("Brigus, Seedborn / King of the Great Basin. Wounds: None. "
          "Engines: Gold Sledge, Bulwark, Bond %d/5; Skytalon, Bond 5/5; "
          "Razor-Back, Bond 3/5; Goliath Dreadnought, Bond 5/5; "
          "Surveyor-Strider, Bond 5/5. Pack: Vance, Tull, Kaelen, "
          "Nest-Keeper." % sledge_bond)
    return _block(turn, version, clocks, pc)


class TestParseSamples(unittest.TestCase):
    def test_sample_a_parses(self):
        p = sweep_mod.parse_state_block(SAMPLE_A)
        self.assertEqual(p["turn"], 131)
        self.assertEqual(p["state_version"], "vFINAL (v3.00.2)")
        # Sample A's clocks are prose, not Name value/max: carried as
        # text, no clock changes.
        self.assertIsNone(p["clocks"])
        self.assertEqual(
            [(b["engine"], b["bond"]) for b in p["bonds"]],
            [("Gold Sledge", 3), ("Skytalon", 5), ("Razor-Back", 3),
             ("Goliath Dreadnought", 5), ("Surveyor-Strider", 5)])
        self.assertEqual(p["pack"],
                         ["Vance", "Tull", "Queen Kaelen", "Nest-Keeper"])
        self.assertIsNone(p["unresolved_decisions"])
        self.assertEqual(p["scene_tension"], "Low")

    def test_sample_c_parses_clocks(self):
        p = sweep_mod.parse_state_block(SAMPLE_C)
        self.assertEqual(p["turn"], 138)
        self.assertEqual(len(p["clocks"]), 5)
        rescue = [c for c in p["clocks"]
                  if c["name"] == "Mother-Bulwark Rescue"][0]
        self.assertEqual((rescue["value"], rescue["max"]), (3, 4))
        self.assertEqual(p["scene_tension"], "Catastrophic")
        self.assertIsNotNone(p["unresolved_decisions"])

    def test_missing_heading_fails(self):
        with self.assertRaises(sweep_mod.SweepError):
            sweep_mod.parse_state_block("Universe: Ironwild\nTurn: 131\n")

    def test_bond_out_of_range_fails(self):
        bad = SAMPLE_A.replace("Bond 3/5", "Bond 6/5", 1)
        with self.assertRaises(sweep_mod.SweepError):
            sweep_mod.parse_state_block(bad)

    def test_bad_tension_fails(self):
        bad = SAMPLE_A.replace("SCENE_TENSION: Low",
                               "SCENE_TENSION: Apocalyptic")
        with self.assertRaises(sweep_mod.SweepError):
            sweep_mod.parse_state_block(bad)

    def test_missing_pc_line_fails(self):
        bad = SAMPLE_A.replace("Player character: Brigus",
                               "Hero: Brigus")
        with self.assertRaises(sweep_mod.SweepError):
            sweep_mod.parse_state_block(bad)


class TestValidateAndApply(unittest.TestCase):
    def test_sample_a_clean_on_fresh_fork(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        p = sweep_mod.parse_state_block(SAMPLE_A)
        findings = sweep_mod.validate(p, conn)
        self.assertEqual([f for f in findings if f["level"] == "error"], [])
        self.assertTrue(any(f["code"] == "NO_CLOCKS_PARSED"
                            for f in findings))
        self.assertEqual(sweep_mod.diff(p, conn), [])
        conn.close()

    def test_sample_c_flags_unknown_clocks(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        p = sweep_mod.parse_state_block(SAMPLE_C)
        findings = sweep_mod.validate(p, conn)
        self.assertEqual([f for f in findings if f["level"] == "error"], [])
        unknown = [f for f in findings if f["code"] == "CLOCK_UNKNOWN"]
        self.assertEqual(len(unknown), 5)
        self.assertEqual(sweep_mod.diff(p, conn), [])
        conn.close()

    def test_sample_b_frozen(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        p = sweep_mod.parse_state_block(SAMPLE_B)
        findings = sweep_mod.validate(p, conn)
        self.assertTrue(any(f["code"] == "FROZEN_LIVE"
                            and f["level"] == "error" for f in findings))
        with self.assertRaises(sweep_mod.SweepError):
            sweep_mod.apply_sweep(p, conn, approved_by="Bryan")
        conn.close()

    def test_clock_decrease_is_error(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        conn.execute("UPDATE clocks SET value = 1 "
                     "WHERE id = 'dust_baron_retaliation'")
        conn.commit()
        p = sweep_mod.parse_state_block(
            _fork_block(clocks="Dust-Baron Retaliation 0/6"))
        findings = sweep_mod.validate(p, conn)
        self.assertTrue(any(f["code"] == "CLOCK_DECREASE"
                            and f["level"] == "error" for f in findings))
        conn.close()

    def test_clock_increase_applies(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        p = sweep_mod.parse_state_block(
            _fork_block(clocks="Dust-Baron Retaliation 2/6"))
        self.assertEqual([f for f in sweep_mod.validate(p, conn)
                          if f["level"] == "error"], [])
        changes = sweep_mod.diff(p, conn)
        self.assertEqual(len(changes), 1)
        self.assertEqual((changes[0]["kind"], changes[0]["id"],
                          changes[0]["old"], changes[0]["new"]),
                         ("clock", "dust_baron_retaliation", 0, 2))
        with tempfile.TemporaryDirectory() as tmp:
            flag = os.path.join(tmp, "session.json")
            result = sweep_mod.apply_sweep(p, conn, approved_by="Bryan",
                                           flag_path=flag)
        self.assertEqual(result["applied"], changes)
        row = conn.execute("SELECT value FROM clocks "
                           "WHERE id = 'dust_baron_retaliation'").fetchone()
        self.assertEqual(row["value"], 2)
        self.assertEqual(db.get_meta(conn, "last_swept_turn"), "132")
        ok, _ = events.verify_chain(conn)
        self.assertTrue(ok)
        conn.close()

    def test_bond_change_applies(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        p = sweep_mod.parse_state_block(_fork_block(sledge_bond=4))
        changes = sweep_mod.diff(p, conn)
        self.assertEqual(len(changes), 1)
        self.assertEqual((changes[0]["kind"], changes[0]["id"],
                          changes[0]["old"], changes[0]["new"]),
                         ("bond", "sledge", 3, 4))
        with tempfile.TemporaryDirectory() as tmp:
            sweep_mod.apply_sweep(p, conn, approved_by="Bryan",
                                  flag_path=os.path.join(tmp, "s.json"))
        row = conn.execute("SELECT bond FROM bonds "
                           "WHERE engine_id = 'sledge'").fetchone()
        self.assertEqual(row["bond"], 4)
        ok, _ = events.verify_chain(conn)
        self.assertTrue(ok)
        conn.close()

    def test_apply_needs_approver(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        p = sweep_mod.parse_state_block(_fork_block())
        with self.assertRaises(sweep_mod.SweepError):
            sweep_mod.apply_sweep(p, conn, approved_by=None)
        conn.close()

    def test_apply_refused_when_session_open(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        p = sweep_mod.parse_state_block(_fork_block())
        with tempfile.TemporaryDirectory() as tmp:
            flag = os.path.join(tmp, "session.json")
            with open(flag, "w") as f:
                json.dump({"session_open": True, "world_id": "ironwild-fork-a",
                           "opened_at": "2026-11-21T00:00:00",
                           "opened_by": "hub", "turn": 132}, f)
            with self.assertRaises(sweep_mod.SweepError):
                sweep_mod.apply_sweep(p, conn, approved_by="Bryan",
                                      flag_path=flag)
        conn.close()

    def test_stale_proposal_refused(self):
        # An older turn never overwrites newer approved state. A
        # same-turn re-sweep is a flag (review), not an error.
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        with tempfile.TemporaryDirectory() as tmp:
            flag = os.path.join(tmp, "session.json")
            newer = sweep_mod.parse_state_block(_fork_block(turn=134))
            sweep_mod.apply_sweep(newer, conn, approved_by="Bryan",
                                  flag_path=flag)
            stale = sweep_mod.parse_state_block(_fork_block(turn=133))
            findings = sweep_mod.validate(stale, conn)
            self.assertTrue(any(f["code"] == "STALE_PROPOSAL"
                                and f["level"] == "error"
                                for f in findings))
            with self.assertRaises(sweep_mod.SweepError):
                sweep_mod.apply_sweep(stale, conn, approved_by="Bryan",
                                      flag_path=flag)
            same = sweep_mod.parse_state_block(_fork_block(turn=134))
            findings = sweep_mod.validate(same, conn)
            self.assertEqual(
                [f for f in findings if f["level"] == "error"], [])
            self.assertTrue(any(f["code"] == "TURN_ORDER"
                                for f in findings))
        conn.close()

    def test_review_shows_base_vs_approved(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        p = sweep_mod.parse_state_block(_fork_block(turn=132))
        review = sweep_mod.summarize(p, [], [], conn=conn)
        self.assertIn("Based on: Turn 132 vFINAL.1", review)
        self.assertIn("Last approved: Turn - -", review)
        conn.close()

    def test_missing_state_version_is_an_error(self):
        # Every proposal must identify its base version. A block with
        # no State-Version line parses but fails validation.
        block = _fork_block().replace(
            "State-Version: vFINAL.1 | ", "")
        p = sweep_mod.parse_state_block(block)
        self.assertEqual(p["state_version"], "")
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        findings = sweep_mod.validate(p, conn)
        self.assertTrue(any(f["code"] == "NO_VERSION"
                            and f["level"] == "error"
                            for f in findings))
        conn.close()


class TestRealDmBlock(unittest.TestCase):
    """The first real DM block (revised Turn 132, 2026-11-21) exposed
    two parser gaps the synthetic blocks never hit: `;`-separated
    clocks mixing prose context with Name value/max, and a
    "Five Engines, ...:" preamble before the first Bond."""

    def test_clocks_mixed_prose_and_values(self):
        clocks = ("Rift-King Battle resolved (Rift-King annihilated in "
                  "the Salt Flats); Deepmaw Migration diverted by the "
                  "Acoustic Lure; Concord War N/A; Famine N/A; "
                  "Dust-Baron Retaliation 0/6; Concord Blockade 0/6; "
                  "Legion Cohesion 0/6; Great Basin Recovery 1/6 "
                  "(proposed, pending approval)")
        p = sweep_mod.parse_state_block(
            _fork_block(clocks=clocks))
        self.assertEqual(
            [(c["name"], c["value"], c["max"]) for c in p["clocks"]],
            [("Dust-Baron Retaliation", 0, 6),
             ("Concord Blockade", 0, 6),
             ("Legion Cohesion", 0, 6),
             ("Great Basin Recovery", 1, 6)])
        self.assertIsNone(p["clocks"][3]["status"])
        self.assertEqual(len(p["clocks_text"]), 4)

    def test_bonds_colon_preamble(self):
        pc = ("Brigus, Seedborn. Wounds: None. Five Engines, all "
              "exhausted and battered: Gold Sledge, Bulwark, Bond 3/5; "
              "Skytalon, Bond 5/5; Razor-Back, Bond 3/5; Goliath "
              "Dreadnought, Bond 5/5; Surveyor-Strider, Bond 5/5. "
              "Pack: Vance, Tull, Kaelen, Nest-Keeper.")
        p = sweep_mod.parse_state_block(_block(
            132, "ForkA-vFINAL.1", "Dust-Baron Retaliation 0/6", pc))
        self.assertEqual(
            [(b["engine"], b["bond"]) for b in p["bonds"]],
            [("Gold Sledge", 3), ("Skytalon", 5), ("Razor-Back", 3),
             ("Goliath Dreadnought", 5), ("Surveyor-Strider", 5)])

    def test_revised_turn_132_block(self):
        from helpers import ENGINE_DIR
        block_path = os.path.join(
            ENGINE_DIR, "runs", "sweeps", "turn-132", "revised-block.txt")
        with open(block_path) as f:
            p = sweep_mod.parse_state_block(f.read())
        self.assertEqual(p["turn"], 132)
        self.assertEqual(p["state_version"], "ForkA-vFINAL.1")
        self.assertIsNone(p["unresolved_decisions"])
        self.assertEqual(
            [(b["engine"], b["bond"]) for b in p["bonds"]],
            [("Gold Sledge", 3), ("Skytalon", 5), ("Razor-Back", 3),
             ("Goliath Dreadnought", 5), ("Surveyor-Strider", 5)])
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        findings = sweep_mod.validate(p, conn)
        self.assertEqual(
            [f for f in findings if f["level"] == "error"], [])
        self.assertFalse(any(f["code"] == "NO_CLOCKS_PARSED"
                             for f in findings))
        self.assertFalse(any(f["code"] == "ENGINE_UNKNOWN"
                             for f in findings))
        changes = sweep_mod.diff(p, conn)
        self.assertEqual(
            [(c["kind"], c["id"], c["old"], c["new"]) for c in changes],
            [("clock", "great_basin_recovery", 0, 1)])
        conn.close()

    def test_revised_turn_132_applies_with_salvage(self):
        # The V2 block has no Resources field, so the hub-approved
        # Legion Salvage 12 -> 11 arrives as an explicit resource
        # change and lands in the same transaction as the clock.
        from helpers import ENGINE_DIR
        block_path = os.path.join(
            ENGINE_DIR, "runs", "sweeps", "turn-132", "revised-block.txt")
        with open(block_path) as f:
            p = sweep_mod.parse_state_block(f.read())
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        rc = [{"holder": "ironwild_legion", "holder_kind": "faction",
               "resource": "Salvage", "old": 12, "new": 11}]
        result = sweep_mod.apply_sweep(p, conn, "Bryan",
                                       resource_changes=rc)
        self.assertEqual(
            [(c["kind"], c.get("id") or c.get("resource"), c["old"],
              c["new"]) for c in result["applied"]],
            [("clock", "great_basin_recovery", 0, 1),
             ("resource", "Salvage", 12, 11)])
        row = conn.execute(
            "SELECT qty FROM resources WHERE holder_id = ? "
            "AND resource = ?", ("ironwild_legion", "Salvage")
            ).fetchone()
        self.assertEqual(row[0], 11)
        actions = [r[0] for r in conn.execute(
            "SELECT action FROM events ORDER BY id").fetchall()]
        self.assertEqual(actions,
                         ["sweep_clock", "sweep_resource", "sweep"])
        self.assertEqual(result["carried"]["resources"], [
            {"kind": "resource", "holder": "ironwild_legion",
             "holder_kind": "faction", "resource": "Salvage",
             "old": 12, "new": 11}])
        self.assertEqual(db.get_meta(conn, "last_swept_turn"), "132")
        self.assertEqual(db.get_meta(conn, "pending_decision"), "")
        conn.close()

    def test_resource_change_refuses_stale_base(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        p = sweep_mod.parse_state_block(_fork_block())
        rc = [{"holder": "ironwild_legion", "holder_kind": "faction",
               "resource": "Salvage", "old": 11, "new": 10}]
        with self.assertRaises(sweep_mod.SweepError):
            sweep_mod.diff(p, conn, rc)
        conn.close()


if __name__ == "__main__":
    unittest.main()
