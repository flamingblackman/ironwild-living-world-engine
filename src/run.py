"""CLI for the Living World Engine (Phase 1).

  python3 -m src.run seed --seed seed/fork-a.json --db state/ironwild-fork-a.sqlite
  python3 -m src.run tick --db state/ironwild-fork-a.sqlite --n 30
  python3 -m src.run fast-forward --db state/ironwild-fork-a.sqlite --n 400
  python3 -m src.run render --db state/ironwild-fork-a.sqlite --out runs/<id>/world-view.html
  python3 -m src.run verify --db state/ironwild-fork-a.sqlite
"""

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import db, events, render, seed as seed_mod, tick as tick_mod


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

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
