"""Stage 1A proposal pipeline tests.

The pipeline's guarantees, each tested against a scratch fork DB
(never the live test DB):
- a Fork A proposal (Universe Ironwild, State-Version ForkA-vFINAL.k)
  intakes as reviewed; a live-versioned block is rejected;
- intake is idempotent and never writes the DB;
- apply binds to the exact reviewed revision: a tampered Drive file
  (hash mismatch) or a non-Bryan approver refuses, and a second
  apply of the same proposal refuses;
- the applied record carries the approval binding.
"""

import json
import os
import tempfile
import unittest
from unittest import mock

from src import db
from src import proposals as proposals_mod
from src import sweep as sweep_mod
from tests.helpers import fresh_fork_db, fresh_fork_g_db

_PC = ("Brigus, Seedborn / King of the Great Basin. Wounds: None. "
       "Engines: Gold Sledge, Bulwark, Bond 3/5; Skytalon, Bond 5/5; "
       "Razor-Back, Bond 3/5; Goliath Dreadnought, Bond 5/5; "
       "Surveyor-Strider, Bond 5/5. Pack: Vance, Tull, Kaelen, "
       "Nest-Keeper.")


def _fork_block(turn=133, version="ForkA-vFINAL.2",
                clocks="Dust-Baron Retaliation 1/6"):
    return ("[TURN STATE]\n"
            "Universe: Ironwild | State-Version: %s | Turn: %d\n"
            "Clocks: %s\n"
            "Scene: Great Basin | SCENE_TENSION: Low | "
            "ACTIVE_TRADE_OFF: none\n"
            "Player character: %s\n"
            "Unresolved Decisions: none\n"
            "[/TURN STATE]\n"
            % (version, turn, clocks, _PC))


class TestProposalPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn, _ = fresh_fork_db(os.path.join(self.tmp, "fork.sqlite"))
        # Point the registry at a scratch dir, never the live one.
        self._orig_dir = proposals_mod.PROPOSALS_DIR
        self._orig_reg = proposals_mod.REGISTRY_PATH
        proposals_mod.PROPOSALS_DIR = os.path.join(self.tmp, "proposals")
        proposals_mod.REGISTRY_PATH = os.path.join(
            self.tmp, "proposals", "registry.json")

    def tearDown(self):
        proposals_mod.PROPOSALS_DIR = self._orig_dir
        proposals_mod.REGISTRY_PATH = self._orig_reg
        self.conn.close()

    def test_proposal_id_stable_and_content_bound(self):
        text = _fork_block()
        self.assertEqual(proposals_mod.proposal_id(133, text),
                         proposals_mod.proposal_id(133, text))
        self.assertNotEqual(proposals_mod.proposal_id(133, text),
                            proposals_mod.proposal_id(
                                133, text.replace("1/6", "2/6")))

    def test_fork_a_identifier_accepts_fork_versions(self):
        for version in ("ForkA-vFINAL", "ForkA-vFINAL.1", "ForkA-vFINAL.2"):
            p = sweep_mod.parse_state_block(_fork_block(version=version))
            self.assertEqual(proposals_mod.validate_fork_a(p), [],
                             version)

    def test_fork_a_identifier_rejects_live_versions(self):
        bad = [
            _fork_block(version="vFINAL.5"),
            _fork_block(version="vFINAL (v3.00.2)"),
            _fork_block(version="vFINAL.7"),
            _fork_block().replace("Universe: Ironwild",
                                  "Universe: Ashen Accord"),
            _fork_block(version=""),
        ]
        for text in bad:
            p = sweep_mod.parse_state_block(text)
            findings = proposals_mod.validate_fork_a(p)
            self.assertTrue(
                any(f["code"] == "NOT_FORK_A" and f["level"] == "error"
                    for f in findings), text[:60])

    def test_intake_reviews_and_never_writes_db(self):
        entry = proposals_mod.intake_file(
            "drive-file-1", "turn-133-proposal.txt", _fork_block(),
            self.conn)
        self.assertEqual(entry["status"], "reviewed")
        self.assertEqual(entry["turn"], 133)
        self.assertTrue(entry["proposal_id"].startswith("prop-133-"))
        self.assertEqual(
            entry["changes"],
            [{"kind": "clock", "id": "dust_baron_retaliation",
              "name": "Dust-Baron Retaliation", "old": 0, "new": 1,
              "max": 6}])
        # The DB is untouched: still tick 0, no events.
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM events").fetchone()[0], 0)
        # The review record is on disk.
        self.assertTrue(os.path.exists(os.path.join(
            proposals_mod.PROPOSALS_DIR, entry["proposal_id"],
            "review.json")))

    def test_intake_rejects_live_turn_136(self):
        with open(os.path.join(os.path.dirname(__file__), "..",
                               "runs", "harness-demo",
                               "sample-b.txt"), encoding="utf-8") as f:
            text = f.read()
        entry = proposals_mod.intake_file(
            "drive-file-2", "turn-136.txt", text, self.conn)
        self.assertEqual(entry["status"], "rejected")
        codes = {f["code"] for f in entry["findings"]}
        self.assertIn("FROZEN_LIVE", codes)
        self.assertIn("NOT_FORK_A", codes)

    def test_intake_is_idempotent(self):
        first = proposals_mod.intake_file(
            "drive-file-1", "turn-133-proposal.txt", _fork_block(),
            self.conn)
        second = proposals_mod.intake_file(
            "drive-file-1", "turn-133-proposal.txt", _fork_block(),
            self.conn)
        self.assertEqual(first["proposal_id"], second["proposal_id"])
        self.assertEqual(len(proposals_mod.load_registry()), 1)

    def _reviewed(self):
        # The shared gate requires the turn to be exactly
        # last_swept + 1: Turn 133 applies only once 132 is swept.
        db.set_meta(self.conn, "last_swept_turn", 132)
        db.set_meta(self.conn, "last_swept_version", "ForkA-vFINAL.1")
        self.conn.commit()
        entry = proposals_mod.intake_file(
            "drive-file-1", "turn-133-proposal.txt", _fork_block(),
            self.conn)
        self.assertEqual(entry["status"], "reviewed")
        return entry

    def test_apply_binds_and_lands_once(self):
        entry = self._reviewed()
        with mock.patch(
                "src.drive_io.download_text",
                return_value=_fork_block()):
            result = proposals_mod.apply_proposal(
                entry["proposal_id"], self.conn, "Bryan")
        self.assertEqual(result["proposal_binding"]["proposal_id"],
                         entry["proposal_id"])
        self.assertEqual(result["proposal_binding"]["content_hash"],
                         entry["content_hash"])
        self.assertEqual(result["proposal_binding"]["approved_by"],
                         "Bryan")
        self.assertEqual(
            self.conn.execute(
                "SELECT value FROM clocks "
                "WHERE id='dust_baron_retaliation'").fetchone()[0], 1)
        self.assertEqual(self.conn.execute(
            "SELECT value FROM meta WHERE key='last_swept_turn'"
            ).fetchone()[0], "133")
        # A second apply of the same proposal refuses.
        with mock.patch(
                "src.drive_io.download_text",
                return_value=_fork_block()):
            with self.assertRaises(sweep_mod.SweepError):
                proposals_mod.apply_proposal(
                    entry["proposal_id"], self.conn, "Bryan")

    def test_apply_with_lore_approval_labels_the_apply_as_lore(self):
        entry = self._reviewed()
        with mock.patch(
                "src.drive_io.download_text",
                return_value=_fork_block()):
            result = proposals_mod.apply_proposal(
                entry["proposal_id"], self.conn, "Bryan",
                lore_approval="lore-sub-1")
        self.assertEqual(result["proposal_binding"]["approved_by"],
                         "Lore")
        self.assertEqual(result["proposal_binding"]["lore_approval"],
                         "lore-sub-1")
        self.assertEqual(result["approved_by"], "Lore")
        note = self.conn.execute(
            "SELECT effect FROM events WHERE action = 'sweep' "
            "ORDER BY id DESC LIMIT 1").fetchone()[0]
        self.assertIn("Lore-approved (submission lore-sub-1)", note)

    def test_apply_with_lore_approval_still_needs_bryan(self):
        # The lore-approval path does not bypass the Bryan guard:
        # the command authorization is still Bryan's standing
        # approval; only the recorded verdict source is Lore's.
        entry = self._reviewed()
        with mock.patch(
                "src.drive_io.download_text",
                return_value=_fork_block()):
            with self.assertRaises(sweep_mod.SweepError):
                proposals_mod.apply_proposal(
                    entry["proposal_id"], self.conn, "Case",
                    lore_approval="lore-sub-1")

    def test_apply_refuses_tampered_file(self):
        entry = self._reviewed()
        tampered = _fork_block().replace("1/6", "2/6")
        with mock.patch(
                "src.drive_io.download_text", return_value=tampered):
            with self.assertRaises(sweep_mod.SweepError):
                proposals_mod.apply_proposal(
                    entry["proposal_id"], self.conn, "Bryan")
        # Nothing advanced: the clock is still 0, no events.
        self.assertEqual(
            self.conn.execute(
                "SELECT value FROM clocks "
                "WHERE id='dust_baron_retaliation'").fetchone()[0], 0)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM events").fetchone()[0], 0)
        self.assertEqual(
            proposals_mod.load_registry()[entry["proposal_id"]]["status"],
            "held")

    def test_apply_refuses_non_bryan_approver(self):
        entry = self._reviewed()
        with mock.patch(
                "src.drive_io.download_text",
                return_value=_fork_block()):
            with self.assertRaises(sweep_mod.SweepError):
                proposals_mod.apply_proposal(
                    entry["proposal_id"], self.conn, "Case")

    def test_held_proposal_revives_when_file_restored(self):
        # Tamper -> held; restore the reviewed content -> intake
        # revives it to reviewed, because the hash IS the binding.
        entry = self._reviewed()
        with mock.patch(
                "src.drive_io.download_text",
                return_value=_fork_block().replace("1/6", "2/6")):
            with self.assertRaises(sweep_mod.SweepError):
                proposals_mod.apply_proposal(
                    entry["proposal_id"], self.conn, "Bryan")
        self.assertEqual(
            proposals_mod.load_registry()[entry["proposal_id"]]["status"],
            "held")
        file_entry = {"id": "drive-file-1", "name": "turn-133.txt",
                      "mimeType": "text/plain"}
        with mock.patch(
                "src.proposals.drive_io.list_folder",
                return_value=[file_entry]), mock.patch(
                "src.proposals.drive_io.download_text",
                return_value=_fork_block()):
            new_entries, skipped = proposals_mod.intake_folder(
                "inbox-folder", self.conn)
        self.assertEqual(skipped, 0)
        self.assertEqual(len(new_entries), 1)
        revived = new_entries[0]
        self.assertEqual(revived["proposal_id"], entry["proposal_id"])
        self.assertEqual(revived["status"], "reviewed")
        self.assertTrue(revived.get("restored_after_hold"))
        # And now it applies.
        with mock.patch(
                "src.drive_io.download_text",
                return_value=_fork_block()):
            proposals_mod.apply_proposal(
                entry["proposal_id"], self.conn, "Bryan")
        self.assertEqual(
            self.conn.execute(
                "SELECT value FROM clocks "
                "WHERE id='dust_baron_retaliation'").fetchone()[0], 1)


class TestForkG(unittest.TestCase):
    """Fork G (Gemini DM test): same seed content as Fork A, separate
    ledger. The intake's fork check follows the DB's world_id, so the
    two forks never accept each other's blocks."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn_g, _ = fresh_fork_g_db(
            os.path.join(self.tmp, "fork-g.sqlite"))
        self.conn_a, _ = fresh_fork_db(
            os.path.join(self.tmp, "fork-a.sqlite"))
        self._orig_dir = proposals_mod.PROPOSALS_DIR
        self._orig_reg = proposals_mod.REGISTRY_PATH
        proposals_mod.PROPOSALS_DIR = os.path.join(self.tmp, "proposals")
        proposals_mod.REGISTRY_PATH = os.path.join(
            self.tmp, "proposals", "registry.json")

    def tearDown(self):
        proposals_mod.PROPOSALS_DIR = self._orig_dir
        proposals_mod.REGISTRY_PATH = self._orig_reg
        self.conn_g.close()
        self.conn_a.close()

    def test_fork_g_versions_accepted_on_fork_g(self):
        for version in ("ForkG-vFINAL", "ForkG-vFINAL.1", "ForkG-vFINAL.2"):
            p = sweep_mod.parse_state_block(
                _fork_block(version=version))
            self.assertEqual(
                proposals_mod.validate_fork(p, "ironwild-fork-g"), [],
                version)

    def test_fork_a_versions_rejected_on_fork_g(self):
        for version in ("ForkA-vFINAL", "ForkA-vFINAL.1", "vFINAL.5"):
            p = sweep_mod.parse_state_block(
                _fork_block(version=version))
            findings = proposals_mod.validate_fork(
                p, "ironwild-fork-g")
            self.assertTrue(
                any(f["code"] == "NOT_FORK_A" and f["level"] == "error"
                    for f in findings), version)

    def test_intake_accepts_fork_g_block_on_fork_g_db(self):
        entry = proposals_mod.intake_file(
            "drive-file-g", "turn-132-proposal.txt",
            _fork_block(turn=132, version="ForkG-vFINAL.1"),
            self.conn_g)
        self.assertEqual(entry["status"], "reviewed")
        self.assertEqual(entry["turn"], 132)

    def test_intake_rejects_fork_a_block_on_fork_g_db(self):
        entry = proposals_mod.intake_file(
            "drive-file-a", "turn-132-proposal.txt",
            _fork_block(turn=132, version="ForkA-vFINAL.1"),
            self.conn_g)
        self.assertEqual(entry["status"], "rejected")
        self.assertTrue(
            any(f["code"] == "NOT_FORK_A"
                for f in entry.get("findings", [])))

    def test_intake_rejects_fork_g_block_on_fork_a_db(self):
        entry = proposals_mod.intake_file(
            "drive-file-g", "turn-132-proposal.txt",
            _fork_block(turn=132, version="ForkG-vFINAL.1"),
            self.conn_a)
        self.assertEqual(entry["status"], "rejected")
        self.assertTrue(
            any(f["code"] == "NOT_FORK_A"
                for f in entry.get("findings", [])))


if __name__ == "__main__":
    unittest.main()
