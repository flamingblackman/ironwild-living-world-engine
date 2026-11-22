"""One-command turn wrapper: `python3 -m src.run turn`.

Chains the steps the engine already has. It adds no new rules.
Drive and the 15-minute poll stay available but are no longer the
daily path.

Order, stop at the first failure:
1. Read the block from --file or stdin. Never from Drive.
2. Refuse if the session flag is open.
3. Parse and validate with the existing functions. Print findings.
4. Turn-order check (shared gate): the turn must be exactly
   last_swept_turn + 1. "expected Turn N, got Turn M".
5. Print the old-to-new diff and the routing tier: AUTO (zero
   changes, zero findings, pure carry-over), REVIEW (anything
   else, no errors), HOLD (validation errors).
6. AUTO applies. REVIEW asks for confirmation unless --yes.
   HOLD never applies.
7. Before apply, a SQLite backup to
   runs/backups/<fork>-turn-<n>-pre.sqlite (+ sidecar json).
8. Apply through the shared adapter. Approver "Bryan", source
   "local-file", content hash recorded.
9. Tick 3 days using the existing path: `tick_mod.run_ticks(conn, 3)`
   with NO rng argument, exactly as `attempt_auto_apply` and
   `cmd_tick` call it today — the same sequence the pipeline
   produces. Under rng_scheme v1 `run_ticks` re-seeds
   `random.Random(rng_seed)` on the call; under v2 the per-actor
   streams in tick.rng_for govern. Do not change tick semantics.
   On EngineHalt: report clearly, stop, exit 2, no retry, no
   handshake.
10. Generate the next handshake, write it to
    runs/<fork>/handshakes/turn-<n+1>.txt, and print it.
11. Print a short summary. A record file
    runs/<fork>/turns/turn-<n>.json is written (mirrors
    auto-applied.json).

`--dry-run` does steps 1-5 only and writes nothing.
`--queue` lists proposals and files waiting, in apply order.
`--rollback` restores the most recent pre-apply backup after
confirmation, verifies the restored state hash against the
sidecar, and resets that turn's registry entry from `applied`
back to `reviewed` so the same block can be re-applied.
"""

import datetime
import json
import os
import shutil
import sqlite3
import sys

from . import apply_adapter as adapter_mod
from . import auto_apply as auto_apply_mod
from . import db
from . import events
from . import handshake as handshake_mod
from . import proposals as proposals_mod
from . import session as session_mod
from . import sweep as sweep_mod
from . import tick as tick_mod

TICKS_PER_TURN = 3


class TurnError(sweep_mod.SweepError):
    """A turn-wrapper refusal. Nothing was applied."""


def _runs_dir():
    return os.environ.get("IRONWILD_RUNS_DIR", "runs")


def _fork_slug(conn, db_path):
    """runs/<fork>/... slug: the DB's world_id minus the
    "ironwild-" prefix, else the DB filename stem."""
    world_id = db.get_meta(conn, "world_id") or ""
    if world_id.startswith("ironwild-"):
        return world_id[len("ironwild-"):]
    if world_id:
        return world_id
    stem = os.path.splitext(os.path.basename(db_path))[0]
    for prefix in ("ironwild-",):
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
    return stem.replace("-test", "")


def _load_last_carried(conn):
    last_swept = db.get_meta(conn, "last_swept_turn")
    if last_swept is None:
        return None
    path = os.path.join(_runs_dir(), "sweeps",
                        "turn-%s" % last_swept, "carried.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_sweep_records(out_dir, result, review_record):
    """The standard sweep records the checkpoint reads:
    applied.json + carried.json + review.json under
    runs/sweeps/turn-<n>/."""
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "applied.json"), "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    with open(os.path.join(out_dir, "carried.json"), "w") as f:
        json.dump(result["carried"], f, indent=2, sort_keys=True)
    with open(os.path.join(out_dir, "review.json"), "w") as f:
        json.dump(review_record, f, indent=2, sort_keys=True)


def _backup(conn, db_path, fork, turn, proposal_id):
    """Consistent pre-apply backup via the sqlite3 backup API.
    Returns (backup_path, sidecar_path). The sidecar records the
    pre-apply state hash so a rollback can verify the restore."""
    out_dir = os.path.join(_runs_dir(), "backups")
    os.makedirs(out_dir, exist_ok=True)
    backup_path = os.path.join(
        out_dir, "%s-turn-%d-pre.sqlite" % (fork, turn))
    sidecar_path = backup_path + ".json"
    conn.commit()  # close any open read transaction: clean snapshot
    dest = sqlite3.connect(backup_path)
    try:
        conn.backup(dest)
    finally:
        dest.close()
    with open(sidecar_path, "w") as f:
        json.dump({
            "fork": fork,
            "turn": turn,
            "proposal_id": proposal_id,
            "tick": db.get_tick(conn),
            "state_hash": db.state_hash(conn),
            "created_at": datetime.datetime.now(
                datetime.timezone.utc).isoformat(),
        }, f, indent=2, sort_keys=True)
    return backup_path, sidecar_path


def _confirm(prompt):
    """True only on an explicit yes. EOF (piped stdin) is a no."""
    try:
        answer = input(prompt + " [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def run_turn(db_path, text, name="local-file", yes=False, dry_run=False,
             flag_path=None):
    """Run one turn from a local block. Returns the turn record.

    Raises TurnError on any refusal; nothing is applied then.
    Raises tick_mod.EngineHalt (as TurnError) when the post-apply
    tick halts: the apply stands, no handshake is generated, no
    retry happens.
    """
    conn = db.connect(db_path)
    try:
        return _run_turn(conn, db_path, text, name=name, yes=yes,
                         dry_run=dry_run, flag_path=flag_path)
    except sweep_mod.SweepError as exc:
        # The wrapper's public contract is TurnError; the gate and
        # the apply path raise plain SweepError.
        if isinstance(exc, TurnError):
            raise
        raise TurnError(str(exc)) from exc
    finally:
        conn.close()


def _run_turn(conn, db_path, text, name="local-file", yes=False,
              dry_run=False, flag_path=None):
    flag_path = flag_path or session_mod.FLAG_PATH
    reason = session_mod.refuse_reason(flag_path)
    if reason:
        raise TurnError(reason)
    try:
        parsed = sweep_mod.parse_state_block(text)
    except sweep_mod.SweepError as exc:
        raise TurnError("parse failed: %s" % exc)
    row = conn.execute(
        "SELECT value FROM meta WHERE key = 'world_id'").fetchone()
    world_id = row["value"] if row else "ironwild-fork-a"
    findings = (sweep_mod.validate(parsed, conn)
                + proposals_mod.validate_fork(parsed, world_id))
    try:
        changes = sweep_mod.diff(parsed, conn)
    except sweep_mod.SweepError as exc:
        raise TurnError("apply refused: %s" % exc)
    review = sweep_mod.summarize(parsed, findings, changes, conn=conn)
    errors = [f for f in findings if f["level"] == "error"]
    # Step 4: the shared gate. Duplicate first ("already applied"),
    # then turn order ("expected Turn N, got Turn M").
    adapter_mod.check_apply_gate(
        parsed, conn, proposals_mod.content_hash(text))
    # Step 5: routing tier.
    if errors:
        tier = "HOLD"
        flags = []
    else:
        eligible, _reasons = auto_apply_mod.check_eligible(
            parsed, findings, changes, conn, flag_path)
        flags = auto_apply_mod.flag_narrative_changes(
            parsed, _load_last_carried(conn), conn)
        tier = "AUTO" if (eligible and not flags) else "REVIEW"
    record = {
        "turn": parsed["turn"],
        "state_version": parsed["state_version"],
        "tier": tier,
        "findings": findings,
        "changes": changes,
        "flags": flags,
        "review": review,
        "dry_run": dry_run,
    }
    if dry_run:
        return record
    if tier == "HOLD":
        raise TurnError(
            "HOLD: validation errors block apply: "
            + "; ".join(f["message"] for f in errors))
    if tier == "REVIEW" and not yes:
        why = ("; ".join(
            "%s: %s" % (f["code"], f["detail"]) for f in flags)
            or "%d change(s)" % len(changes))
        if not _confirm(
                "REVIEW Turn %d (%s). Apply?" % (parsed["turn"], why)):
            raise TurnError("not confirmed; nothing applied")
    fork = _fork_slug(conn, db_path)
    # Register first so the backup sidecar can name the proposal.
    entry = adapter_mod.register_local_block(text, conn, name=name)
    if entry["status"] == "rejected":
        raise TurnError("local block rejected: %s"
                        % (entry.get("error") or "validation failed"))
    backup_path, _sidecar = _backup(
        conn, db_path, fork, parsed["turn"], entry["proposal_id"])
    tick_before = db.get_tick(conn)
    events_before = conn.execute(
        "SELECT COUNT(*) FROM events").fetchone()[0]
    result = adapter_mod.apply_registered(
        entry["proposal_id"], conn, approved_by="Bryan",
        flag_path=flag_path)
    out_dir = os.path.join(_runs_dir(), "sweeps",
                           "turn-%d" % result["turn"])
    review_record = {
        "ok": True, "dry_run": False, "turn": result["turn"],
        "state_version": entry["state_version"],
        "findings": entry["findings"], "changes": result["applied"],
        "review": entry["review"],
        "proposal_id": entry["proposal_id"],
        "proposal_binding": result["proposal_binding"],
        "turn_wrapper": True,
    }
    _write_sweep_records(out_dir, result, review_record)
    # Step 9: tick 3 days on the existing path. No rng argument:
    # run_ticks uses the DB's rng_scheme (v1 re-seeds
    # random.Random(rng_seed) on the call; v2 uses the per-actor
    # streams), exactly as attempt_auto_apply and cmd_tick do
    # today. Do not change tick semantics.
    tick_halted = None
    try:
        tick_after = tick_mod.run_ticks(conn, TICKS_PER_TURN)
    except tick_mod.EngineHalt as exc:
        tick_after = db.get_tick(conn)
        tick_halted = str(exc)
    problems = tick_mod.verify_invariants(conn)
    chain_ok, _ = events.verify_chain(conn)
    events_after = conn.execute(
        "SELECT COUNT(*) FROM events").fetchone()[0]
    record.update({
        "proposal_id": entry["proposal_id"],
        "content_hash": entry["content_hash"],
        "source": "local-file",
        "approved_by": "Bryan",
        "applied": result["applied"],
        "tick_before": tick_before,
        "tick_after": tick_after,
        "events_before": events_before,
        "events_after": events_after,
        "state_hash": db.state_hash(conn),
        "hash_chain_ok": chain_ok,
        "invariant_problems": problems,
        "tick_halted": tick_halted,
        "backup_path": backup_path,
        "handshake": None,
    })
    if tick_halted or problems or not chain_ok:
        _write_turn_record(fork, record)
        raise TurnError(
            "Turn %d applied but the follow-up failed — tick halted: "
            "%s; invariant problems: %s; hash chain ok: %s. No "
            "handshake generated; the apply stands."
            % (parsed["turn"], tick_halted, problems, chain_ok))
    # Step 10: next handshake, per-fork path, printed for copy-paste.
    hs = handshake_mod.generate_handshake(
        conn, result["carried"], since_tick=tick_before)
    next_turn = result["turn"] + 1
    hs_path = os.path.join(_runs_dir(), fork, "handshakes",
                           "turn-%d.txt" % next_turn)
    os.makedirs(os.path.dirname(hs_path), exist_ok=True)
    with open(hs_path, "w") as f:
        f.write(hs["text"] + "\n")
    with open(hs_path + ".json", "w") as f:
        json.dump(hs["meta"], f, indent=2, sort_keys=True)
    record["handshake"] = {
        "path": hs_path,
        "words": hs["meta"]["words"],
        "turn": next_turn,
        "state_version": hs["meta"]["state_version"],
        "text": hs["text"],
    }
    _write_turn_record(fork, record)
    return record


def _write_turn_record(fork, record):
    out_dir = os.path.join(_runs_dir(), fork, "turns")
    os.makedirs(out_dir, exist_ok=True)
    stored = {k: v for k, v in record.items() if k != "handshake"}
    if record.get("handshake"):
        stored["handshake"] = {
            k: v for k, v in record["handshake"].items()
            if k != "text"}
    with open(os.path.join(out_dir, "turn-%d.json" % record["turn"]),
              "w") as f:
        json.dump(stored, f, indent=2, sort_keys=True)


def _list_backups(fork):
    out_dir = os.path.join(_runs_dir(), "backups")
    found = []
    if not os.path.isdir(out_dir):
        return found
    for name in os.listdir(out_dir):
        if not name.startswith(fork + "-turn-"):
            continue
        if not name.endswith("-pre.sqlite"):
            continue
        try:
            turn = int(name[len(fork + "-turn-"):-len("-pre.sqlite")])
        except ValueError:
            continue
        found.append((turn, os.path.join(out_dir, name)))
    found.sort()
    return found


def run_queue(db_path):
    """List proposals and files waiting, in the order they must be
    applied. Returns the list of (turn, proposal_id, status)."""
    conn = db.connect(db_path)
    try:
        fork = _fork_slug(conn, db_path)
    finally:
        conn.close()
    registry = proposals_mod.load_registry()
    waiting = [e for e in registry.values()
               if e.get("status") in ("reviewed", "held")]
    waiting.sort(key=lambda e: (e.get("turn") or 0,
                                e.get("proposal_id") or ""))
    # Newest revision per turn wins; older ones are superseded.
    newest = {}
    for e in waiting:
        turn = e.get("turn")
        path = os.path.join(proposals_mod._proposal_dir(
            e["proposal_id"]), "proposal.txt")
        mtime = os.path.getmtime(path) if os.path.exists(path) else 0
        if turn not in newest or mtime > newest[turn][0]:
            newest[turn] = (mtime, e["proposal_id"])
    rows = []
    for e in waiting:
        turn = e.get("turn")
        current = newest.get(turn, (0, None))[1] == e["proposal_id"]
        rows.append({
            "turn": turn,
            "proposal_id": e["proposal_id"],
            "state_version": e.get("state_version"),
            "status": e.get("status"),
            "current_revision": current,
            "path": os.path.join(proposals_mod._proposal_dir(
                e["proposal_id"]), "proposal.txt"),
        })
    queue_dir = os.path.join(_runs_dir(), fork, "queue")
    files = []
    if os.path.isdir(queue_dir):
        files = sorted(f for f in os.listdir(queue_dir)
                       if f.endswith(".txt"))
    return {"fork": fork, "proposals": rows, "queue_files": files}


def run_rollback(db_path, yes=False):
    """Restore the most recent pre-apply backup after confirmation.
    Verifies the restored state hash against the sidecar and resets
    that turn's registry entry from `applied` back to `reviewed`
    so the same block can be re-applied. Returns the restore record.
    """
    conn = db.connect(db_path)
    try:
        fork = _fork_slug(conn, db_path)
    finally:
        conn.close()
    backups = _list_backups(fork)
    if not backups:
        raise TurnError("no pre-apply backup found for %s" % fork)
    turn, backup_path = backups[-1]
    sidecar_path = backup_path + ".json"
    sidecar = {}
    if os.path.exists(sidecar_path):
        with open(sidecar_path) as f:
            sidecar = json.load(f)
    if not yes and not _confirm(
            "Restore %s to its pre-Turn-%d state?" % (fork, turn)):
        raise TurnError("rollback declined; nothing restored")
    conn = db.connect(db_path)
    conn.close()
    shutil.copyfile(backup_path, db_path)
    conn = db.connect(db_path)
    try:
        restored_hash = db.state_hash(conn)
        restored_tick = db.get_tick(conn)
    finally:
        conn.close()
    expected_hash = sidecar.get("state_hash")
    if expected_hash and restored_hash != expected_hash:
        raise TurnError(
            "rollback restored the file but the state hash does not "
            "match the sidecar (%s != %s); investigate before "
            "continuing" % (restored_hash, expected_hash))
    # Reset the registry entry so the same block can be re-applied.
    registry = proposals_mod.load_registry()
    pid = sidecar.get("proposal_id")
    targets = []
    if pid and pid in registry:
        targets = [pid]
    else:
        targets = [p for p, e in registry.items()
                   if e.get("turn") == turn
                   and e.get("status") == "applied"]
    for p in targets:
        entry = registry[p]
        entry["status"] = "reviewed"
        entry.pop("applied_at", None)
        registry[p] = entry
        applied_path = os.path.join(
            proposals_mod._proposal_dir(p), "applied.json")
        if os.path.exists(applied_path):
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            os.rename(applied_path,
                      applied_path + ".rolled-back-" + stamp)
    if targets:
        proposals_mod.save_registry(registry)
    return {
        "fork": fork,
        "turn": turn,
        "backup_path": backup_path,
        "state_hash": restored_hash,
        "tick": restored_tick,
        "registry_reset": targets,
    }


def cmd_turn(args):
    """CLI entry point for `python3 -m src.run turn`."""
    if args.queue:
        result = run_queue(args.db)
        print("queue for %s:" % result["fork"])
        if not result["proposals"] and not result["queue_files"]:
            print("  (empty)")
        for row in result["proposals"]:
            tag = "" if row["current_revision"] else " (superseded)"
            print("  Turn %s %s %s%s — %s"
                  % (row["turn"], row["proposal_id"], row["status"],
                     tag, row["path"]))
        for name in result["queue_files"]:
            print("  local file: %s" % name)
        return
    if args.rollback:
        try:
            result = run_rollback(args.db, yes=args.yes)
        except TurnError as exc:
            print("rollback refused: %s" % exc)
            sys.exit(1)
        print("restored %s to its pre-Turn-%d state "
              "(state hash %s, tick %d)"
              % (result["fork"], result["turn"],
                 result["state_hash"], result["tick"]))
        if result["registry_reset"]:
            print("registry reset to reviewed: %s"
                  % ", ".join(result["registry_reset"]))
        return
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
        name = os.path.basename(args.file)
    elif args.stdin:
        text = sys.stdin.read()
        name = "stdin"
    else:
        print("turn needs --file <block.txt> or --stdin "
              "(or --queue / --rollback)")
        sys.exit(1)
    try:
        record = run_turn(args.db, text, name=name, yes=args.yes,
                          dry_run=args.dry_run)
    except TurnError as exc:
        print("turn refused: %s" % exc)
        sys.exit(1)
    print(record["review"])
    print("tier: %s" % record["tier"])
    if record["dry_run"]:
        print("dry run only — nothing written.")
        return
    print("applied Turn %d %s (%d change(s)); "
          "tick %d -> %d; %d events added"
          % (record["turn"], record["state_version"],
             len(record["applied"]), record["tick_before"],
             record["tick_after"],
             record["events_after"] - record["events_before"]))
    print("new tick: %d" % record["tick_after"])
    print("handshake: %s" % record["handshake"]["path"])
    print("backup: %s" % record["backup_path"])
    print()
    print(record["handshake"]["text"])
