# Living World Engine — Ironwild

The machine, not the story. A deterministic tick engine that runs a forked
Ironwild world off NPC and player actions, with the state database as the
single source of truth and an append-only event log.

**Status (2026-11-21):** Built and accepted on v1.3, rerun on v1.4 and
v1.5. 51 tests pass (14 fixture + 37 Fork A). v1.5 acceptance checks
PASS: 30-tick run (356 events, 54 rests) and 400-tick fast-forward
(4,674 events, 785 rests vs 1,106 in v1.3, legacy once at tick 365,
Era 2 unnamed), 3 territory controller flips proven on real seed data.
The v1.5 combined fix works for its stated goal: Dream Share fires 225
times in 400 ticks (v1.4: 0) and restores 224 Bond, all five Engines end
at Bond 5, Pack Merge recurs (55 vs 4). Honest consequence: the fix moved
the starvation to the Legion — its Feed ends at 0, trade collapses
(28 vs 645), feed_engine halves (304 vs 556), Instinct fires 272 times
(v1.4: 0), rests rise to 785, and the Pack floods to 698 Feed. That is a
seed-economy question for Lore/Bryan, not an engine bug. Phase 2 stays on
hold until Bryan approves the v1.5 rerun in the hub. See
`phase-1-plan.md` sections 10 and 14.

**How this was built:** I designed the build as separate workstreams on
Muse, an AI agent platform: specialized agents with defined roles (Lore
guards canon and writes the seed, Engine builds and tests, Career handles
positioning), with acceptance checks and hub reporting between them. I
directed the work and verified the output against the checks. Ironwild is
an original world, inspired by Zoids and Gaogaigar, not franchise IP.

## v1.5 engine work (2026-11-21)

Seed v1.5 (Bryan's call, combined fix options 1 + 3): hunt Feed goes to
the Pack, and Dream Share is a scored action, not a rest hook. Engine
changes: `conditions.py` gains an `any_bond` leaf ("an Engine's Bond is
below 5"); `targets.py` gains a `lowest_bond_engine` selector (lowest
Bond, ties to Sledge); the adapter emits Dream Share as a machine action
(25 machine actions, no hook) and routes hunt Feed to the pack holder;
the post-rest hook is retired and the Bond guard now allows increases
only from the dream_share action. One render bug exposed by the fix:
`render.py` crashed on `bond_add` ops with no pilot key — fixed, with a
test. Instinct hunts still feed the pilot's faction per the plan's rule
(Sledge's Instinct hunts gave the Legion 122 Feed in 400 ticks); the seed
changed the hunt action only, so rerouting Instinct is a Lore call for
a later seed.

## Hard rules

- **Rules first, LLM never.** The tick loop is pure deterministic code. No
  LLM call ever writes state. Narration is a separate render pass over the
  finished event log, and it is optional.
- **State database is the single source of truth.** One SQLite file per
  world fork. Everything the world "is" lives there.
- **The event log is append-only.** Database triggers refuse UPDATE/DELETE
  on `events`, and every event carries a hash chain (prev_hash + event_hash)
  so tampering is detectable.
- **The engine never invents canon.** Every actor, action, trigger, and
  material effect comes from the seed. If a rule is not in the seed, the
  engine stops and asks instead of improvising.
- **The freeze is absolute.** Crown of Cold Iron stays at Turn 136,
  vFINAL.5, Krov ambush decision pending. The engine never loads, advances,
  or spends that scene. Fork A seeds from Turn 131 vFINAL only; the seed
  loader refuses any source naming Turn 136 or Krov.
- **The engine never writes to canon files.** It reads bibles, codices, and
  the registry. It writes only inside `living-world-engine/`.

## Layout

```
living-world-engine/
  phase-1-plan.md         — the approved Phase 1 plan
  README.md               — this file
  state/schema.sql        — the tables (single source of truth)
  seed/                   — Lore's seed package lands here (fork-a.json)
  src/                    — the engine (Python 3 stdlib + SQLite only)
    db.py                 — connection, schema, deterministic state hash
    events.py             — append-only log + hash chain
    conditions.py         — trigger / need clause evaluation
    resources.py          — resource moves, clamped at zero
    actions.py            — material effect ops
    scoring.py            — goal x capability x trigger scoring
    clocks.py             — clock completion
    eras.py               — era boundary + legacy rules
    tick.py               — the tick loop
    render.py             — world-view HTML from the DB
    run.py                — CLI
    seed.py               — seed loading (validates the freeze)
  tests/
    fixture_seed.json     — TEST FIXTURE, synthetic actors, NOT canon
    test_engine.py        — 14 acceptance tests
  runs/<run-id>/          — proof runs: database + world-view.html
```

## Running it

```bash
cd living-world-engine
python3 -m unittest discover -s tests -v   # the 14 tests

# A run (fixture shown; replace with seed/fork-a.json when Lore delivers):
python3 -m src.run seed --seed tests/fixture_seed.json --db runs/proof-30/fork-a.sqlite
python3 -m src.run tick --db runs/proof-30/fork-a.sqlite --n 30
python3 -m src.run verify --db runs/proof-30/fork-a.sqlite
python3 -m src.run render --db runs/proof-30/fork-a.sqlite --out runs/proof-30/world-view.html

# Fast-forward (400 ticks crosses one era boundary at tick 365):
python3 -m src.run fast-forward --db runs/proof-400/fork-a.sqlite --n 400
```

## The tick

1 tick = 1 in-world day. In fixed order: molted engines return to active;
every engine's Hunger +1; engines at their Hunger threshold hunt on
Instinct (Feed +2 to their pilot, Hunger set to 4); every active NPC scores
its legal actions and executes the best; every active engine that did not go
Instinct does the same (Bond 0 with no legal action logs `refuse_to_move` —
a Bond 0 Engine will not move); clock completions fire; era boundaries fire
legacy rules once; snapshot every 10 ticks.

Scoring: an action is legal when the actor's kind matches, the actor holds
its capability, every trigger clause holds, and a goal tag matches. Score =
weight (Lore-set) + 1 per satisfied need clause. Ties break by the run's
seeded RNG. The event row records the winner's score and the runner-up, so
any tick can be audited.

## The seed (what Lore supplies)

One JSON file: world id, fork label, source snapshot, RNG seed, era length,
legacy rules, factions, locations, NPCs, engines, bonds, resources, clocks,
and the action catalog. Each action carries its goal tags, capability,
weight, trigger clauses, need clauses, and material effect ops. Anything
not in the catalog cannot happen. See `tests/fixture_seed.json` for the
exact shape (synthetic actors — do not mistake it for canon).

## The future dynamic map (Phase 4, not Phase 1)

Bryan's requirement: the world view map must eventually become dynamic, so
a wiped-out continent, a flipped territory, a fallen den, or a destroyed
region is visible on the map. Phase 1 does not build that map. What Phase 1
does is record every location and territory change as state — in the
`locations` table (controller + status) and in the event log
(`location_set` / `status_set` effects) — so a later dynamic map can render
them. The fixture proof runs already demonstrate it: the raid flips the Old
Wreck to the Breakers, and the completed Muster clock flips the Rust Flats
to the Concord.

## Known Phase 1 limitations (honest list)

- **The fixture catalog is minimal.** After both fixture clocks complete,
  NPCs mostly scout (weight 5, always legal) and the high-Bond engine
  molts nearly every tick. That is a catalog problem, not an engine problem:
  the world is only as interesting as its action catalog. The real Lore
  seed has now landed (`seed/fork-a.json`) and the engine runs it — the
  live issue is the evacuate halt at tick 1, not fixture pacing.
- **No per-action cooldowns.** The engine has no cooldown mechanic; pacing
  is the catalog's job via triggers and weights.
- **Pack Merge burns the top two Bonds at the location.** The
  `pack_merge_burn` effect picks the two highest-Bond engines present and
  burns each −2. A named-pair merge is a Phase 2 refinement.
- **No narration layer, no Companion integration.** The world view is a
  static HTML page generated from the DB. That was the approved Phase 1
  stand-in.
- **No run resume.** A run is seeded fresh and runs to completion. Same
  seed + same seed data always reproduces the same world, verified by the
  determinism test.
