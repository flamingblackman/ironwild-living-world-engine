"""CLI for the Living World Engine (Phase 1).

  python3 -m src.run seed --seed seed/fork-a.json --db state/ironwild-fork-a.sqlite
  python3 -m src.run tick --db state/ironwild-fork-a.sqlite --n 30
  python3 -m src.run fast-forward --db state/ironwild-fork-a.sqlite --n 400
  python3 -m src.run render --db state/ironwild-fork-a.sqlite --out runs/<id>/world-view.html
  python3 -m src.run verify --db state/ironwild-fork-a.sqlite
"""

import argparse
import datetime
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import (apply_adapter as apply_adapter_mod,
                 auto_apply as auto_apply_mod,
                 auto_tick as auto_tick_mod,
                 checkpoint as checkpoint_mod,
                 db, drive_io, events, handshake as handshake_mod,
                 proposals as proposals_mod, render,
                 seed as seed_mod, session as session_mod, sweep as sweep_mod,
                 tick as tick_mod, turn as turn_mod)


def _open(db_path):
    return db.connect(db_path)


def cmd_seed(args):
    if os.path.exists(args.db):
        os.remove(args.db)
    with open(args.seed) as f:
        seed_data = json.load(f)
    conn = _open(args.db)
    db.init_schema(conn)
    seed_mod.load_seed(conn, seed_data)
    conn.close()
    print(f"seeded {args.db} from {args.seed} "
          f"({seed_data['fork_label']}, source {seed_data['source_snapshot']})")


def cmd_tick(args):
    conn = _open(args.db)
    rng = random.Random(int(db.get_meta(conn, "rng_seed", 0)))
    try:
        final = tick_mod.run_ticks(conn, args.n, rng=rng)
    except tick_mod.EngineHalt as exc:
        print(f"STOP — the engine halted at tick "
              f"{db.get_tick(conn)} and asks Lore: {exc}")
        conn.close()
        sys.exit(2)
    problems = tick_mod.verify_invariants(conn)
    conn.close()
    print(f"tick {final} reached")
    if problems:
        print("INVARIANT VIOLATIONS:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("invariants clean")


def cmd_render(args):
    conn = _open(args.db)
    if args.format == "json":
        carried = None
        if args.carried:
            with open(args.carried, encoding="utf-8") as f:
                carried = json.load(f)
        out = args.out
        if not out:
            # The stable Companion export path: runs/<world>/world-view.json
            out = os.path.join(_runs_dir(),
                               db.get_meta(conn, "world_id", "world"),
                               "world-view.json")
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        render.render_world_view_json(conn, out, carried=carried)
        conn.close()
        print(f"world view (json) written to {out}")
        return
    if not args.out:
        print("render --format html needs --out")
        conn.close()
        sys.exit(1)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    render.render_world_view(conn, args.out)
    conn.close()
    print(f"world view written to {args.out}")


def cmd_verify(args):
    conn = _open(args.db)
    ok, bad = events.verify_chain(conn)
    problems = tick_mod.verify_invariants(conn)
    triggers = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'trigger' "
        "AND tbl_name = 'events'").fetchall()
    conn.close()
    print(f"event hash chain: {'OK' if ok else f'BROKEN at event {bad}'}")
    print(f"append-only triggers: {len(triggers)} present")
    print(f"invariants: {'clean' if not problems else problems}")
    if not ok or problems or len(triggers) < 2:
        sys.exit(1)


def _save_review(out_dir, record):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "review.json"), "w") as f:
        json.dump(record, f, indent=2, sort_keys=True)


def _runs_dir():
    """The runs tree. Scopable for tests (IRONWILD_RUNS_DIR) so the
    1A acceptance test's sweep records never land in the live
    runs/sweeps/ tree."""
    return os.environ.get("IRONWILD_RUNS_DIR", "runs")


def _write_sweep_records(out_dir, result, review_record):
    """The standard sweep records the checkpoint's sweep-source check
    reads: applied.json + carried.json + review.json under
    runs/sweeps/turn-<n>/. Used by both the manual sweep path and the
    proposal apply path, so a proposal apply is indistinguishable
    from a manual one in the audit trail."""
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "applied.json"), "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    with open(os.path.join(out_dir, "carried.json"), "w") as f:
        json.dump(result["carried"], f, indent=2, sort_keys=True)
    _save_review(out_dir, review_record)


def _load_proposal_config():
    path = os.path.join("runs", "proposals", "config.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def cmd_intake(args):
    """Poll the Drive inbox for V2 proposals (Stage 1A).

    Registers + validates each new file, writes its review, updates
    the registry. Never touches the DB — unless --auto-apply is set,
    in which case each NEW reviewed proposal that passes the
    0-change eligibility check is applied under Bryan's standing
    approval, ticked 3, and handed a next handshake in the outbox
    (see attempt_auto_apply). Anything not eligible is held for
    Bryan and its review printed, as before. A rejected proposal is
    a recorded outcome, not a crash; a Drive failure exits 1.
    """
    config = _load_proposal_config()
    inbox = args.inbox or config.get("inbox_folder_id")
    if not inbox:
        print("intake needs --inbox (or runs/proposals/config.json)")
        sys.exit(1)
    conn = _open(args.db)
    try:
        new_entries, skipped = proposals_mod.intake_folder(inbox, conn)
    except drive_io.DriveError as exc:
        print(f"intake halted (Drive): {exc}")
        conn.close()
        sys.exit(1)
    for e in new_entries:
        print(f"{e['proposal_id']}: {e['status']} "
              f"(turn {e.get('turn')}, {e.get('state_version')})")
        if e["status"] == "rejected":
            print(f"  rejected: {e.get('error')}")
        elif args.auto_apply and e["status"] == "reviewed":
            try:
                record = attempt_auto_apply(
                    e["proposal_id"], conn,
                    flag_path=session_mod.FLAG_PATH,
                    outbox=args.outbox)
            except auto_apply_mod.LoreCall as exc:
                print(f"LORE-CALL {exc.pid}: "
                      + "; ".join("%s: %s" % (f["code"], f["detail"])
                                 for f in exc.flags))
                print(f"  block: {os.path.join(proposals_mod._proposal_dir(exc.pid), 'proposal.txt')}")
                continue
            except sweep_mod.SweepError as exc:
                print(f"HELD {e['proposal_id']}: {exc}")
                continue
            except drive_io.DriveError as exc:
                print(f"AUTO-APPLY FAILED {e['proposal_id']} "
                      f"(Drive): {exc}")
                continue
            hs = record["handshake"] or {}
            print(f"AUTO-APPLIED {record['proposal_id']} turn "
                  f"{record['turn']} {record['state_version']}: "
                  f"tick {record['tick_before']} -> "
                  f"{record['tick_after']}, "
                  f"{record['events_after']} events, handshake "
                  f"{hs.get('path')} (Drive {hs.get('drive_file_id')})")
    print(f"intake done: {len(new_entries)} new, {skipped} already "
          f"registered")
    conn.close()


def cmd_apply_proposal(args):
    """Apply a reviewed proposal by ID, with approval binding
    (Stage 1A). The block applied is the STORED (reviewed) content,
    hash-verified against the Drive file at apply time. Writes the
    standard sweep records so the checkpoint audit sees it like any
    other apply."""
    conn = _open(args.db)
    resource_changes = []
    for spec in args.resource_change:
        try:
            holder, holder_kind, resource, old, new = spec.split(":")
            resource_changes.append({
                "holder": holder, "holder_kind": holder_kind,
                "resource": resource, "old": int(old), "new": int(new)})
        except ValueError:
            print(f"bad --resource-change (want "
                  f"holder:kind:resource:old:new): {spec}")
            conn.close()
            sys.exit(1)
    try:
        result = proposals_mod.apply_proposal(
            args.proposal_id, conn, args.approved_by,
            flag_path=args.flag or session_mod.FLAG_PATH,
            resource_changes=resource_changes,
            lore_approval=args.lore_approval)
    except sweep_mod.SweepError as exc:
        print(f"apply refused: {exc}")
        conn.close()
        sys.exit(1)
    registry = proposals_mod.load_registry()
    entry = registry[args.proposal_id]
    out_dir = os.path.join(_runs_dir(), "sweeps",
                           "turn-%d" % result["turn"])
    review_record = {
        "ok": True, "dry_run": False, "turn": result["turn"],
        "state_version": entry["state_version"],
        "findings": entry["findings"], "changes": result["applied"],
        "review": entry["review"],
        "proposal_id": args.proposal_id,
        "proposal_binding": result["proposal_binding"],
    }
    if args.lore_approval:
        # A flagged proposal Lore approved: record it as
        # Lore-approved, not as a pure auto-apply, so the audit trail
        # shows who cleared it.
        review_record["lore_approved"] = True
    _write_sweep_records(out_dir, result, review_record)
    if args.lore_approval:
        proposals_mod.record_lore_approval(args.proposal_id,
                                          args.lore_approval)
        print(f"Lore-approved apply (submission {args.lore_approval}); "
              f"record written to runs/proposals/{args.proposal_id}/"
              f"lore-approved.json")
    print(f"applied {len(result['applied'])} change(s) from "
          f"{args.proposal_id}, approved by "
          f"{'Lore' if args.lore_approval else args.approved_by}; "
          f"record written to {out_dir}/")
    conn.close()


def _load_last_carried(conn):
    """The carried record of the last approved sweep
    (runs/sweeps/turn-<n>/carried.json), or None when no prior sweep
    exists or its record is missing. The narrative-flag comparison
    in flag_narrative_changes needs it; a missing baseline is itself
    a flag (NO_BASELINE)."""
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


def _write_auto_applied(pid, record):
    """The auto-apply log: proposal ID + hash binding, what the
    standing approval authorized, and what happened after the apply
    (ticks, handshake). Lives next to applied.json in the proposal
    dir, so the audit trail shows the auto path separately from a
    per-proposal tap."""
    out_dir = proposals_mod._proposal_dir(pid)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "auto-applied.json"), "w") as f:
        json.dump(record, f, indent=2, sort_keys=True)


def attempt_auto_apply(pid, conn, flag_path=None, ticks=3, outbox=None):
    """Apply one reviewed proposal under the standing 0-change
    approval, tick, and generate + upload the next handshake.

    Eligibility is re-checked fresh against the live DB (the intake
    review is stale the moment anything ticks). Raises SweepError on
    any refusal — nothing is applied. The eligibility, fork, hash,
    and session checks all run before the first write; once the
    apply commits, a later failure (tick halt, invariant problem,
    handshake upload failure) leaves the apply standing and the
    record says so loudly — the handshake is not generated from a
    halted or suspect state. Returns the auto-apply record.
    """
    flag_path = flag_path or session_mod.FLAG_PATH
    registry = proposals_mod.load_registry()
    entry = registry.get(pid)
    if entry is None:
        raise sweep_mod.SweepError("unknown proposal %s: no such "
                                   "proposal in the registry" % pid)
    if entry["status"] != "reviewed":
        raise sweep_mod.SweepError("proposal %s is %s, not reviewed; "
                                   "only a reviewed proposal can be "
                                   "applied" % (pid, entry["status"]))
    with open(os.path.join(proposals_mod._proposal_dir(pid),
                           "proposal.txt"), encoding="utf-8") as f:
        stored = f.read()
    parsed = sweep_mod.parse_state_block(stored)
    row = conn.execute(
        "SELECT value FROM meta WHERE key = 'world_id'").fetchone()
    world_id = row["value"] if row else "ironwild-fork-a"
    findings = (sweep_mod.validate(parsed, conn)
                + proposals_mod.validate_fork(parsed, world_id))
    changes = sweep_mod.diff(parsed, conn)
    eligible, reasons = auto_apply_mod.check_eligible(
        parsed, findings, changes, conn, flag_path)
    last_carried = _load_last_carried(conn)
    flags = auto_apply_mod.flag_narrative_changes(
        parsed, last_carried, conn)
    if eligible and not flags:
        pass  # pure carry-over; fall through to the apply below
    elif flags and not {r["code"] for r in reasons} - {
            auto_apply_mod.REASON_PENDING_DECISION}:
        # 0-change, but the block carries a narrative change the
        # sweep cannot validate (guard (a)–(c)). Lore decides
        # APPROVE or ESCALATE — the Engine does not auto-apply it.
        raise auto_apply_mod.LoreCall(pid, flags)
    else:
        why = "; ".join(r["message"] for r in reasons)
        if flags:
            why += ("; narrative flags: "
                    + "; ".join("%s: %s" % (f["code"], f["detail"])
                               for f in flags))
        raise sweep_mod.SweepError(
            "proposal %s is not eligible for auto-apply: %s" % (pid, why))
    tick_before = db.get_tick(conn)
    events_before = conn.execute(
        "SELECT COUNT(*) FROM events").fetchone()[0]
    result = proposals_mod.apply_proposal(pid, conn, "Bryan",
                                          flag_path=flag_path)
    # The standard sweep records, so the checkpoint sees an
    # auto-apply exactly like a manual one.
    out_dir = os.path.join(_runs_dir(), "sweeps",
                           "turn-%d" % result["turn"])
    review_record = {
        "ok": True, "dry_run": False, "turn": result["turn"],
        "state_version": entry["state_version"],
        "findings": entry["findings"], "changes": result["applied"],
        "review": entry["review"],
        "proposal_id": pid,
        "proposal_binding": result["proposal_binding"],
        "auto_applied": True,
    }
    _write_sweep_records(out_dir, result, review_record)
    tick_after = tick_before
    tick_halted = None
    try:
        tick_after = tick_mod.run_ticks(conn, ticks)
    except tick_mod.EngineHalt as exc:
        tick_after = db.get_tick(conn)
        tick_halted = str(exc)
    problems = tick_mod.verify_invariants(conn)
    chain_ok, _ = events.verify_chain(conn)
    record = {
        "proposal_id": pid,
        "content_hash": entry["content_hash"],
        "drive_file_id": entry["drive_file_id"],
        "turn": result["turn"],
        "state_version": entry["state_version"],
        "approved_by": "Bryan",
        "approval": auto_apply_mod.STANDING_APPROVAL,
        "applied_at": result["proposal_binding"]["applied_at"],
        "tick_before": tick_before,
        "tick_after": tick_after,
        "events_before": events_before,
        "events_after": conn.execute(
            "SELECT COUNT(*) FROM events").fetchone()[0],
        "state_hash": db.state_hash(conn),
        "hash_chain_ok": chain_ok,
        "invariant_problems": problems,
        "tick_halted": tick_halted,
        "handshake": None,
    }
    if tick_halted or problems or not chain_ok:
        _write_auto_applied(pid, record)
        raise sweep_mod.SweepError(
            "auto-apply of %s applied (0 changes) but the follow-up "
            "failed — tick halted: %s; invariant problems: %s; hash "
            "chain ok: %s. No handshake generated; report to the hub."
            % (pid, tick_halted, problems, chain_ok))
    hs = handshake_mod.generate_handshake(
        conn, result["carried"], since_tick=tick_before)
    next_turn = result["turn"] + 1
    hs_path = os.path.join(_runs_dir(), "handshakes",
                           "turn-%d.md" % next_turn)
    os.makedirs(os.path.dirname(hs_path) or ".", exist_ok=True)
    with open(hs_path, "w") as f:
        f.write(hs["text"] + "\n")
    with open(hs_path + ".json", "w") as f:
        json.dump(hs["meta"], f, indent=2, sort_keys=True)
    outbox_id = outbox or _load_proposal_config().get("outbox_folder_id")
    hs_file_id = None
    if outbox_id:
        try:
            hs_file_id = drive_io.upload_text(
                outbox_id, os.path.basename(hs_path), hs["text"] + "\n",
                hs_path)
        except drive_io.DriveError as exc:
            record["handshake"] = {"path": hs_path,
                                   "drive_file_id": None,
                                   "upload_error": str(exc)}
            _write_auto_applied(pid, record)
            raise sweep_mod.SweepError(
                "auto-apply of %s applied and ticked, but the handshake "
                "upload failed (Drive): %s. Handshake is on disk at %s; "
                "report to the hub." % (pid, exc, hs_path))
    record["handshake"] = {
        "path": hs_path,
        "drive_file_id": hs_file_id,
        "words": hs["meta"]["words"],
        "turn": next_turn,
        "state_version": hs["meta"]["state_version"],
    }
    _write_auto_applied(pid, record)
    registry = proposals_mod.load_registry()
    entry = registry[pid]
    entry["auto_applied"] = True
    entry["auto_apply_approval"] = auto_apply_mod.STANDING_APPROVAL
    proposals_mod.save_registry(registry)
    return record


def cmd_sweep(args):
    """Parse + validate a Turn state block (read-only), and apply it
    only with --apply plus --approved-by (Bryan's tap in the hub).

    Every proposal is recorded under runs/sweeps/, so the every-3-turns
    checkpoint (the formal acceptance test) can count schema obedience:
    a dry run or an apply writes turn-<n>/review.json; a block that
    fails parsing writes rejected/<timestamp>.json.
    """
    with open(args.block) as f:
        text = f.read()
    try:
        parsed = sweep_mod.parse_state_block(text)
    except sweep_mod.SweepError as exc:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        out_dir = os.path.join(_runs_dir(), "sweeps", "rejected")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "rejected-%s.json" % stamp),
                  "w") as f:
            json.dump({"ok": False, "stage": "parse",
                       "error": str(exc)}, f, indent=2, sort_keys=True)
        print(f"sweep refused at parse: {exc}")
        sys.exit(1)
    conn = _open(args.db)
    findings = sweep_mod.validate(parsed, conn)
    resource_changes = []
    for spec in args.resource_change:
        try:
            holder, holder_kind, resource, old, new = spec.split(":")
            rc = {"holder": holder, "holder_kind": holder_kind,
                  "resource": resource, "old": int(old), "new": int(new)}
        except ValueError:
            print(f"bad --resource-change (want "
                  f"holder:kind:resource:old:new): {spec}")
            conn.close()
            sys.exit(1)
        resource_changes.append(rc)
    try:
        changes = sweep_mod.diff(parsed, conn, resource_changes)
    except sweep_mod.SweepError as exc:
        print(f"apply refused: {exc}")
        conn.close()
        sys.exit(1)
    review = sweep_mod.summarize(parsed, findings, changes, conn=conn)
    print(review)
    errors = [f for f in findings if f["level"] == "error"]
    out_dir = os.path.join(_runs_dir(), "sweeps",
                           "turn-%d" % parsed["turn"])
    record = {"ok": not errors, "dry_run": not args.apply,
              "turn": parsed["turn"],
              "state_version": parsed["state_version"],
              "findings": findings, "changes": changes,
              "review": review}
    if not args.apply:
        _save_review(out_dir, record)
        print("dry run only — nothing applied. Re-run with --apply "
              "--approved-by NAME to apply after Bryan's approval.")
        conn.close()
        sys.exit(0)
    if errors:
        _save_review(out_dir, record)
        print("apply refused: validation errors above.")
        conn.close()
        sys.exit(1)
    db.init_schema(conn)  # migrate: applied_turns + prev_hash index
    try:
        # The shared gate: turn order + duplicate. Applies to the
        # manual path too, including a human approval.
        apply_adapter_mod.check_apply_gate(
            parsed, conn, proposals_mod.content_hash(text))
        result = sweep_mod.apply_sweep(
            parsed, conn, args.approved_by,
            flag_path=args.flag or session_mod.FLAG_PATH,
            resource_changes=resource_changes,
            content_hash=proposals_mod.content_hash(text),
            proposal_id=None, source="manual-sweep")
    except sweep_mod.SweepError as exc:
        record["ok"] = False
        record["error"] = str(exc)
        _save_review(out_dir, record)
        print(f"apply refused: {exc}")
        conn.close()
        sys.exit(1)
    record["dry_run"] = False
    _write_sweep_records(out_dir, result, record)
    print(f"applied {len(result['applied'])} change(s), "
          f"approved by {args.approved_by}; "
          f"record written to {out_dir}/")
    conn.close()


def cmd_handshake(args):
    conn = _open(args.db)
    with open(args.carried) as f:
        carried = json.load(f)
    result = handshake_mod.generate_handshake(
        conn, carried, since_tick=args.since_tick)
    conn.close()
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        f.write(result["text"] + "\n")
    with open(args.out + ".json", "w") as f:
        json.dump(result["meta"], f, indent=2, sort_keys=True)
    print(f"handshake written to {args.out} "
          f"({result['meta']['words']} words, "
          f"{result['meta']['rumors']} rumor(s), "
          f"{len(result['meta']['clocks_about_to_fire'])} clock(s) "
          f"about to fire)")
    outbox = args.outbox or _load_proposal_config().get("outbox_folder_id")
    if outbox:
        try:
            file_id = drive_io.upload_text(
                outbox, os.path.basename(args.out), result["text"] + "\n",
                args.out)
        except drive_io.DriveError as exc:
            print(f"handshake upload halted (Drive): {exc}")
            sys.exit(1)
        print(f"handshake uploaded to outbox (Drive file {file_id})")


def cmd_checkpoint(args):
    text, drift = checkpoint_mod.audit(
        args.db, args.carried, args.out,
        sweeps_dir=args.sweeps or None, seed_path=args.seed or None)
    print(text)
    print(f"checkpoint written to {args.out} ({drift} drift line(s))")


def cmd_auto_tick(args):
    result = auto_tick_mod.run_auto_tick(
        args.db, today=args.date,
        flag_path=args.flag or session_mod.FLAG_PATH)
    print(f"auto tick: {result['outcome']} (tick {result['tick']}, "
          f"events {result['events_before']}->{result['events_after']})")
    if result.get("reason"):
        print(f"  {result['reason']}")
    if result["outcome"] == "halted":
        sys.exit(2)
    if result["outcome"] == "ticked" and result.get("problems"):
        print("INVARIANT VIOLATIONS:")
        for p in result["problems"]:
            print(f"  - {p}")
        sys.exit(1)


def cmd_migrate(args):
    """Apply the schema (idempotent) to an existing DB: creates the
    applied_turns table and the UNIQUE prev_hash index if missing.
    Prints the state hash before and after — the migration alone
    must not change it."""
    conn = _open(args.db)
    before = db.state_hash(conn)
    db.init_schema(conn)
    after = db.state_hash(conn)
    rows = conn.execute(
        "SELECT COUNT(*) FROM applied_turns").fetchone()[0]
    index = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'index' "
        "AND name = 'idx_events_prev_hash'").fetchone()[0]
    conn.close()
    print(f"migrated {args.db}: applied_turns rows={rows}, "
          f"prev_hash index={'present' if index else 'MISSING'}, "
          f"state hash {before[:12]} -> {after[:12]}"
          + (" (unchanged)" if before == after else " (CHANGED!)"))


def main():
    parser = argparse.ArgumentParser(description="Living World Engine")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("seed")
    p.add_argument("--seed", required=True)
    p.add_argument("--db", required=True)
    p.set_defaults(fn=cmd_seed)

    p = sub.add_parser("tick")
    p.add_argument("--db", required=True)
    p.add_argument("--n", type=int, default=1)
    p.set_defaults(fn=cmd_tick)

    p = sub.add_parser("fast-forward")
    p.add_argument("--db", required=True)
    p.add_argument("--n", type=int, required=True)
    p.set_defaults(fn=cmd_tick)

    p = sub.add_parser("render")
    p.add_argument("--db", required=True)
    p.add_argument("--out", required=False, default=None)
    p.add_argument("--format", choices=["html", "json"], default="html")
    p.add_argument("--carried", required=False, default=None)
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("verify")
    p.add_argument("--db", required=True)
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("sweep")
    p.add_argument("--db", required=True)
    p.add_argument("--block", required=True)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--approved-by", default=None)
    p.add_argument("--flag", default=None)
    # Explicitly approved resource moves the V2 block cannot express
    # (it has no Resources field), one per flag:
    # holder:holder_kind:resource:old:new — e.g.
    # ironwild_legion:faction:Salvage:12:11
    p.add_argument("--resource-change", action="append", default=[])
    p.set_defaults(fn=cmd_sweep)

    p = sub.add_parser("handshake")
    p.add_argument("--db", required=True)
    p.add_argument("--carried", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--since-tick", type=int, default=0)
    p.add_argument("--outbox", default=None,
                   help="Drive folder id to upload the handshake to "
                        "(defaults to runs/proposals/config.json)")
    p.set_defaults(fn=cmd_handshake)

    p = sub.add_parser("intake")
    p.add_argument("--db", required=True)
    p.add_argument("--inbox", default=None,
                   help="Drive folder id to poll for proposals "
                        "(defaults to runs/proposals/config.json)")
    p.add_argument("--auto-apply", action="store_true",
                   help="auto-apply eligible 0-change proposals under "
                        "Bryan's standing approval (apply, tick 3, "
                        "next handshake to the outbox); anything not "
                        "eligible is held for Bryan")
    p.add_argument("--outbox", default=None,
                   help="Drive folder id for the auto-apply handshake "
                        "upload (defaults to runs/proposals/config.json)")
    p.set_defaults(fn=cmd_intake)

    p = sub.add_parser("apply-proposal")
    p.add_argument("--db", required=True)
    p.add_argument("--proposal-id", required=True)
    p.add_argument("--approved-by", default=None)
    p.add_argument("--flag", default=None)
    p.add_argument("--resource-change", action="append", default=[])
    p.add_argument("--lore-approval", default=None,
                   help="Lore's APPROVE submission id for a flagged "
                        "proposal (records the apply as Lore-approved, "
                        "not a pure auto-apply)")
    p.set_defaults(fn=cmd_apply_proposal)

    p = sub.add_parser("checkpoint")
    p.add_argument("--db", required=True)
    p.add_argument("--carried", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--sweeps", default="runs/sweeps")
    p.add_argument("--seed", default=None)
    p.set_defaults(fn=cmd_checkpoint)

    p = sub.add_parser("turn")
    p.add_argument("--db", required=True)
    p.add_argument("--file", default=None,
                   help="local [TURN STATE] block file to apply")
    p.add_argument("--stdin", action="store_true",
                   help="read the block from stdin instead of --file")
    p.add_argument("--yes", action="store_true",
                   help="confirm a REVIEW tier without prompting")
    p.add_argument("--dry-run", action="store_true",
                   help="parse, validate and tier only; write nothing")
    p.add_argument("--queue", action="store_true",
                   help="list proposals and files waiting, in order")
    p.add_argument("--rollback", action="store_true",
                   help="restore the most recent pre-apply backup")
    p.set_defaults(fn=turn_mod.cmd_turn)

    p = sub.add_parser("migrate")
    p.add_argument("--db", required=True)
    p.set_defaults(fn=cmd_migrate)

    p = sub.add_parser("auto-tick")
    p.add_argument("--db", required=True)
    p.add_argument("--date", default=None)
    p.add_argument("--flag", default=None)
    p.set_defaults(fn=cmd_auto_tick)

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
