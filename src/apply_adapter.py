"""Shared apply adapter: the one place where the turn-order and
duplicate checks live.

Every apply path calls `check_apply_gate` before touching the DB:
the Drive path (`proposals.apply_proposal`), the local-file path
(`apply_local_block` / `apply_registered` below), and the manual
sweep path (`run.cmd_sweep --apply`). `sweep.apply_sweep` itself is
unchanged: it stays the low-level "apply this validated block in
one transaction", so no existing direct caller breaks.

The local-file path reuses the Drive path's safeguards, with the
local file in place of the Drive re-download: the block is
registered as a proposal (proposal.txt + review.json + registry
entry, content hash recorded), the stored file is hash-checked at
apply time, and the approval binding (approver, source
"local-file", content hash, timestamp) is recorded in applied.json
exactly as `apply_proposal` records the Drive binding.

Note on imports: this module imports `proposals` lazily inside
the functions that use it, because `proposals` imports this
module (for the gate call in `apply_proposal`) and a top-level
cycle would be fragile.
"""

import datetime
import json
import os

from . import db
from . import forks as forks_mod
from . import sweep as sweep_mod


def _applied_proposal_id(conn, turn, content_hash):
    """The proposal id for an already-applied (turn, hash) pair, or
    None. Checks the applied_turns table when it exists (Step 1)
    and the registry (pre-migration applies + the Drive path's
    record) — both, because the table starts empty on a migrated
    DB. A manual-sweep row has no proposal id; it reports as
    "manual-sweep"."""
    from . import proposals as proposals_mod

    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "applied_turns" in tables:
        row = conn.execute(
            "SELECT proposal_id FROM applied_turns "
            "WHERE turn = ? AND content_hash = ?",
            (turn, content_hash)).fetchone()
        if row is not None:
            return row["proposal_id"] or "manual-sweep"
    registry = proposals_mod.load_registry()
    for entry in registry.values():
        if (entry.get("status") == "applied"
                and entry.get("turn") == turn
                and entry.get("content_hash") == content_hash):
            return entry.get("proposal_id")
    return None


def check_apply_gate(parsed, conn, content_hash=None):
    """Raise SweepError unless this block may be applied now.

    - The turn must be exactly last_swept_turn + 1 (or the fork's
      first turn when nothing has been swept yet). Otherwise the
      refusal names both turns: "expected Turn N, got Turn M".
    - When a content hash is given, the (turn, hash) pair must not
      already be applied. Otherwise the refusal is "already
      applied". Source of truth today: registry entries with
      status "applied" matching turn + hash. Step 1 adds the
      `applied_turns` table; the gate will check it first when it
      exists, with the registry as fallback.
    """
    from . import proposals as proposals_mod

    turn = parsed["turn"]
    if content_hash is not None:
        pid = _applied_proposal_id(conn, turn, content_hash)
        if pid is not None:
            raise sweep_mod.SweepError(
                "Turn %d is already applied (proposal %s); "
                "refusing to double-apply" % (turn, pid))
    last_swept = db.get_meta(conn, "last_swept_turn")
    world_id = db.get_meta(conn, "world_id", "ironwild-fork-a")
    expected = ((int(last_swept) + 1) if last_swept is not None
                else forks_mod.fork_first_turn(world_id))
    if turn != expected:
        raise sweep_mod.SweepError(
            "expected Turn %d, got Turn %d" % (expected, turn))
    return expected


def register_local_block(text, conn, name="local-file"):
    """Register a local block as a proposal. Never writes the DB.

    Reuses `proposals.intake_file` with no Drive file id: it writes
    proposal.txt + review.json and the registry entry (content hash
    recorded, status reviewed or rejected). The entry is tagged
    source "local-file". Returns the registry entry.
    """
    from . import proposals as proposals_mod

    entry = proposals_mod.intake_file(None, name, text, conn)
    entry["source"] = "local-file"
    registry = proposals_mod.load_registry()
    registry[entry["proposal_id"]] = entry
    proposals_mod.save_registry(registry)
    return entry


def apply_registered(pid, conn, approved_by="Bryan", flag_path=None,
                     resource_changes=None, lore_approval=None):
    """Apply a registered proposal by ID, with approval binding.

    The stored proposal.txt is hash-checked against the registered
    hash, the shared gate runs, then `apply_sweep` applies it in
    one transaction. The approval binding (approver, source,
    content hash, timestamp) is recorded in applied.json, mirroring
    `apply_proposal`. Raises SweepError on any refusal — nothing
    is applied.
    """
    from . import proposals as proposals_mod

    db.init_schema(conn)  # migrate: applied_turns + prev_hash index
    registry = proposals_mod.load_registry()
    entry = registry.get(pid)
    if entry is None:
        raise sweep_mod.SweepError(
            "unknown proposal %s: no such proposal in the registry"
            % pid)
    if entry["status"] != "reviewed":
        raise sweep_mod.SweepError(
            "proposal %s is %s, not reviewed; only a reviewed "
            "proposal can be applied" % (pid, entry["status"]))
    if approved_by != "Bryan":
        raise sweep_mod.SweepError(
            "proposal applies need Bryan's approval; got %r"
            % (approved_by or "",))
    with open(os.path.join(proposals_mod._proposal_dir(pid),
                           "proposal.txt"),
              encoding="utf-8") as f:
        stored = f.read()
    if proposals_mod.content_hash(stored) != entry["content_hash"]:
        raise sweep_mod.SweepError(
            "stored proposal %s does not match its recorded hash; "
            "refusing to apply" % pid)
    parsed = sweep_mod.parse_state_block(stored)
    check_apply_gate(parsed, conn, entry["content_hash"])
    result = sweep_mod.apply_sweep(
        parsed, conn, approved_by, flag_path=flag_path,
        resource_changes=resource_changes, lore_approval=lore_approval,
        content_hash=entry["content_hash"], proposal_id=pid,
        source=entry.get("source", "local-file"))
    result["proposal_binding"] = {
        "proposal_id": pid,
        "drive_file_id": entry.get("drive_file_id"),
        "source": entry.get("source", "local-file"),
        "content_hash": entry["content_hash"],
        "approved_by": "Lore" if lore_approval else approved_by,
        "applied_at": result["applied_at"],
    }
    if lore_approval:
        result["proposal_binding"]["lore_approval"] = lore_approval
    entry["status"] = "applied"
    entry["applied_at"] = result["proposal_binding"]["applied_at"]
    registry[pid] = entry
    proposals_mod.save_registry(registry)
    with open(os.path.join(proposals_mod._proposal_dir(pid),
                           "applied.json"), "w",
              encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    return result


def apply_local_block(text, conn, name="local-file", approved_by="Bryan",
                      flag_path=None, resource_changes=None,
                      lore_approval=None):
    """Register a local block and apply it. Convenience wrapper
    around register_local_block + apply_registered."""
    entry = register_local_block(text, conn, name=name)
    if entry["status"] == "rejected":
        raise sweep_mod.SweepError(
            "local block rejected: %s" % (entry.get("error") or
                                          "validation failed"))
    return apply_registered(
        entry["proposal_id"], conn, approved_by=approved_by,
        flag_path=flag_path, resource_changes=resource_changes,
        lore_approval=lore_approval)
