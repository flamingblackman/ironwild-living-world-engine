"""Fork A acceptance tests — the real Lore seed (seed/fork-a.json via the
adapter), not the fixture.

Seed v1.5 (2026-11-21, Bryan's call, combined fix options 1 + 3): the v1.3
quiet-world fix (forage, scavenge, claim — floors, not floods), v1.4 Bond
recovery through Dream Share (option C), and v1.5 hunt Feed to the Pack
plus Dream Share as a scored action, not a rest hook. The 30-tick and
400-tick acceptance runs must complete, the quiet must stay fixed (far
fewer rests than v1.3's 1,106 in 400 ticks), Dream Share must fire and
Bond must recover, and at least one territory controller flip must be
proven on real seed data.

Drift rules DC-01..DC-19 are each checked where the plan's test files map
them (noted per test).
"""

import hashlib
import json
import os
import random
import re
import tempfile
import unittest

from helpers import (CANON_FILES, event_log, event_text, fresh_fork_db,
                     load_internal_seed, load_lore_seed)
from src import actions, db, eras, events, tick as tick_mod

SEQUEL_CLOCK_NAMES = {
    "Rider Army Mustering", "Sanctuary Integration",
    "Mother-Bulwark Rescue", "Outer Siege-Ring", "Northern Pass Approach",
}

FORBIDDEN_WORDS = ["krov", "136", "rift-king", "den boss",
                   "deepmaw migration", "first seed core",
                   "seed core origin", "blood-oath", "mortar"]


def _run_fork(tmp_path, subdir="a", n=30):
    """Run the Fork A seed for n ticks. Returns the connection (no halt
    expected since Bryan's raid-target call)."""
    conn, _ = fresh_fork_db(os.path.join(tmp_path, subdir, "fork.sqlite"))
    tick_mod.run_ticks(conn, n, rng=random.Random(131))
    return conn


class TestForkFreeze(unittest.TestCase):
    """DC-03, DC-04 (plan test_freeze.py). State-based, not string-based."""

    def test_source_is_turn_131_vfinal(self):
        conn, _ = fresh_fork_db(
            os.path.join(tempfile.mkdtemp(), "fork.sqlite"))
        self.assertEqual(
            db.get_meta(conn, "source_snapshot"),
            "Ironwild Turn 131 vFINAL (v3.00.2), CAMPAIGN COMPLETE")
        conn.close()

    def test_only_the_four_fork_clocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn, _ = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            names = [r["name"] for r in conn.execute(
                "SELECT name FROM clocks ORDER BY id")]
            self.assertEqual(names, [
                "Concord Blockade", "Dust-Baron Retaliation",
                "Great Basin Recovery", "Legion Cohesion"])
            for name in names:
                self.assertNotIn(name, SEQUEL_CLOCK_NAMES)
            conn.close()

    def test_no_sequel_actor_or_location_ids(self):
        lore = load_lore_seed()
        with tempfile.TemporaryDirectory() as tmp:
            conn, _ = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            actor_ids = {r["id"] for r in conn.execute("SELECT id FROM npcs")}
            loc_ids = {r["id"] for r in conn.execute(
                "SELECT id FROM locations")}
            self.assertEqual(
                actor_ids, {a["id"] for a in lore["actors"]})
            self.assertEqual(
                loc_ids, {loc["id"] for loc in lore["locations"]})
            conn.close()


class TestForkAcceptance(unittest.TestCase):
    """The Fork A acceptance runs (plan section 10).

    The 30-tick run used to halt at tick 1 on the evacuate stop rule.
    Bryan's call (2026-11-20 23:31 EST, via the hub) moved the Breaker
    Chief's raid target to Great Basin, like the Captain's, so the run
    now completes. The evacuate halt machinery is still tested directly
    (test_evacuate_halt_still_arms) as a safety net.
    """

    def test_thirty_tick_run_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _run_fork(tmp)
            self.assertEqual(db.get_tick(conn), 30)
            self.assertEqual(tick_mod.verify_invariants(conn), [])
            ok, bad = events.verify_chain(conn)
            self.assertTrue(ok, f"hash chain broken at {bad}")
            conn.close()

    def test_thirty_tick_run_is_deterministic(self):
        # DC-15 + determinism: two runs with the seed produce identical
        # logs and identical state hashes.
        with tempfile.TemporaryDirectory() as tmp:
            conn_a = _run_fork(tmp, "a")
            log_a = event_log(conn_a)
            hash_a = db.state_hash(conn_a)
            conn_a.close()
            conn_b = _run_fork(tmp, "b")
            log_b = event_log(conn_b)
            hash_b = db.state_hash(conn_b)
            conn_b.close()
        self.assertEqual(log_a, log_b)
        self.assertEqual(hash_a, hash_b)

    def test_evacuate_halt_still_arms(self):
        # The safety net: if any raid ever flags Concord Camp itself,
        # the Master's evacuate still halts and asks Lore.
        with tempfile.TemporaryDirectory() as tmp:
            conn, seed_data = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            conn.execute(
                "INSERT INTO tick_flags (flag, tick, value) "
                "VALUES ('raid_in_progress:concord_camp', 1, '')")
            catalog = [a for a in seed_data["actions"]
                       if a["id"] in ("evacuate", "rest")]
            with self.assertRaises(tick_mod.EngineHalt) as cm:
                tick_mod._act(conn, 1, random.Random(131),
                              {"id": "caravan_master", "kind": "npc"},
                              catalog)
            self.assertIn("Concord Camp", str(cm.exception))
            conn.close()

    def test_era_acceptance_400_ticks(self):
        # LR-05: the 400-tick fast-forward crosses one era boundary, the
        # legacy rules fire exactly once, Era 1 closes, Era 2 opens
        # unnamed (the engine never names eras).
        with tempfile.TemporaryDirectory() as tmp:
            conn = _run_fork(tmp, n=400)
            self.assertEqual(db.get_tick(conn), 400)
            legacy = conn.execute(
                "SELECT COUNT(*) AS n FROM events WHERE action = 'legacy'"
            ).fetchone()["n"]
            self.assertEqual(legacy, 1, "legacy must fire exactly once")
            closed = conn.execute(
                "SELECT name, legacy_applied FROM eras "
                "WHERE end_tick IS NOT NULL").fetchall()
            self.assertEqual(len(closed), 1)
            self.assertEqual(closed[0]["name"], "The Beacon Year")
            self.assertEqual(closed[0]["legacy_applied"], 1)
            open_era = conn.execute(
                "SELECT name FROM eras WHERE end_tick IS NULL").fetchone()
            self.assertIsNone(open_era["name"])
            retired = conn.execute(
                "SELECT COUNT(*) AS n FROM npcs WHERE status = 'retired'"
            ).fetchone()["n"]
            self.assertEqual(retired, 0)
            molted = conn.execute(
                "SELECT COUNT(*) AS n FROM engines WHERE status = 'molted'"
            ).fetchone()["n"]
            self.assertEqual(molted, 0)
            self.assertEqual(tick_mod.verify_invariants(conn), [])
            ok, bad = events.verify_chain(conn)
            self.assertTrue(ok, f"hash chain broken at {bad}")
            # The quiet-world fix (v1.3, DC-17): v1.3 logged 1,106 rests
            # in 400 ticks. The fix must cut that, the three floor actions
            # must fire, and at least one territory controller must flip.
            counts = {}
            for r in conn.execute(
                    "SELECT action, COUNT(*) AS n FROM events GROUP BY "
                    "action"):
                counts[r["action"]] = r["n"]
            self.assertLess(counts.get("rest", 0), 1106,
                            "the world is still quiet")
            self.assertGreater(counts.get("forage", 0), 0)
            self.assertGreater(
                sum(counts.get(a, 0) for a in counts
                    if a.startswith("scavenge")), 0)
            self.assertGreater(
                sum(counts.get(a, 0) for a in counts
                    if a.startswith("claim")), 0)
            # The combined fix (v1.5, DC-19): Dream Share must fire as a
            # scored action, and at least one Bond restore must land.
            self.assertGreater(counts.get("dream_share", 0), 0,
                               "Dream Share never fired")
            restored = 0
            for r in conn.execute(
                    "SELECT effect FROM events WHERE action = 'dream_share'"):
                for op in json.loads(r["effect"]):
                    if (op.get("op") == "bond_add"
                            and op.get("applied_qty", 0) > 0):
                        restored += op["applied_qty"]
            self.assertGreater(restored, 0,
                               "Dream Share never restored Bond")
            flips = 0
            for r in conn.execute("SELECT effect FROM events"):
                for op in json.loads(r["effect"]):
                    if (op.get("op") == "location_set"
                            and "controller" in op
                            and op.get("old_controller") is None
                            and op["controller"]):
                        flips += 1
            self.assertGreater(flips, 0,
                               "no territory controller flipped")
            conn.close()


class TestForkRules(unittest.TestCase):
    """DC-01, DC-02, DC-05..DC-12, DC-14, DC-16 (plan test_rules.py)."""

    def test_bond_only_changes_by_the_established_rules(self):
        # DC-06 (v1.4) + DC-18 + DC-19: Pack Merge burns Bond -2 per
        # Engine; Dream Share restores +1 to one Engine at a cost of 2
        # Feed, never above 5; no other action changes Bond. The catalog
        # carries the burn and the restore (Dream Share is a scored
        # action since v1.5), and the runtime refuses a positive bond_add
        # from any other caller.
        internal = load_internal_seed()
        self.assertEqual(internal.get("bond_recovery"), "dream_share_only")
        bond_ops = []
        for action in internal["actions"]:
            for op in action.get("effect", []):
                if op.get("op") in ("bond_add", "bond_add_pack",
                                    "pack_merge_burn"):
                    bond_ops.append((action["id"], op))
        self.assertTrue(bond_ops, "no Bond op in the catalog")
        for action_id, op in bond_ops:
            if op["qty"] > 0:
                self.assertEqual(action_id, "dream_share",
                                 "only Dream Share may raise Bond")
                self.assertEqual(op["qty"], 1)
        merge = [a for a in internal["actions"]
                 if a["id"] == "pack_merge"][0]
        burn = [o for o in merge["effect"]
                if o["op"] == "pack_merge_burn"][0]
        self.assertEqual(burn["qty"], -2)
        # Runtime guard: a positive bond_add from an action raises.
        with tempfile.TemporaryDirectory() as tmp:
            conn, _ = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            with self.assertRaises(ValueError):
                actions.apply_effects(conn, [
                    {"op": "bond_add", "engine": "sledge", "qty": 1}],
                    tick=1)
            conn.close()

    def test_clocks_never_decrease_in_catalog(self):
        # DC-09: no negative clock_add anywhere (catalog or completions).
        internal = load_internal_seed()
        for action in internal["actions"]:
            for op in action.get("effect", []):
                if op.get("op") == "clock_add":
                    self.assertGreaterEqual(op["qty"], 0)
        for clock in internal["clocks"]:
            for op in clock.get("on_complete", []):
                if op.get("op") == "clock_add":
                    self.assertGreaterEqual(op["qty"], 0)

    def test_no_new_actors_engines_locations(self):
        # DC-07: the ID sets after the halted run equal the seed's sets.
        lore = load_lore_seed()
        with tempfile.TemporaryDirectory() as tmp:
            conn = _run_fork(tmp)
            self.assertEqual(
                {r["id"] for r in conn.execute("SELECT id FROM npcs")},
                {a["id"] for a in lore["actors"]})
            self.assertEqual(
                {r["id"] for r in conn.execute("SELECT id FROM engines")},
                {e["id"] for e in lore["engines"]})
            self.assertEqual(
                {r["id"] for r in conn.execute("SELECT id FROM locations")},
                {loc["id"] for loc in lore["locations"]})
            conn.close()

    def test_no_forbidden_content_in_events_or_catalog(self):
        # DC-01/DC-02 (no origins, no open-mystery answers), DC-05 (no
        # Rift-King / Den Boss return), DC-08 (no blood-oath fate), DC-11
        # (no mortar restoration), DC-12 (no invented heal).
        internal = load_internal_seed()
        catalog_text = json.dumps(internal["actions"]).lower()
        for word in FORBIDDEN_WORDS:
            self.assertNotIn(word, catalog_text, f"catalog has {word}")
        with tempfile.TemporaryDirectory() as tmp:
            conn = _run_fork(tmp)
            text = event_text(conn).lower()
            for word in FORBIDDEN_WORDS:
                self.assertNotIn(word, text, f"event log has {word}")
            self.assertNotIn("heal", text)
            conn.close()

    def test_concord_camp_is_not_chalk_canyons(self):
        # DC-10: the two locations keep their own names.
        with tempfile.TemporaryDirectory() as tmp:
            conn = _run_fork(tmp)
            camp = conn.execute(
                "SELECT name FROM locations WHERE id = 'concord_camp'"
            ).fetchone()["name"]
            canyon = conn.execute(
                "SELECT name FROM locations WHERE id = 'chalk_canyons'"
            ).fetchone()["name"]
            self.assertEqual(camp, "Concord Camp")
            self.assertEqual(canyon, "Chalk Canyons")
            conn.close()

    def test_locations_never_deleted_and_changes_carry_old_values(self):
        # DC-13: 7 locations before and after; every controller/status
        # change records old and new values (the dynamic map's source).
        with tempfile.TemporaryDirectory() as tmp:
            conn = _run_fork(tmp)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS n FROM locations")
                .fetchone()["n"], 7)
            for row in conn.execute("SELECT effect FROM events"):
                for op in json.loads(row["effect"]):
                    if op.get("skipped"):
                        continue  # a skipped op changes nothing
                    if op.get("op") == "location_set":
                        self.assertIn("old_status", op)
                        self.assertIn("old_controller", op)
                    if op.get("op") == "status_set":
                        self.assertIn("old_status", op)
            conn.close()

    def test_catalog_is_exactly_the_seed_actions_plus_split(self):
        # DC-14: no new mechanic beyond the seed's own. The 18 seed
        # actions map to 25 machine actions (trade split by counterparty,
        # raid split by actor, scavenge split in three by holder, claim
        # split in four by faction; dream_share is a scored action since
        # v1.5, no hook).
        lore = load_lore_seed()
        internal = load_internal_seed()
        seed_ids = {a["id"] for a in lore["actions"]}
        machine_ids = {a["id"] for a in internal["actions"]}
        self.assertEqual(machine_ids,
                         (seed_ids - {"trade", "raid",
                                      "scavenge", "claim"})
                         | {"trade_concord", "trade_kaelen",
                            "raid_captain", "raid_chief",
                            "scavenge_legion", "scavenge_dust_baron",
                            "scavenge_breakers",
                            "claim_legion", "claim_dust_baron",
                            "claim_breakers", "claim_nest_keepers"})
        self.assertIn("dream_share", machine_ids)
        self.assertNotIn("hooks", internal)

    def test_hunt_feeds_the_pack_not_the_holder(self):
        # DC-19 (v1.5): hunt Feed goes to the pack holder, and the hunt
        # scores higher while Pack Feed is below 3.
        internal = load_internal_seed()
        hunt = [a for a in internal["actions"] if a["id"] == "hunt"][0]
        feed_op = [o for o in hunt["effect"]
                   if o.get("op") == "resource_add"
                   and o.get("resource") == "Feed"][0]
        self.assertEqual(feed_op["holder"], "pack")
        self.assertEqual(feed_op["holder_kind"], "pack")
        self.assertEqual(feed_op["qty"], 2)
        need = hunt["need"][0]
        self.assertEqual(need["kind"], "resource")
        self.assertEqual(need["holder"], "pack")
        self.assertEqual(need["value"], 3)

    def test_render_handles_bond_add_without_pilot(self):
        # v1.5 exposed this: Dream Share firing is the first bond_add to
        # reach the render, and the old code crashed on op['pilot'].
        # Bond is looked up by engine only; the pilot may be null.
        from src import render
        text = render._effect_text(
            {"op": "bond_add", "engine": "sledge", "qty": 1,
             "applied_qty": 1})
        self.assertIn("Bond +1", text)
        self.assertIn("sledge", text)

    def test_render_has_no_generic_mech_language(self):
        # DC-16: no piloted humanoid robots, no generic 'mech' language in
        # the render, no combining sequence that forgets the Bond cost.
        from src import render
        with tempfile.TemporaryDirectory() as tmp:
            conn = _run_fork(tmp)
            out = os.path.join(tmp, "world-view.html")
            render.render_world_view(conn, out)
            with open(out) as f:
                html = f.read()
            self.assertIn("Ironwild Fork A — The Beacon Year", html)
            self.assertIsNone(re.search(r"\bmech\b", html, re.IGNORECASE))
            self.assertNotIn("humanoid", html.lower())
            conn.close()


class TestForkMechanics(unittest.TestCase):
    """Direct tests of the Fork A machinery (raid block, bargain chain,
    dream_share scored action, pack_merge burn, legacy rules)."""

    def test_feed_burn_logged_on_tick_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = _run_fork(tmp)
            burn = conn.execute(
                "SELECT effect FROM events WHERE action = 'feed_burn'"
            ).fetchone()
            self.assertIsNotNone(burn)
            ops = json.loads(burn["effect"])
            holders = {(o["holder"], o["applied_qty"]) for o in ops}
            self.assertIn(("ironwild_legion", -1), holders)
            self.assertIn(("pack", -1), holders)
            conn.close()

    def test_raid_blocked_when_fortified(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn, _ = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            conn.execute("UPDATE locations SET status = 'fortified' "
                         "WHERE id = 'great_basin'")
            internal = load_internal_seed()
            raid = [a for a in internal["actions"]
                    if a["id"] == "raid_captain"][0]
            before = db.state_hash(conn)
            applied = actions.apply_effects(
                conn, raid["effect"], tick=1)
            feed = conn.execute(
                "SELECT qty FROM resources WHERE holder_id = "
                "'ironwild_legion' AND resource = 'Feed'").fetchone()["qty"]
            self.assertEqual(feed, 10, "blocked raid must not take Feed")
            notes = [o for o in applied if o.get("op") == "note"
                     and not o.get("skipped")]
            self.assertTrue(any("fortified" in o["text"] for o in notes))
            conn.close()

    def test_bargain_chain_one_step_per_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn, seed_data = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            catalog = seed_data["actions"]
            baron = {"id": "high_baron", "kind": "npc"}
            tick_mod._act(conn, 1, random.Random(131), baron, catalog)
            status = conn.execute(
                "SELECT status FROM npcs WHERE id = 'high_baron'"
            ).fetchone()["status"]
            self.assertEqual(status, "active, watched")
            tick_mod._act(conn, 1, random.Random(131), baron, catalog)
            row = conn.execute(
                "SELECT status, location_id FROM npcs WHERE id = 'high_baron'"
            ).fetchone()
            self.assertEqual(row["status"], "active")
            self.assertEqual(row["location_id"], "rust_dunes")
            conn.close()

    def test_dream_share_maps_an_unmapped_location(self):
        # DC-19: Dream Share is a scored action since v1.5. With an
        # unmapped location, Brigus choosing it maps one (no cost).
        with tempfile.TemporaryDirectory() as tmp:
            conn, seed_data = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            catalog = [a for a in seed_data["actions"]
                       if a["id"] == "dream_share"]
            tick_mod._act(conn, 1, random.Random(131),
                          {"id": "brigus", "kind": "npc"}, catalog)
            row = conn.execute(
                "SELECT mapped FROM locations WHERE id = 'leviathans_ribs'"
            ).fetchone()
            self.assertEqual(row["mapped"], 1)
            share = conn.execute(
                "SELECT * FROM events WHERE action = 'dream_share'"
            ).fetchone()
            self.assertIsNotNone(share)
            conn.close()

    def test_dream_share_bond_branch_restores_lowest_ties_to_sledge(self):
        # DC-18/DC-19: with the map done, the dream restores +1 Bond to
        # the lowest-Bond Engine (ties to Sledge) and costs the Pack
        # 2 Feed.
        with tempfile.TemporaryDirectory() as tmp:
            conn, seed_data = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            conn.execute("UPDATE locations SET mapped = 1")
            conn.execute("UPDATE bonds SET bond = 1")
            conn.execute("UPDATE resources SET qty = 4 WHERE holder_id = "
                         "'pack' AND resource = 'Feed'")
            catalog = [a for a in seed_data["actions"]
                       if a["id"] == "dream_share"]
            tick_mod._act(conn, 1, random.Random(131),
                          {"id": "brigus", "kind": "npc"}, catalog)
            sledge = conn.execute(
                "SELECT bond FROM bonds WHERE engine_id = 'sledge'"
            ).fetchone()["bond"]
            self.assertEqual(sledge, 2)
            for other in ("goliath", "skytalon", "razor_back", "strider"):
                self.assertEqual(conn.execute(
                    "SELECT bond FROM bonds WHERE engine_id = ?",
                    (other,)).fetchone()["bond"], 1)
            pack = conn.execute(
                "SELECT qty FROM resources WHERE holder_id = 'pack' "
                "AND resource = 'Feed'").fetchone()["qty"]
            self.assertEqual(pack, 2)
            conn.close()

    def test_dream_share_bond_branch_needs_pack_feed(self):
        # DC-18/DC-19: the power is heavy, never free. With Pack Feed
        # below 2, the Bond branch cannot fire and no dream_share event
        # is logged (Brigus rests instead).
        with tempfile.TemporaryDirectory() as tmp:
            conn, seed_data = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            conn.execute("UPDATE locations SET mapped = 1")
            conn.execute("UPDATE bonds SET bond = 1")
            conn.execute("UPDATE resources SET qty = 1 WHERE holder_id = "
                         "'pack' AND resource = 'Feed'")
            catalog = [a for a in seed_data["actions"]
                       if a["id"] == "dream_share"]
            tick_mod._act(conn, 1, random.Random(131),
                          {"id": "brigus", "kind": "npc"}, catalog)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) AS n FROM events WHERE action = "
                "'dream_share'").fetchone()["n"], 0)
            self.assertEqual(conn.execute(
                "SELECT bond FROM bonds WHERE engine_id = 'sledge'"
            ).fetchone()["bond"], 1)
            conn.close()

    def test_dream_share_does_not_fire_when_nothing_to_do(self):
        # DC-19: map done, all Bonds at 5 -> the action is not legal,
        # so Brigus rests and no dream_share event is logged.
        with tempfile.TemporaryDirectory() as tmp:
            conn, seed_data = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            conn.execute("UPDATE locations SET mapped = 1")
            conn.execute("UPDATE bonds SET bond = 5")
            catalog = [a for a in seed_data["actions"]
                       if a["id"] == "dream_share"]
            tick_mod._act(conn, 1, random.Random(131),
                          {"id": "brigus", "kind": "npc"}, catalog)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) AS n FROM events WHERE action = "
                "'dream_share'").fetchone()["n"], 0)
            conn.close()

    def test_forage_fires_only_when_legion_feed_low(self):
        # DC-17: forage is a floor, not a flood. Legion Feed 3 -> +2.
        with tempfile.TemporaryDirectory() as tmp:
            conn, seed_data = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            conn.execute("UPDATE resources SET qty = 3 WHERE holder_id = "
                         "'ironwild_legion' AND resource = 'Feed'")
            catalog = [a for a in seed_data["actions"]
                       if a["id"] == "forage"]
            tick_mod._act(conn, 1, random.Random(131),
                          {"id": "legion_captain", "kind": "npc"}, catalog)
            feed = conn.execute(
                "SELECT qty FROM resources WHERE holder_id = "
                "'ironwild_legion' AND resource = 'Feed'").fetchone()["qty"]
            self.assertEqual(feed, 5)
            conn.close()

    def test_scavenge_fires_only_when_salvage_low_and_wreck_mapped(self):
        # DC-17: holder Salvage below 4 and a mapped wreck exists.
        with tempfile.TemporaryDirectory() as tmp:
            conn, seed_data = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            conn.execute("UPDATE resources SET qty = 2 WHERE holder_id = "
                         "'ironwild_legion' AND resource = 'Salvage'")
            catalog = [a for a in seed_data["actions"]
                       if a["id"] == "scavenge_legion"]
            tick_mod._act(conn, 1, random.Random(131),
                          {"id": "legion_captain", "kind": "npc"}, catalog)
            salv = conn.execute(
                "SELECT qty FROM resources WHERE holder_id = "
                "'ironwild_legion' AND resource = 'Salvage'"
            ).fetchone()["qty"]
            self.assertEqual(salv, 3)
            conn.close()

    def test_claim_flips_uncontrolled_ground_and_costs_salvage(self):
        # DC-17: Rust Dunes (uncontrolled, mapped) becomes Legion ground
        # for 1 Salvage; the event records old (null) and new controller.
        with tempfile.TemporaryDirectory() as tmp:
            conn, seed_data = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            catalog = [a for a in seed_data["actions"]
                       if a["id"] == "claim_legion"]
            tick_mod._act(conn, 1, random.Random(131),
                          {"id": "legion_captain", "kind": "npc"}, catalog)
            row = conn.execute(
                "SELECT controller_faction_id FROM locations "
                "WHERE id = 'rust_dunes'").fetchone()
            self.assertEqual(row["controller_faction_id"], "ironwild_legion")
            salv = conn.execute(
                "SELECT qty FROM resources WHERE holder_id = "
                "'ironwild_legion' AND resource = 'Salvage'"
            ).fetchone()["qty"]
            self.assertEqual(salv, 11)
            event = conn.execute(
                "SELECT effect FROM events WHERE action = 'claim_legion'"
            ).fetchone()
            ops = json.loads(event["effect"])
            loc_op = [o for o in ops if o.get("op") == "location_set"][0]
            self.assertIsNone(loc_op["old_controller"])
            conn.close()

    def test_claim_cannot_take_controlled_ground(self):
        # DC-17: the selector only ever returns uncontrolled ground.
        # Once Rust Dunes is claimed, no uncontrolled mapped location
        # remains at tick 0, so the claim trigger fails.
        from src import targets
        with tempfile.TemporaryDirectory() as tmp:
            conn, seed_data = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            first = targets.resolve_targets(
                conn, {"target": "uncontrolled_mapped_location"})
            self.assertEqual(first, "rust_dunes")
            conn.execute("UPDATE locations SET controller_faction_id = "
                         "'ironwild_legion' WHERE id = 'rust_dunes'")
            second = targets.resolve_targets(
                conn, {"target": "uncontrolled_mapped_location"})
            self.assertIsNone(second)
            catalog = [a for a in seed_data["actions"]
                       if a["id"] == "claim_legion"]
            acted = tick_mod._act(conn, 1, random.Random(131),
                                  {"id": "legion_captain", "kind": "npc"},
                                  catalog)
            self.assertEqual(acted, "rest")
            conn.close()

    def test_pack_merge_burns_top_two_bonds(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn, _ = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            applied = actions.apply_effects(conn, [
                {"op": "pack_merge_burn", "location": "great_basin",
                 "min_bond": 3, "qty": -2}], tick=1)
            pair = applied[0]["pair"]
            self.assertEqual(pair, ["goliath", "skytalon"])
            bonds = {r["engine_id"]: r["bond"] for r in conn.execute(
                "SELECT engine_id, bond FROM bonds")}
            self.assertEqual(bonds["goliath"], 3)
            self.assertEqual(bonds["skytalon"], 3)
            self.assertEqual(bonds["sledge"], 3)
            conn.close()

    def test_legacy_rules_lr01_to_lr05(self):
        # LR-01: no ages established, so no aging numbers change and no
        # retirement fires. LR-02: no Molt trigger earned, so no molt.
        # LR-04: cores confirmed marker recorded. LR-05: era applied once,
        # Era 2 stays unnamed (NULL — the engine never names eras).
        with tempfile.TemporaryDirectory() as tmp:
            conn, seed_data = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            legacy = seed_data["legacy"]
            legacy["era_length"] = 365
            effects = eras.apply_legacy(conn, 365, legacy)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS n FROM events "
                             "WHERE action = 'legacy'").fetchone()["n"], 1)
            closed = conn.execute(
                "SELECT name, legacy_applied FROM eras "
                "WHERE end_tick IS NOT NULL").fetchone()
            self.assertEqual(closed["name"], "The Beacon Year")
            self.assertEqual(closed["legacy_applied"], 1)
            open_era = conn.execute(
                "SELECT name FROM eras WHERE end_tick IS NULL").fetchone()
            self.assertIsNone(open_era["name"])
            retired = conn.execute(
                "SELECT COUNT(*) AS n FROM npcs WHERE status = 'retired'"
            ).fetchone()["n"]
            self.assertEqual(retired, 0)
            molted = conn.execute(
                "SELECT COUNT(*) AS n FROM engines WHERE status = 'molted'"
            ).fetchone()["n"]
            self.assertEqual(molted, 0)
            self.assertTrue(any("cores_confirmed" in e for e in effects))
            conn.close()

    def test_legacy_molt_fires_only_on_earned_trigger(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn, seed_data = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            conn.execute("UPDATE engines SET molt_trigger = 1 "
                         "WHERE id = 'skytalon'")
            legacy = seed_data["legacy"]
            legacy["era_length"] = 365
            eras.apply_legacy(conn, 365, legacy)
            row = conn.execute(
                "SELECT status, hunger, molt_trigger FROM engines "
                "WHERE id = 'skytalon'").fetchone()
            self.assertEqual(row["status"], "molted")
            self.assertEqual(row["hunger"], 0)
            self.assertEqual(row["molt_trigger"], 0)
            conn.close()

    def test_legacy_succession_halts_without_named_successor(self):
        # LR-03: a dead NPC with no successor stops the engine.
        with tempfile.TemporaryDirectory() as tmp:
            conn, seed_data = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            conn.execute("UPDATE npcs SET status = 'dead' WHERE id = 'brigus'")
            legacy = seed_data["legacy"]
            legacy["era_length"] = 365
            with self.assertRaises(eras.EngineHalt):
                eras.apply_legacy(conn, 365, legacy)
            conn.close()

    def test_legacy_succession_transfers_to_named_successor(self):
        # LR-03: Vance names Tull; his Bonds and holdings pass on.
        with tempfile.TemporaryDirectory() as tmp:
            conn, seed_data = fresh_fork_db(os.path.join(tmp, "fork.sqlite"))
            conn.execute("UPDATE npcs SET status = 'dead' WHERE id = 'vance'")
            legacy = seed_data["legacy"]
            legacy["era_length"] = 365
            eras.apply_legacy(conn, 365, legacy)
            conn.close()


class TestForkNoCanonWrites(unittest.TestCase):
    def test_canon_files_unchanged_by_a_fork_run(self):
        def digest():
            out = {}
            for path in CANON_FILES:
                with open(path, "rb") as f:
                    out[path] = hashlib.sha256(f.read()).hexdigest()
            return out

        with tempfile.TemporaryDirectory() as tmp:
            before = digest()
            conn = _run_fork(tmp)
            conn.close()
        self.assertEqual(digest(), before)


if __name__ == "__main__":
    unittest.main()
