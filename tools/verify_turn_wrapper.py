"""Acceptance verification for the turn wrapper (docs/turn-wrapper-plan.md).

Runs Fork B Turns 2, 3, 4 in order on a COPY of the live Fork B DB
two ways and compares the state hash after each turn:
  A. the wrapper: turn_mod.run_turn (local file, --yes equivalent)
  B. the current pipeline's core functions: sweep.apply_sweep +
     tick.run_ticks(conn, 3) + handshake.generate_handshake
The hashes must match exactly. Nothing here touches the live DB,
the live registry, or the live runs tree: both copies run under
temp dirs, and the live DB is only read (copied).
"""

import json
import os
import shutil
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="turn-verify-")
os.environ["IRONWILD_PROPOSALS_DIR"] = os.path.join(TMP, "proposals")
os.environ["IRONWILD_RUNS_DIR"] = os.path.join(TMP, "runs")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import db, handshake as handshake_mod  # noqa: E402
from src import sweep as sweep_mod  # noqa: E402
from src import tick as tick_mod  # noqa: E402
from src import turn as turn_mod  # noqa: E402

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE_DB = os.path.join(ENGINE_DIR, "state", "ironwild-fork-b-test.sqlite")
PROP_DIR = os.path.join(ENGINE_DIR, "runs", "proposals", "fork-b")


def _read_prop(pid):
    with open(os.path.join(PROP_DIR, pid, "proposal.txt"),
              encoding="utf-8") as f:
        return f.read()


def _revise(text, turn):
    """Bond 1/5 -> Bond 2/5 (the post-tick value). Exactly one
    replacement must happen, or the block is not the one we think."""
    revised = text.replace("Bond 1/5", "Bond 2/5")
    assert revised.count("Bond 2/5") == text.count("Bond 1/5") == 1, \
        "Turn %d block does not carry exactly one Bond 1/5" % turn
    assert "newly awakened and battered" in revised
    return revised


def main():
    flag_path = os.path.join(TMP, "session.json")
    with open(flag_path, "w") as f:
        json.dump({"session_open": False,
                   "world_id": "ironwild-fork-b"}, f)
    blocks = [
        (2, _read_prop("prop-2-763a40e0")),
        (3, _revise(_read_prop("prop-3-bdfd9c07"), 3)),
        (4, _revise(_read_prop("prop-4-18912941"), 4)),
    ]
    db_a = os.path.join(TMP, "a.sqlite")
    db_b = os.path.join(TMP, "b.sqlite")
    shutil.copyfile(LIVE_DB, db_a)
    shutil.copyfile(LIVE_DB, db_b)

    ok = True
    for turn, text in blocks:
        # Path A: the wrapper.
        record = turn_mod.run_turn(
            db_a, text, name="turn-%d.txt" % turn, yes=True,
            flag_path=flag_path)
        conn_a = db.connect(db_a)
        hash_a = db.state_hash(conn_a)
        tick_a = db.get_tick(conn_a)
        conn_a.close()
        # Path B: the pipeline's core functions, same inputs.
        conn_b = db.connect(db_b)
        try:
            parsed = sweep_mod.parse_state_block(text)
            tick_before = db.get_tick(conn_b)
            result = sweep_mod.apply_sweep(
                parsed, conn_b, "Bryan", flag_path=flag_path)
            tick_mod.run_ticks(conn_b, 3)
            hs_b = handshake_mod.generate_handshake(
                conn_b, result["carried"], since_tick=tick_before)
            hash_b = db.state_hash(conn_b)
            tick_b = db.get_tick(conn_b)
        finally:
            conn_b.close()
        match = (hash_a == hash_b and tick_a == tick_b
                 and record["handshake"]["text"] == hs_b["text"])
        ok = ok and match
        print("Turn %d: wrapper hash %s | pipeline hash %s | "
              "tick %d/%d | handshake identical: %s -> %s"
              % (turn, hash_a[:12], hash_b[:12], tick_a, tick_b,
                 record["handshake"]["text"] == hs_b["text"],
                 "MATCH" if match else "MISMATCH"))
    print("temp dir (kept for inspection): %s" % TMP)
    print("ACCEPTANCE: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
