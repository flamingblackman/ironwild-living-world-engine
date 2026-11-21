"""0-change auto-apply tests (Bryan's standing approval, 2026-11-21),
narrowed by Lore's canon guard (lore-auto-apply-guard.md).

Eligibility is the gate: a clean 0-change proposal auto-applies;
anything with a change, a finding, a wrong turn/version, a Base
mismatch, a new pending decision, or a RESOLVED pending decision
(the Turn 134 class — 0 mechanical changes but the decision got
answered) comes to Bryan. A 0-change proposal that carries a
narrative change the sweep cannot validate (scene change, new PC
fact, status mismatch, no baseline) goes to Lore for a call. The
refusal and Lore-call paths must not touch the DB.
"""

import json
import os
import tempfile
import unittest

from src import auto_apply as auto_apply_mod
from src import proposals as proposals_mod
from src import run as run_mod
from src import session as session_mod
from src import sweep as sweep_mod
from tests.helpers import fresh_fork_db

_PC = ("Brigus, Seedborn / King of the Great Basin. Wounds: None. "
       "Engines: Gold Sledge, Bulwark, Bond 3/5; Skytalon, Bond 5/5; "
       "Razor-Back, Bond 3/5; Goliath Dreadnought, Bond 5/5; "
       "Surveyor-Strider, Bond 5/5. Pack: Vance, Tull, Kaelen, "
       "Nest-Keeper.")

_CLOCKS_0 = ("Dust-Baron Retaliation 0/6; Concord Blockade 0/6; "
             "Legion Cohesion 0/6; Great Basin Recovery 0/6")


def _block(turn=132, version="ForkA-vFINAL.1", clocks=_CLOCKS_0,
           decisions="none", base=None,
           scene="Great Basin | SCENE_TENSION: Low | "
                 "ACTIVE_TRADE_OFF: none",
           pc=_PC):
    lines = ["[TURN STATE]",
             "Universe: Ironwild | State-Version: %s | Turn: %d"
             % (version, turn)]
    if base:
        lines[1] += " | Base: %s" % base
    lines += ["Clocks: %s" % clocks,
              "Scene: %s" % scene,
              "Player character: %s" % pc,
              "Unresolved Decisions: %s" % decisions,
              "[/TURN STATE]"]
    return "\n".join(lines) + "\n"


def _check(block, conn, flag_path=None):
    parsed = sweep_mod.parse_state_block(block)
    findings = (sweep_mod.validate(parsed, conn)
                + proposals_mod.validate_fork(parsed, "ironwild-fork-a"))
    changes = sweep_mod.diff(parsed, conn)
    return auto_apply_mod.check_eligible(parsed, findings, changes,
                                         conn, flag_path)


def _messages(reasons):
    return [r["message"] for r in reasons]


class TestAutoApplyEligible(unittest.TestCase):
    def test_clean_zero_change_is_eligible(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        flag = os.path.join(tempfile.mkdtemp(), "session.json")
        eligible, reasons = _check(_block(), conn, flag)
        self.assertTrue(eligible)
        self.assertEqual(reasons, [])
        conn.close()

    def test_clock_change_is_not_eligible(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        flag = os.path.join(tempfile.mkdtemp(), "session.json")
        block = _block(clocks="Dust-Baron Retaliation 1/6; "
                              "Concord Blockade 0/6; Legion Cohesion 0/6; "
                              "Great Basin Recovery 0/6")
        eligible, reasons = _check(block, conn, flag)
        self.assertFalse(eligible)
        self.assertTrue(any("1 change" in m for m in _messages(reasons)))
        conn.close()

    def test_finding_is_not_eligible(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        flag = os.path.join(tempfile.mkdtemp(), "session.json")
        block = _block(clocks="Mystery Clock 1/6")
        eligible, reasons = _check(block, conn, flag)
        self.assertFalse(eligible)
        self.assertTrue(any("CLOCK_UNKNOWN" in m
                            for m in _messages(reasons)))
        conn.close()

    def test_wrong_turn_is_not_eligible(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        flag = os.path.join(tempfile.mkdtemp(), "session.json")
        eligible, reasons = _check(_block(turn=134,
                                          version="ForkA-vFINAL.3"),
                                   conn, flag)
        self.assertFalse(eligible)
        self.assertTrue(any("not the next turn (132)" in m
                            for m in _messages(reasons)))
        conn.close()

    def test_wrong_version_is_not_eligible(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        flag = os.path.join(tempfile.mkdtemp(), "session.json")
        eligible, reasons = _check(_block(version="ForkA-vFINAL.2"),
                                   conn, flag)
        self.assertFalse(eligible)
        self.assertTrue(any("not the expected next version" in m
                            for m in _messages(reasons)))
        conn.close()

    def test_base_mismatch_is_not_eligible(self):
        tmp = tempfile.mkdtemp()
        conn, _ = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
        flag = os.path.join(tmp, "session.json")
        parsed = sweep_mod.parse_state_block(_block())
        sweep_mod.apply_sweep(parsed, conn, approved_by="Bryan",
                              flag_path=flag)
        conn.commit()
        block = _block(turn=133, version="ForkA-vFINAL.2",
                       base="ForkA-vFINAL.2")
        eligible, reasons = _check(block, conn, flag)
        self.assertFalse(eligible)
        self.assertTrue(any("Base ForkA-vFINAL.2 does not match" in m
                            for m in _messages(reasons)))
        conn.close()

    def test_new_pending_decision_is_not_eligible(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        flag = os.path.join(tempfile.mkdtemp(), "session.json")
        block = _block(decisions="\"What kind of elite force should "
                                 "the engineers develop?\"")
        eligible, reasons = _check(block, conn, flag)
        self.assertFalse(eligible)
        self.assertTrue(any("creates a new pending decision" in m
                            for m in _messages(reasons)))
        conn.close()

    def test_resolved_pending_decision_is_not_eligible(self):
        # The Turn 134 class: 0 mechanical changes, no findings —
        # but the block answers a decision the DB still holds open.
        # The sweep's diff does not track the pending decision, so
        # this check is the only thing holding it for Bryan.
        tmp = tempfile.mkdtemp()
        conn, _ = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
        flag = os.path.join(tmp, "session.json")
        first = _block(decisions="\"What kind of elite force should "
                                 "the engineers develop?\"")
        parsed = sweep_mod.parse_state_block(first)
        sweep_mod.apply_sweep(parsed, conn, approved_by="Bryan",
                              flag_path=flag)
        conn.commit()
        eligible, reasons = _check(
            _block(turn=133, version="ForkA-vFINAL.2"), conn, flag)
        self.assertFalse(eligible)
        self.assertTrue(any("resolves the pending decision" in m
                            for m in _messages(reasons)))
        conn.close()

    def test_unchanged_pending_decision_does_not_block(self):
        # Fork B Turn 1 (2026-11-21): the opening decision is the
        # canon decision, not a change — but the PENDING_DECISION
        # finding ("carried verbatim") is always present while a
        # decision stands. It must not create a FINDINGS reason by
        # itself, or no turn carrying a pending decision could ever
        # auto-apply or reach Lore.
        tmp = tempfile.mkdtemp()
        conn, _ = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
        flag = os.path.join(tmp, "session.json")
        decision = ("\"What kind of elite force should the engineers "
                    "develop?\"")
        first = _block(decisions=decision)
        parsed = sweep_mod.parse_state_block(first)
        sweep_mod.apply_sweep(parsed, conn, approved_by="Bryan",
                              flag_path=flag)
        conn.commit()
        eligible, reasons = _check(
            _block(turn=133, version="ForkA-vFINAL.2",
                   decisions=decision),
            conn, flag)
        self.assertTrue(eligible)
        self.assertEqual(reasons, [])
        conn.close()

    def test_open_session_flag_is_not_eligible(self):
        tmp = tempfile.mkdtemp()
        conn, _ = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
        flag = os.path.join(tmp, "session.json")
        session_mod.save_flag(
            {"session_open": True, "world_id": "ironwild-fork-a",
             "opened_at": "2026-11-21T09:30:00Z", "opened_by": "test",
             "turn": 132},
            flag)
        eligible, reasons = _check(_block(), conn, flag)
        self.assertFalse(eligible)
        self.assertTrue(any("session flag is open" in m
                            for m in _messages(reasons)))
        conn.close()


class TestFlagNarrativeChanges(unittest.TestCase):
    """The canon guard's field comparison against the last approved
    block's carried record."""

    def _applied_carried(self):
        tmp = tempfile.mkdtemp()
        conn, _ = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
        parsed = sweep_mod.parse_state_block(_block())
        result = sweep_mod.apply_sweep(
            parsed, conn, approved_by="Bryan",
            flag_path=os.path.join(tmp, "session.json"))
        conn.commit()
        return tmp, conn, result["carried"]

    def test_pure_carryover_has_no_flags(self):
        tmp, conn, carried = self._applied_carried()
        block = _block(turn=133, version="ForkA-vFINAL.2")
        parsed = sweep_mod.parse_state_block(block)
        flags = auto_apply_mod.flag_narrative_changes(
            parsed, carried, conn)
        self.assertEqual(flags, [])
        conn.close()

    def test_scene_change_flagged(self):
        tmp, conn, carried = self._applied_carried()
        block = _block(
            turn=133, version="ForkA-vFINAL.2",
            scene="Great Basin — Legion Reconstruction Council | "
                  "SCENE_TENSION: Low | ACTIVE_TRADE_OFF: none")
        parsed = sweep_mod.parse_state_block(block)
        flags = auto_apply_mod.flag_narrative_changes(
            parsed, carried, conn)
        self.assertEqual([f["code"] for f in flags], ["SCENE_CHANGE"])
        conn.close()

    def test_tradeoff_change_flagged(self):
        tmp, conn, carried = self._applied_carried()
        block = _block(
            turn=133, version="ForkA-vFINAL.2",
            scene="Great Basin | SCENE_TENSION: Low | "
                  "ACTIVE_TRADE_OFF: New trade-off text")
        parsed = sweep_mod.parse_state_block(block)
        flags = auto_apply_mod.flag_narrative_changes(
            parsed, carried, conn)
        self.assertEqual([f["code"] for f in flags], ["SCENE_CHANGE"])
        conn.close()

    def test_new_pc_fact_flagged(self):
        tmp, conn, carried = self._applied_carried()
        block = _block(turn=133, version="ForkA-vFINAL.2",
                       pc=_PC + " Brigus also orders the forges doubled.")
        parsed = sweep_mod.parse_state_block(block)
        flags = auto_apply_mod.flag_narrative_changes(
            parsed, carried, conn)
        self.assertEqual([f["code"] for f in flags], ["NEW_PC_FACT"])
        conn.close()

    def test_bond_only_pc_change_not_flagged(self):
        # A Bond number moves through ticks (Dream Share); the
        # normalization masks it, so it is not a new PC fact.
        tmp, conn, carried = self._applied_carried()
        pc = _PC.replace("Razor-Back, Bond 3/5",
                         "Razor-Back, Bond 4/5")
        block = _block(turn=133, version="ForkA-vFINAL.2", pc=pc)
        parsed = sweep_mod.parse_state_block(block)
        flags = auto_apply_mod.flag_narrative_changes(
            parsed, carried, conn)
        self.assertEqual(flags, [])
        conn.close()

    def test_status_mismatch_flagged(self):
        tmp, conn, carried = self._applied_carried()
        pc = _PC.replace("Razor-Back, Bond 3/5",
                         "Razor-Back, Bond 3/5, field-patched")
        block = _block(turn=133, version="ForkA-vFINAL.2", pc=pc)
        parsed = sweep_mod.parse_state_block(block)
        flags = auto_apply_mod.flag_narrative_changes(
            parsed, carried, conn)
        codes = [f["code"] for f in flags]
        self.assertIn("STATUS_MISMATCH", codes)
        conn.close()

    def test_decision_resolved_flagged(self):
        tmp = tempfile.mkdtemp()
        conn, _ = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
        first = _block(decisions="\"What kind of elite force should "
                                 "the engineers develop?\"")
        parsed = sweep_mod.parse_state_block(first)
        result = sweep_mod.apply_sweep(
            parsed, conn, approved_by="Bryan",
            flag_path=os.path.join(tmp, "session.json"))
        conn.commit()
        block = _block(turn=133, version="ForkA-vFINAL.2")
        parsed = sweep_mod.parse_state_block(block)
        flags = auto_apply_mod.flag_narrative_changes(
            parsed, result["carried"], conn)
        self.assertEqual([f["code"] for f in flags],
                         ["PENDING_DECISION"])
        conn.close()

    def test_no_baseline_flagged(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        parsed = sweep_mod.parse_state_block(_block())
        flags = auto_apply_mod.flag_narrative_changes(parsed, None, conn)
        self.assertEqual([f["code"] for f in flags], ["NO_BASELINE"])
        conn.close()


class TestAttemptAutoApplyRefusal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn, _ = fresh_fork_db(os.path.join(self.tmp,
                                                  "fork.sqlite"))
        self._orig_dir = proposals_mod.PROPOSALS_DIR
        self._orig_reg = proposals_mod.REGISTRY_PATH
        proposals_mod.PROPOSALS_DIR = os.path.join(self.tmp, "proposals")
        proposals_mod.REGISTRY_PATH = os.path.join(
            self.tmp, "proposals", "registry.json")
        self.flag = os.path.join(self.tmp, "session.json")

    def tearDown(self):
        proposals_mod.PROPOSALS_DIR = self._orig_dir
        proposals_mod.REGISTRY_PATH = self._orig_reg
        self.conn.close()

    def test_clock_change_proposal_is_held_without_touching_db(self):
        block = _block(clocks="Dust-Baron Retaliation 1/6; "
                              "Concord Blockade 0/6; Legion Cohesion 0/6; "
                              "Great Basin Recovery 0/6")
        entry = proposals_mod.intake_file("drive-test-1", "turn-132.txt",
                                          block, self.conn)
        self.assertEqual(entry["status"], "reviewed")
        events_before = self.conn.execute(
            "SELECT COUNT(*) FROM events").fetchone()[0]
        with self.assertRaises(sweep_mod.SweepError) as cm:
            run_mod.attempt_auto_apply(entry["proposal_id"], self.conn,
                                       flag_path=self.flag)
        self.assertIn("not eligible for auto-apply", str(cm.exception))
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM events").fetchone()[0], events_before)
        registry = proposals_mod.load_registry()
        self.assertEqual(registry[entry["proposal_id"]]["status"],
                         "reviewed")

    def test_record_lore_approval(self):
        entry = proposals_mod.intake_file("drive-test-2", "turn-132.txt",
                                          _block(), self.conn)
        record = proposals_mod.record_lore_approval(
            entry["proposal_id"], "submission-test-123")
        self.assertEqual(record["lore_verdict"], "APPROVE")
        self.assertEqual(record["lore_submission"], "submission-test-123")
        path = os.path.join(
            proposals_mod._proposal_dir(entry["proposal_id"]),
            "lore-approved.json")
        self.assertTrue(os.path.exists(path))
        registry = proposals_mod.load_registry()
        saved = registry[entry["proposal_id"]]
        self.assertTrue(saved["lore_approved"])
        self.assertEqual(saved["lore_approval_submission"],
                         "submission-test-123")


class TestAttemptAutoApplyRouting(unittest.TestCase):
    """A 0-change proposal with a narrative flag goes to Lore, not
    to an auto-apply and not (yet) to Bryan — and the DB is untouched."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn, _ = fresh_fork_db(os.path.join(self.tmp,
                                                  "fork.sqlite"))
        self._orig_dir = proposals_mod.PROPOSALS_DIR
        self._orig_reg = proposals_mod.REGISTRY_PATH
        proposals_mod.PROPOSALS_DIR = os.path.join(self.tmp, "proposals")
        proposals_mod.REGISTRY_PATH = os.path.join(
            self.tmp, "proposals", "registry.json")
        self._orig_runs = os.environ.get("IRONWILD_RUNS_DIR")
        os.environ["IRONWILD_RUNS_DIR"] = os.path.join(self.tmp, "runs")
        self.flag = os.path.join(self.tmp, "session.json")
        # Apply Turn 132 and write its carried record where the
        # auto-apply path looks for the last approved block.
        parsed = sweep_mod.parse_state_block(_block())
        result = sweep_mod.apply_sweep(parsed, self.conn,
                                       approved_by="Bryan",
                                       flag_path=self.flag)
        self.conn.commit()
        out_dir = os.path.join(self.tmp, "runs", "sweeps", "turn-132")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "carried.json"), "w") as f:
            json.dump(result["carried"], f, indent=2, sort_keys=True)

    def tearDown(self):
        proposals_mod.PROPOSALS_DIR = self._orig_dir
        proposals_mod.REGISTRY_PATH = self._orig_reg
        if self._orig_runs is None:
            os.environ.pop("IRONWILD_RUNS_DIR", None)
        else:
            os.environ["IRONWILD_RUNS_DIR"] = self._orig_runs
        self.conn.close()

    def test_scene_change_proposal_goes_to_lore(self):
        block = _block(
            turn=133, version="ForkA-vFINAL.2",
            scene="Great Basin — Legion Reconstruction Council | "
                  "SCENE_TENSION: Low | ACTIVE_TRADE_OFF: none")
        entry = proposals_mod.intake_file("drive-test-3", "turn-133.txt",
                                          block, self.conn)
        self.assertEqual(entry["status"], "reviewed")
        events_before = self.conn.execute(
            "SELECT COUNT(*) FROM events").fetchone()[0]
        with self.assertRaises(auto_apply_mod.LoreCall) as cm:
            run_mod.attempt_auto_apply(entry["proposal_id"], self.conn,
                                       flag_path=self.flag)
        self.assertEqual([f["code"] for f in cm.exception.flags],
                         ["SCENE_CHANGE"])
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM events").fetchone()[0], events_before)
        registry = proposals_mod.load_registry()
        self.assertEqual(registry[entry["proposal_id"]]["status"],
                         "reviewed")
