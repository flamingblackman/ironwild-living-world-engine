"""Handshake tests — the 10-section generator (Phase 2 harness).

Carried state is built from Lore's Sample A (Turn 131) plus the
resolved list and watchlist from Lore's Phase 2 inputs
(lore-phase-2-inputs.md, section 2).
"""

import json
import os
import tempfile
import unittest

from helpers import fresh_fork_db
from src import db, events, handshake as handshake_mod

CARRIED = {
    "turn": 131,
    "state_version": "vFINAL (v3.00.2)",
    "scene": "Salt Flats (final battle) / Great Basin (post-victory)",
    "scene_tension": "Low",
    "active_trade_off": "none",
    "pending_decision": None,
    "pc_raw": ("Brigus, Seedborn / King of the Great Basin. Wounds: None. "
               "Status: exhausted after the Feral God merge, victorious. "
               "King is a Beacon."),
    "pc_short": ("Brigus, Seedborn / King of the Great Basin. Wounds: "
                 "None. Status: exhausted after the Feral God merge, "
                 "victorious."),
    "pack": ["Vance", "Tull", "Queen Kaelen", "Nest-Keeper"],
    "wounds": "None",
    "resolved_do_not_resurrect": [
        "Rift-King (corrupted Den Boss) annihilated in the Salt Flats.",
        "Den Boss dead.",
        "Deepmaw Migration diverted by the Acoustic Lure.",
    ],
    "dormant_watchlist": [
        "IW-42 Learning Black Box only.",
        "IW-46 and IW-84 activated and resolved in the final arc; "
        "do not re-trigger them as dormant.",
    ],
}


class TestHandshake(unittest.TestCase):
    def test_all_ten_sections_present(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        result = handshake_mod.generate_handshake(conn, CARRIED)
        text = result["text"]
        for section in (
                "Base state:", "PC:", "Scene:", "Engines:", "Pack:",
                "Vance location:", "Clocks:",
                "Resolved, do not resurrect:", "Dormant Watchlist:",
                "Pending decision, verbatim:"):
            self.assertIn(section, text)
        self.assertIn("First reply: echo", text)
        self.assertIn("Pending decision, verbatim: none", text)
        self.assertIn("Rumors live:\n  None.", text)
        self.assertIn("Clocks about to fire:\n  None.", text)
        self.assertIn("Gold Sledge", text)
        self.assertIn("Bond 3/5", text)
        self.assertNotIn("Krov", text)
        conn.close()

    def test_rumors_come_from_events_only(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        # Events land at tick 1 (after the tick-0 session close), so
        # the handshake's since_tick=0 window includes them.
        tick = 1
        events.append_event(
            conn, tick, "breaker_poacher_chief", "claim_breakers", None,
            None, [{"op": "location_set", "location": "rust_dunes",
                    "controller": "breakers"}])
        events.append_event(
            conn, tick, "dust_baron_captain", "raid_captain", None, None,
            [{"op": "flag_set", "flag": "raid_great_basin",
              "value": "great_basin"}])
        events.append_event(
            conn, tick, "caravan_master", "trade_concord", None, None,
            [{"op": "resource_move", "from": "ironwild_legion",
              "from_kind": "faction", "to": "caravan_concord",
              "to_kind": "faction", "resource": "Feed", "qty": 2}])
        events.append_event(conn, tick, "brigus", "rest", None, None,
                            [{"op": "rest"}])
        conn.commit()
        result = handshake_mod.generate_handshake(conn, CARRIED)
        text = result["text"]
        self.assertEqual(result["meta"]["rumors"], 3)
        rumor_lines = [line for line in text.splitlines()
                       if line.strip().startswith("Rumor (unverified):")]
        self.assertEqual(len(rumor_lines), 3)
        self.assertTrue(any("Rust Dunes" in line for line in rumor_lines))
        self.assertTrue(any("Great Basin" in line for line in rumor_lines))
        self.assertTrue(any("trade is moving" in line
                            for line in rumor_lines))
        # No rumor for the rest event, and no certain language in rumors.
        for line in rumor_lines:
            self.assertNotIn(" will ", line)
        conn.close()

    def test_clock_about_to_fire(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        conn.execute("UPDATE clocks SET value = 5 "
                     "WHERE id = 'dust_baron_retaliation'")
        conn.commit()
        result = handshake_mod.generate_handshake(conn, CARRIED)
        self.assertIn("Dust-Baron Retaliation is at 5/6.",
                      result["text"])
        self.assertEqual(result["meta"]["clocks_about_to_fire"],
                         ["dust_baron_retaliation"])
        conn.close()

    def test_word_budget(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        tick = db.get_tick(conn)
        for i in range(30):
            events.append_event(
                conn, tick, "legion_captain", "forage", None, None,
                [{"op": "resource_add", "holder": "ironwild_legion",
                  "holder_kind": "faction", "resource": "Feed", "qty": 2}])
        conn.commit()
        result = handshake_mod.generate_handshake(conn, CARRIED)
        self.assertLessEqual(result["meta"]["words"], 600)
        conn.close()

    def test_vance_location_comes_from_db(self):
        # Actor locations come from the DB (Lore, 2026-11-21), never
        # from carried state when the DB knows. Vance is at Great
        # Basin in the fork seed; a carried location saying otherwise
        # must not win.
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        carried = dict(CARRIED, vance_location="Rust Dunes")
        result = handshake_mod.generate_handshake(conn, carried)
        self.assertIn("Vance location: Great Basin.", result["text"])
        self.assertNotIn("Vance location: Rust Dunes.", result["text"])
        conn.close()

    def test_vance_location_falls_back_to_carried(self):
        # When the DB has no location for the actor, the carried state
        # is the fallback — never an invented value.
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        conn.execute("UPDATE npcs SET location_id = NULL "
                     "WHERE id = 'vance'")
        conn.commit()
        carried = dict(CARRIED, vance_location="Rust Dunes")
        result = handshake_mod.generate_handshake(conn, carried)
        self.assertIn("Vance location: Rust Dunes.", result["text"])
        conn.close()

    def test_resolved_and_watchlist_default_when_carried_lacks_them(self):
        # The V2 block has no resolved-list or watchlist fields, so a
        # real sweep's carried state lacks them — the handshake must
        # still carry Lore's stated lists, never "not recorded".
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        carried = {k: v for k, v in CARRIED.items()
                   if k not in ("resolved_do_not_resurrect",
                                "dormant_watchlist")}
        result = handshake_mod.generate_handshake(conn, carried)
        self.assertIn(
            "Rift-King (corrupted Den Boss) annihilated in the "
            "Salt Flats.", result["text"])
        self.assertIn("IW-42 Learning Black Box only.", result["text"])
        self.assertNotIn("not recorded", result["text"].split(
            "Resolved, do not resurrect:")[1].split(
            "What moved")[0])
        conn.close()

    def test_pc_line_is_carried_in_full(self):
        # The PC line is never truncated: a 200-char cap cut the real
        # Turn 132 line mid-list ("...battered: Gold"). The handshake
        # must carry all five Engines with Bonds and details.
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        long_pc = ("Brigus, Seedborn, King of the Great Basin, Beacon. "
                   "Wounds: None. Status: exhausted after the Feral God "
                   "merge, victorious, directing reconstruction. Five "
                   "Engines, all exhausted and battered: Gold Sledge, "
                   "black-and-gold gorilla Bulwark, Bond 3/5, "
                   "Titanium-Cestus (Diamond-Claw melted Turn 126), "
                   "neural Sentient Seat (not a saddle-harness); "
                   "Skytalon, ADULT Shadow-Owl, Bond 5/5.")
        carried = dict(CARRIED, pc_short=None, pc_raw=long_pc)
        result = handshake_mod.generate_handshake(conn, carried)
        pc_line = [l for l in result["text"].splitlines()
                   if l.startswith("PC: ")][0]
        self.assertEqual(pc_line, "PC: " + long_pc)
        conn.close()

    def test_pc_bonds_come_from_db(self):
        # Turn 134 shipped Sledge 3/5 in the PC line and 4/5 in the
        # Engines section: Dream Share restored +1 at tick 5 after
        # the sweep. The PC line's Bonds now come from the DB, so
        # the handshake never carries two values for one Bond.
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        conn.execute("UPDATE bonds SET bond = 4 "
                     "WHERE engine_id = 'sledge'")
        conn.commit()
        pc = ("Brigus, Seedborn. Five Engines: Gold Sledge, Bond 3/5; "
              "Skytalon, Bond 5/5; Razor-Back, Bond 3/5; "
              "Goliath Dreadnought, Bond 5/5; Surveyor-Strider, "
              "Bond 5/5. All Engine Bonds unchanged.")
        carried = dict(CARRIED, pc_short=None, pc_raw=pc)
        result = handshake_mod.generate_handshake(conn, carried)
        pc_line = [l for l in result["text"].splitlines()
                   if l.startswith("PC: ")][0]
        self.assertIn("Gold Sledge, Bond 4/5", pc_line)
        self.assertNotIn("Bond 3/5", pc_line.split("Gold Sledge")[1]
                         .split(";")[0])
        self.assertIn("Gold Sledge (Bulwark), Bond 4/5",
                      result["text"])
        # The carried "unchanged" claim is false now, so it goes.
        self.assertNotIn("All Engine Bonds unchanged",
                         result["text"])
        conn.close()

    def test_pc_unchanged_claim_stays_when_bonds_match(self):
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        pc = ("Brigus, Seedborn. Five Engines: Gold Sledge, Bond 3/5; "
              "Skytalon, Bond 5/5; Razor-Back, Bond 3/5; "
              "Goliath Dreadnought, Bond 5/5; Surveyor-Strider, "
              "Bond 5/5. All Engine Bonds unchanged.")
        carried = dict(CARRIED, pc_short=None, pc_raw=pc)
        result = handshake_mod.generate_handshake(conn, carried)
        pc_line = [l for l in result["text"].splitlines()
                   if l.startswith("PC: ")][0]
        self.assertIn("Gold Sledge, Bond 3/5", pc_line)
        self.assertIn("All Engine Bonds unchanged", pc_line)
        conn.close()

    def test_skipped_ops_render_as_nothing(self):
        # A skipped op never happened: its note text must not appear
        # in the off-screen lines (the first Turn 133 handshake
        # claimed a raid was "blocked" although the raid had landed).
        from src import render as render_mod
        self.assertIsNone(render_mod._effect_text(
            {"op": "note", "skipped": True,
             "text": "raid blocked: Great Basin fortified"}))
        self.assertEqual(
            render_mod._effect_text(
                {"op": "move", "id": "high_baron",
                 "old_location": "great_basin",
                 "location": "rust_dunes"}),
            "high_baron: great_basin -> rust_dunes")

    def test_sweep_events_are_not_off_screen_movement(self):
        # Ledger bookkeeping (a sweep apply, a correction) is not
        # world movement: it never appears in "What moved off-screen".
        conn, _ = fresh_fork_db(os.path.join(tempfile.mkdtemp(),
                                             "fork.sqlite"))
        events.append_event(
            conn, 1, "sweep", "sweep_clock", None, None,
            [{"op": "sweep_clock", "clock": "great_basin_recovery",
              "old": 0, "new": 1, "source_turn": 132}])
        conn.commit()
        result = handshake_mod.generate_handshake(conn, CARRIED,
                                                  since_tick=0)
        self.assertNotIn("sweep_clock", result["text"])
        self.assertNotIn("sweep: clock", result["text"])
        conn.close()


if __name__ == "__main__":
    unittest.main()
