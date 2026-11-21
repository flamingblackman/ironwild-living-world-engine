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

from src import (auto_tick as auto_tick_mod, checkpoint as checkpoint_mod,
                 db, drive_io, events, handshake as handshake_mod,
                 proposals as proposals_mod, render,
                 seed as seed_mod, session as session_mod, sweep as sweep_mod,
                 tick as tick_mod)


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
    the registry. Never touches the DB. A rejected proposal is a
    recorded outcome, not a crash; a Drive failure exits 1.
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
    conn.close()
    for e in new_entries:
        print(f"{e['proposal_id']}: {e['status']} "
              f"(turn {e.get('turn')}, {e.get('state_version')})")
    print(f"intake done: {len(new_entries)} new, {skipped} already "
          f"registered")


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
            resource_changes=resource_changes)
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
    _write_sweep_records(out_dir, result, review_record)
    print(f"applied {len(result['applied'])} change(s) from "
          f"{args.proposal_id}, approved by {args.approved_by}; "
          f"record written to {out_dir}/")
    conn.close()


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
    try:
        result = sweep_mod.apply_sweep(
            parsed, conn, args.approved_by,
            flag_path=args.flag or session_mod.FLAG_PATH,
            resource_changes=resource_changes)
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
    p.add_argument("--out", required=True)
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
    p.set_defaults(fn=cmd_intake)

    p = sub.add_parser("apply-proposal")
    p.add_argument("--db", required=True)
    p.add_argument("--proposal-id", required=True)
    p.add_argument("--approved-by", default=None)
    p.add_argument("--flag", default=None)
    p.add_argument("--resource-change", action="append", default=[])
    p.set_defaults(fn=cmd_apply_proposal)

    p = sub.add_parser("checkpoint")
    p.add_argument("--db", required=True)
    p.add_argument("--carried", nargs="+", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--sweeps", default="runs/sweeps")
    p.add_argument("--seed", default=None)
    p.set_defaults(fn=cmd_checkpoint)

    p = sub.add_parser("auto-tick")
    p.add_argument("--db", required=True)
    p.add_argument("--date", default=None)
    p.add_argument("--flag", default=None)
    p.set_defaults(fn=cmd_auto_tick)

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
