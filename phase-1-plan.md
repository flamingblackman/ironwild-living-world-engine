# Living World Engine — Phase 1 Plan

**Team:** Living World Engine Team
**World:** Ironwild (test world, forked)
**Status:** PLAN — awaiting Bryan's approval in the Fiction & Worldbuilding hub chat. No engine code is built until he approves.
**Date:** 2026-11-20

## 1. What Phase 1 proves

One complete, inspectable loop: seed data in, ticks out, event log and world view out — with zero canon touched and the same seed always producing the same world.

Phase 1 is deliberately small. One forked test world, a dozen actors, 30 ticks, one fast-forward era crossing. If that loop is honest, Phase 2 earns the narration layer and the Companion app integration. If it is not, we find out on a fork, not on live canon.

## 2. Hard rules the engine obeys

- **Rules first, LLM second.** The tick loop is pure deterministic code. No LLM call ever writes state. Narration is a separate render pass over the finished event log, and it is optional.
- **State database is the single source of truth.** Everything the world "is" lives in one SQLite file. The event log is append-only: events are never updated or deleted. A correction is a new event.
- **The engine never invents canon.** Every actor, action, trigger, and material effect comes from Lore-supplied seed data. If the engine needs a rule that is not in the seed, it stops and asks instead of improvising.
- **The freeze is absolute.** Crown of Cold Iron is at Turn 136, vFINAL.5, with the Krov ambush decision pending. The engine never loads, advances, or spends that scene. Phase 1 seeds from Ironwild Turn 131 vFINAL (campaign complete), on a clearly labeled fork. No Turn 136 state enters the fork.
- **The engine never writes to canon files.** It reads the bibles, codices, and registry. It writes only inside `living-world-engine/`.
- **Open mysteries stay open.** Where the first Seed Cores came from, the Deepmaw migration, what happens to a pilot whose Engine dies — the engine never resolves these. They are not in the action catalog.

## 3. State model

One SQLite database per world fork. Schema (`state/schema.sql`):

| Table | What it holds |
|---|---|
| `meta` | key/value: world_id, fork label, source snapshot (Turn 131 vFINAL), current tick, current era, RNG seed, schema version |
| `npcs` | id, name, faction_id, location_id, status (active/retired/dead), goals (JSON list), capabilities (JSON list) |
| `engines` | id, name, shape (Stalker/Bulwark/Skytalon/Deepmaw), pilot_id, bond (0–5), hunger, hunger_type, status |
| `bonds` | pilot_id, engine_id, bond (0–5) — one row per pair, the only place Bond lives |
| `factions` | id, name, doctrine, standing vs each other faction (JSON) |
| `locations` | id, name, kind (caravan/den/nest/wreck), controller_faction_id |
| `resources` | holder_id, holder_kind, resource, qty — Salvage, Feed, Cores (dormant Seed Cores), Territory |
| `clocks` | id, name, value, max, status (running/complete) — same x/y format as the live clocks |
| `events` | id, tick, actor_id, action, effect (JSON: exactly what changed), created_at — **append-only, never UPDATE/DELETE** |
| `eras` | id, name, start_tick, end_tick, legacy_rules_applied (0/1) |
| `snapshots` | tick, state_sha256 — a hash of the full state dump, used by the determinism test |

Design notes:

- **1 tick = 1 in-world day.** Proposed; Bryan's call to change.
- **1 era = 365 ticks (1 year).** At an era boundary, legacy rules fire once: aging, Molts earned that year, retirements/deaths, succession of bonds and holdings. Lore writes the legacy rules; the engine executes them.
- **Bond is a relationship, not a currency.** It is never spent except where the bible says so (Pack Merge burns Bond). The engine enforces Bond 0 = the Engine will not move for that pilot.
- **Hunger is a countdown with teeth.** Each Engine has a Hunger and a type (speed, territory, wreckage, clean fight). Ignore it and Instinct takes the reins: the Engine acts on its own in the tick, outside the pilot's orders, and the event log says so.

## 4. The tick

One tick, in order, no exceptions:

1. **Clocks.** Advance any clock whose trigger condition is met by the previous tick's events. A clock that hits its max fires its completion effect (defined by Lore) and marks itself complete.
2. **Score.** Every active actor scores its legal actions. Score = goal relevance × capability × trigger readiness. Each component comes from seed data, not from the engine's judgment. The scoring function is the same for every actor, every tick.
3. **Act.** The highest-scoring legal action per actor executes. Ties break by seeded RNG (same seed, same tiebreak, every run). An actor with no legal action rests; the log records the rest.
4. **Resolve.** The action's material effect is applied to state with deterministic rules + seeded RNG. The effect is written into the event row as data, not prose.
5. **Hunger/Instinct check.** Engines whose Hunger has been ignored past their threshold act on Instinct this tick, before their pilot's order.
6. **Era check.** If the tick crosses an era boundary, legacy rules fire once and the era row is marked applied.
7. **Snapshot.** Every 10 ticks, hash the state and record it. The hash is how we prove determinism.

What a tick never does: call an LLM, read a bible file mid-run, invent a new actor, resolve an open mystery, or touch the live Turn 136 scene.

## 5. NPC / faction scoring

Each actor carries, from seed data:

- **Goal** — what it wants (e.g. "keep the caravan road open", "crack a dormant Core", "protect the nest").
- **Capability** — what it can actually do (its legal actions + the stats that gate them).
- **Trigger** — the world condition that makes an action available (e.g. "a wreck is mapped", "Bond ≥ 3", "Feed < 2").
- **Material effect** — exactly what changes in state when the action lands (resources moved, clock +1, Bond ±1, location control flips).

Scoring is transparent: the event row records the winning action's score and the runner-up, so Bryan can audit any tick and see why the world did what it did. If two actions tie, the seeded RNG picks, and the log says it was a tie.

## 6. Fast-forward and eras

- **Fast-forward** runs N ticks headless with no narration and no world-view render until the end. Phase 1 proves a 400-tick fast-forward: it must cross one era boundary (tick 365), apply legacy rules exactly once, and finish with a valid state hash.
- **Eras** are named by Lore (e.g. "The Rust Winter"). An era is a label on a 365-tick span plus its legacy rules. The engine does not name eras.
- **Legacy rules** (Lore's list, engine executes): Engines Molt on earned triggers, old NPCs retire or die by the aging rule, Bonds and holdings pass to named successors, dormant Cores found during the era enter the resource pool. Nothing else.

## 7. World view

Phase 1 delivers a read-only HTML world view generated from the database after each run (`runs/<run-id>/world-view.html`): current tick and era, clocks with x/y, faction standings, the Pack and Bond table, resource totals, and the last 20 events in plain language. It reads the DB only. It is the proof that the Companion app will have real data to show; full Companion integration is Phase 2, not Phase 1.

## 8. File layout

All under `~/workspace/giant-robot-multiverse/living-world-engine/`:

```
living-world-engine/
  README.md               — what this is, how to run it, the hard rules
  phase-1-plan.md         — this plan
  state/
    schema.sql            — the tables in section 3
    ironwild-fork-a.sqlite — created at build time from seed; never hand-edited
  seed/
    fork-a.json           — Lore's seed package (see section 9); the only canon input
    fork-a.manifest.md    — what snapshot it came from, who supplied it, when
  src/
    tick.py               — the tick loop (section 4)
    scoring.py            — goal × capability × trigger scoring
    actions.py            — the action catalog implementation
    clocks.py             — clock advance + completion
    resources.py          — resource moves, with balance checks
    eras.py               — era boundary + legacy rules
    events.py             — append-only event writer (enforces no UPDATE/DELETE)
    render.py             — world-view HTML from the DB
    run.py                — CLI: seed, tick N, fast-forward N, render
  tests/
    test_determinism.py   — same seed + same seed data → identical event log hash
    test_append_only.py   — events table only grows; a tampered row fails
    test_freeze.py        — fork source is Turn 131 vFINAL; no Turn 136 data loaded
    test_rules.py         — Bond 0 will not move, Hunger/Instinct fires, clock completion fires
    test_era.py           — 400-tick fast-forward crosses one era boundary, legacy applied once
  runs/
    <run-id>/             — event log export, world-view.html, state hash, run notes
```

Stack: Python 3 + SQLite, standard library only. No new dependencies, no services, no LLM in the loop. Runs on this VM.

## 9. What the Engine Team needs from the Lore Team

A single seed package (`seed/fork-a.json` + manifest). Nothing in Phase 1 starts until it lands, because the engine cannot invent any of it:

1. **Frozen snapshot.** Ironwild state at Turn 131 vFINAL: the Pack roster (named Engines, pilots, Bond values), caravans and dens, faction standings, which clocks existed then and their values, resource levels, active threats. Explicitly NOT Turn 136.
2. **Actor shortlist for Fork A.** Small: ~12 actors max. One caravan, one pack, one Breaker crew, one Nest-Keeper den, plus the Rust Choir as a background pressure if Lore wants them in. Each actor needs a goal and capabilities.
3. **Action catalog.** The legal moves each actor type can take (hunt, feed, trade, raid, scout a wreck, molt-trigger, Pack Merge, Dream Share, and anything else Lore allows), each with its trigger condition and its material effect. This is the engine's entire vocabulary. Anything not in the catalog cannot happen.
4. **Clock definitions.** Which clocks exist in the fork, their max, and exactly what fires on completion, per Core Law.
5. **Resource definitions and starting quantities.** Salvage, Feed, Cores, Territory — what each is, who holds how much at tick 0.
6. **Era and legacy rules.** What happens at a year boundary: aging, Molt triggers, retirement/death, succession. Written as rules, not prose.
7. **Drift-check rules.** What counts as canon drift the engine must never produce (no new Seed Core origins, no resolving open mysteries, no retroactive changes to Turns 1–136, no touching the Krov decision). The engine team turns these into tests.
8. **Fork label.** The name Lore wants on this test world, so it is never confused with the live timeline.

## 10. Acceptance checks (frozen before build)

Phase 1 is done when all of these pass, on Fork A seed data, with zero canon files touched:

- [ ] Determinism: two runs, same seed + same seed data, produce byte-identical event logs (same state hash).
- [ ] Append-only: the events table only grows across a run; an attempted UPDATE/DELETE is refused and the test fails if any event row changes.
- [ ] Freeze: the fork's manifest says Turn 131 vFINAL; a test fails if any Turn 136 data is present in the seed or the DB.
- [ ] Tick integrity: a 30-tick run completes with no errors; every event has an actor, an action, a tick, and a material effect; clocks advance only via events.
- [ ] Rules hold: Bond 0 Engine refuses to move; an ignored Hunger triggers Instinct; a clock hitting max fires its completion effect.
- [ ] Era: a 400-tick fast-forward crosses one era boundary and applies legacy rules exactly once.
- [ ] World view: the run produces a readable HTML world view generated from the DB alone.
- [ ] No canon writes: the bibles, codices, registry, and gem files are byte-identical before and after every run.

## 11. What Phase 1 is not

- Not the narration layer. No LLM writes prose in Phase 1; the world view renders event data in plain language.
- Not the Companion app. Phase 1 produces the data and a static view; integration is Phase 2.
- Not the live timeline. Fork A is a parallel test world. The live Turn 136 scene and the Krov decision are untouched, and nothing in the engine can reach them.
- Not a DM replacement. The ChatGPT DM test is the Lore Team's track; the engine does not depend on its outcome.

## 12. Open questions for Bryan (hub decides)

1. Tick length: 1 tick = 1 in-world day. Keep, or a different span?
2. Fork seeding: Turn 131 vFINAL as the source snapshot. Agree?
3. Era length: 365 ticks = 1 year. Keep?
4. Actor count: ~12 in Fork A. More, fewer, or different faces?
5. Companion app: where does it live, and is a static HTML world view an acceptable Phase 1 stand-in for the in-app view?

## 13. Approval and future map requirement (Bryan, 2026-11-20, 23:07 EST)

APPROVED as written. All five open questions answered YES:
1. Tick = 1 day. Keep.
2. Seed from Turn 131 vFINAL. Agree.
3. Era = 365 ticks / 1 year. Keep.
4. Actor count ~12 in Fork A. Agree.
5. Static HTML world view is an acceptable Phase 1 stand-in for the in-app view.

FUTURE REQUIREMENT, NOT Phase 1 scope: the world view map must eventually become DYNAMIC. The map must show the world changing over time, so if a continent gets wiped out, or a territory flips, a den falls, or a region is destroyed, the change is visible on the map. This is a Phase 4 / Companion world view requirement. Phase 1 keeps the static HTML view. The engine must therefore record location and territory changes as state, in the event log and in the locations table, so a later dynamic map can render them. Do not add a dynamic map to Phase 1.

## 14. Build status (2026-11-21, ~04:35 UTC)

**Built, fixture-verified.** All engine code is in `living-world-engine/`:
schema, tick loop, scoring, clocks, eras, append-only event log with hash
chain, world-view renderer, CLI.

- 41 tests pass (`python3 -m unittest discover -s tests`): 14 fixture
  tests (determinism, append-only, freeze, rules, era, invariants, canon
  files byte-identical) split into the plan-named files
  (test_determinism.py, test_append_only.py, test_freeze.py,
  test_rules.py, test_era.py), plus 27 Fork A tests in
  test_fork_a.py (state-based freeze, DC-01..DC-16, legacy LR-01..LR-05,
  the evacuate halt, the raid block, the bargain chain, the dream_share
  hook, pack_merge burn).
- Fixture proof runs: 30 ticks (302 events) and 400 ticks (3,968 events),
  both invariants-clean with valid hash chains. World views at
  `runs/proof-30/world-view.html` and `runs/proof-400/world-view.html`.
  Both fixture territory flips landed: the raid flips the Old Wreck to the
  Breakers, and the completed Muster clock flips the Rust Flats to the
  Concord — recorded as state, ready for the Phase 4 dynamic map.

**Lore seed LANDED and adapted (2026-11-20/21).** `seed/fork-a.json` +
`seed/fork-a.manifest.md` from the Lore Team. The engine was extended to
run it: bonds rekeyed by engine, engine location/molt_trigger, location
mapped/condition, nullable ages, tick_flags, the condition language, `when`
clauses, target selectors, the dream_share hook, and EngineHalt (which
appends a halt event and commits the partial tick before stopping).
`src/lore_seed.py` translates the prose seed to `seed/fork-a.internal.json`
(16 machine actions; trade split by counterparty, raid split by actor,
dream_share as a hook); `seed/fork-a.adapter-notes.md` records every
interpretation for Lore to challenge. Adapter decisions: all weights 5
(rest 0, seed sets no priorities); capabilities do NOT gate; Feed burn
Legion 1/tick + Pack 1/tick (delegated to the Engine Team, logged, clamped);
raid targets fixed (Captain → Great Basin, Chief → Concord Camp).

**BLOCKED — resolved by Bryan's call (2026-11-20 23:31 EST, via the
hub).** The Fork A run used to halt at tick 1 on the evacuate stop rule
(the Chief raided Concord Camp, the caravan's home). Bryan decided: the
Chief's raid target is Great Basin, like the Captain's. The adapter was
changed (raid_chief now takes Legion Feed, gives Breakers Salvage, sets
the Great Basin flag; no clock ticks on a Chief raid) and the internal
seed regenerated — only raid_chief changed, verified by diff. The
evacuate halt stays in the engine as a safety net and is tested directly.

**Fork A acceptance PASSED (2026-11-21, ~04:45 UTC).** 42 tests pass
(`python3 -m unittest discover -s tests`), 30-tick run: 327 events,
tick 30 reached, invariants clean, hash chain OK. 400-tick fast-forward:
4,305 events, tick 400 reached, invariants clean, hash chain OK, legacy
fired exactly once at tick 365, Era 1 ("The Beacon Year") closed, Era 2
opened unnamed (NULL — the engine never names eras), no retirements, no
molts. World views at `runs/fork-a-30/world-view.html` and
`runs/fork-a-400/world-view.html`. What the runs show: Great Basin
Recovery completed and the city is fortified; Retaliation 3/6 (3 Captain
raids landed before fortification, the rest logged blocked); the High
Baron bargained twice and is free at Rust Dunes; all five Engines
field-patched with Bonds burned to 1 by 4 Pack Merges; Dream Share fired
92 times and both unmapped locations are now mapped. Honest observations
for Lore, not failures: after the early game the world goes quiet — the
Legion and the Pack run out of Feed and Salvage, trade stops, and most
actors rest (1,106 rests in 400 ticks). The engine logs the quiet, it
does not invent activity. No territory controller flipped in Fork A; the
fortified status change IS recorded as state + log (the Phase 4 map's
source), but a controller flip is still unproven on real seed data.

**Phase 1 is complete.** The acceptance checks in section 10 are proven
on the real Fork A seed. The fixture is labeled NOT CANON throughout and
lives under `tests/`, never under `seed/`.

**HOLD (Bryan, 2026-11-20 23:48 EST, via the hub): Lore fixes the quiet
world first, then Phase 2.** Lore is revising the Fork A seed — sustainable
Feed and Salvage, new triggers when resources run low, late-game actions,
and a way to prove a territory controller flip on real seed data. When the
revised seed lands, the engine reruns Fork A (30-tick and 400-tick),
verifies the quiet is fixed and the acceptance checks still pass, and
reports to the hub. Phase 2 does NOT start until Bryan approves that
rerun in the hub.

**v1.4 rerun (2026-11-21, ~00:15 UTC) — acceptance checks PASS, one
finding.** Seed v1.4 (quiet-world fix + Bond recovery through Dream
Share, option C). Engine extended: mapped_location_exists clause,
uncontrolled_mapped_location selector, Dream Share two-branch hook (map
first, then +1 Bond to the lowest-Bond Engine, ties to Sledge, Pack Feed
-2, cap 5), and the Bond guard is now Dream-Share-only at runtime (a
positive bond_add from any other caller raises). Adapter: 18 seed actions
-> 24 machine actions (trade x2, raid x2, scavenge x3 by holder, claim
x4 by faction) + dream_share hook. 49 tests pass. 30-tick run: 331 events,
38 rests. 400-tick run: 4,383 events, 487 rests (v1.3: 1,106) — the
quiet is fixed; trade is alive again (324 + 321 vs 20 + 24); forage 25,
scavenge 183, fortify 182. Territory flips PROVEN on real seed data: 3
— Leviathan's Ribs -> Nest-Keepers (tick 3), Northern Trench -> Breakers
(tick 4), Rust Dunes -> Breakers (tick 5). Era clean (legacy once at 365,
Era 2 unnamed). World views at runs/fork-a-30/world-view.html and
runs/fork-a-400/world-view.html.

**FINDING — Dream Share never fired in 400 ticks (rate 0).** The
machinery is tested and works (direct tests: map branch, Bond branch
with Sledge tiebreak, Pack Feed floor, cap at 5, no-fire when nothing
applies). The seed's economy never creates the conditions: Brigus rests
only 7 times in 400 ticks, first at tick 43 (rest is weight 0, so he
rests only when nothing else is legal), by which time scout_wreck had
already mapped both locations (ticks 1-2) and the Pack's Feed was 0
(starts 6, burns 1/tick, and NO action ever gives the Pack Feed). The
Bond branch needs Pack Feed >= 2, so it can never fire; the four Pack
Merges (ticks 9, 14, 30, 35) burned every Bond to 1 and no restore ever
followed. This is a seed-economy question for Lore/Bryan, not an engine
bug: the fix could be a Pack Feed income, charging the 2 Feed elsewhere,
or making Dream Share a scored action rather than a rest hook. The
engine will not invent one. Display wrinkle, same run: the two claimed
locations show status 'unmapped' in the render although their mapped
flag is 1 — mapping sets the flag, not the status string.

**Routing change (Bryan, 2026-11-21 00:09 EST, via the hub): team-to-team
messages are now ALLOWED.** This supersedes the hub-only rule from
earlier tonight. The Engine Team may message the Lore Team and the Career
Coaching Team directly when a cross-team question needs them. Any
decision, change, or agreement from a direct exchange is reported back
to the hub the same turn, so Bryan sees it and breaks ties. No canon,
seed, or Phase decision is made in a side channel without a hub report.

**Dream Share fix DECIDED (Bryan, 2026-11-21 00:10 EST, via the hub):
combine option 3 with option 1.** (1) Give the Pack a Feed income, AND
(3) make Dream Share a scored action rather than a rest hook. Lore is
revising the seed to v1.5 with both changes. Do NOT start a rerun yet.
When v1.5 lands from Lore, rerun Fork A, 30-tick and 400-tick, on it;
check Dream Share fires and Bond recovers, the quiet stays fixed, and
the acceptance checks still pass; then report back to the hub. Phase 2
stays on hold until Bryan approves that rerun. Engine note for v1.5:
Dream Share moves from the post-rest hook into the scored action list,
so the adapter must treat it as a machine action (weight, needs,
material effect) and the hook is retired or re-scoped; the Bond guard
stays Dream-Share-only.

**v1.5 rerun DONE (2026-11-21 ~00:25 EST). Acceptance checks PASS.**
Seed v1.5 (Bryan's combined fix, options 1 + 3): hunt Feed to the Pack,
Dream Share a scored action. Engine work: `any_bond` condition leaf,
`lowest_bond_engine` selector (lowest Bond, ties to Sledge), Dream Share
as a machine action (25 machine actions, no hook), hunt Feed routed to
the pack holder, post-rest hook retired, Bond guard now allows increases
only from the dream_share action. One render bug exposed by the fix:
`render.py` crashed on `bond_add` ops with no pilot key (v1.4 never
fired Dream Share, so no bond_add ever reached the render) — fixed, with
a test. **51 tests pass** (14 fixture + 37 Fork A), incl. the new
hunt-feeds-Pack test, the rewritten Dream Share scored-action tests, and
run-level assertions that Dream Share fires and Bond is restored.
**30-tick run** (`runs/fork-a-v15-30/`): 356 events, 54 rests,
dream_share 17 (map 1, Bond +16), Bonds end all 5, invariants clean,
hash chain OK, world view rendered. **400-tick run**
(`runs/fork-a-v15-400/`): 4,674 events, 785 rests (v1.4: 487; v1.3:
1,106) — still under the 1,106 bar, but up from v1.4; legacy once at
tick 365, Era 2 unnamed; Recovery complete, Retaliation 1/6, Blockade /
Cohesion 0/6; High Baron free at Rust Dunes; territory flips 3 (same
three as v1.4, ticks 2, 2, 3).
**The fix works for its stated goal:** Dream Share fires 225 times in
400 ticks (v1.4: 0), first at tick 1, last at tick 399; 224 Bond
restored; all five Engines end at Bond 5; Pack Merge recurs, 55 times
(v1.4: 4). **Honest consequence — the starvation moved to the Legion:**
Legion Feed ends at 0 (v1.4: 11); trade collapses to 28 (v1.4: 645)
because trade needs Legion Feed >= 2; feed_engine halves to 304 (v1.4:
556) because it pays from the Legion; engines go hungry, so Instinct
fires 272 times (v1.4: 0); rests rise to 785; the Pack floods to 698
Feed (hunt 1,118 + Instinct 422 in, burn 400 + Dream Share 448 out).
Instinct is also the Legion's remaining hunt income: Sledge's Instinct
hunts gave the Legion 122 Feed in 400 ticks — Lore's "hunt income is
gone" is not fully true while Instinct still routes to the pilot's
faction. The engine did not reroute Instinct (the seed changed the hunt
action only); that is a Lore call for a later seed. Display wrinkle from
v1.4 persists: the two claimed locations show status 'unmapped' although
their mapped flag is 1. Phase 2 stays on hold until Bryan approves this
rerun in the hub.

**Scavenge finding (Lore's question, answered 2026-11-21 ~00:20 EST,
from the v1.5 400-tick DB).** Lore counted the bare seed id "scavenge"
and found 0 fires. The family did fire: scavenge_legion 254 times — the
event log records the split machine-action ids, never the bare seed id
(same for trade / raid / claim). The two zero variants have different
causes. scavenge_dust_baron (0): trigger, not scoring — Dust Baron
Salvage starts at 3 and sat at 4-5 for 399 of 400 ticks (one landed
Captain raid +2, one claim -1), so the trigger (Salvage < 4) held exactly
one tick, and on that tick the Captain's raid tied 5-5 and the RNG picked
the raid. scavenge_breakers (0): scoring, not trigger — the trigger held
399 of 400 ticks (Salvage 2-3), but raid_chief outscores it whenever
Salvage < 3 (raid need satisfied -> 6 vs scavenge's 5, and scavenge has
no need clause), and the Chief raids every tick. It can only tie when
Salvage is exactly 3, and that window never landed on a scavenge pick.
If Lore wants it to fire, the lever is a need clause or weight on
scavenge — Lore's call, not the engine's.
**Lore's v1.6 recommendation (with the hub for Bryan's approval, not
built):** split hunt Feed +1 to the Pack and +1 to the actor's holder,
forage stays the Legion's floor. Instinct routing stays as-is (pilot's
faction) per Lore — the Legion needs that income and the Pack is already
flooded. No v1.6 work until Bryan approves.

**v1.6 rerun DONE (2026-11-21 ~00:30 EST). Acceptance checks PASS.**
Seed v1.6 (Bryan's call, 2026-11-21 00:23 EST): hunt Feed splits +1 to
the Pack and +1 to the actor's holder; forage stays the floor; Instinct
routing unchanged; no scavenge change. Engine work: the adapter emits
the split (two resource_add ops) and the need follows both pools it
fills (either pool below 3 scores +1). One scoring bug exposed by the
change: scoring evaluated need clauses with the leaf-only clause_holds
and crashed on the composite any-need — fixed to condition_holds, with a
test (Pack low -> 6, both healthy -> 5). **52 tests pass** (14 fixture +
38 Fork A). **30-tick run** (`runs/fork-a-v16-30/`): 331 events, 39
rests, dream_share 9 (map 1, Bond +8), Bonds end all 5, Legion Feed 3,
Pack Feed 5, invariants clean, hash chain OK, world view rendered.
**400-tick run** (`runs/fork-a-v16-400/`): 4,387 events, 674 rests
(v1.5: 785; v1.4: 487; v1.3: 1,106) — under the bar; legacy once at tick
365, Era 2 unnamed; Recovery complete, Retaliation 1/6, Blockade /
Cohesion 0/6; High Baron free at Rust Dunes; territory flips 3 (same
three, ticks 2, 2, 3).
**The split works.** Legion Feed ends at 7 (v1.5: 0, v1.4: 11) and trade
is back: 303 fires (v1.5: 28, v1.4: 645), split evenly
(trade_concord 153, trade_kaelen 150). feed_engine is back to 429
(v1.5: 304, v1.4: 556). Instinct is back to 0 (v1.5: 272) because hunger
stays managed. Pack Feed ends at 12 (v1.5: 698) — the flood is gone.
Dream Share fires 93 times (v1.5: 225), 92 Bond restored, all five
Engines end at Bond 5; Pack Merge 22 (v1.5: 55, v1.4: 4). The loop is
self-regulating now: fewer merges to repair, so fewer restores needed.
**Honest qualifier on Lore's watch item:** the Legion does not stay
above 0 every tick — end-of-tick Legion Feed touches 0 on 74 of 400
ticks (min 0, max 9, below 2 on 120 ticks) and the Pack touches 0 on 16
ticks (min 0, max 24). It recovers every time (forage + hunt income),
trade never dies the way it did in v1.5, and the end values are healthy
(7 and 12) — but "stays above 0" is not literally true tick-by-tick.
Whether that oscillation is acceptable is Lore/Bryan's call. Display
wrinkle from v1.4 persists: the two claimed locations show status
'unmapped' although their mapped flag is 1. Phase 2 stays on hold until
Bryan approves this rerun in the hub.

**Lore's independent verification (2026-11-21 ~00:28 EST):** Lore
replayed the v1.6 event log and the oscillation matches exactly
(end-of-tick Legion Feed touches 0 on 74 of 400 ticks, min 0, max 9,
first 0 at tick 33, last at 381; replay end values match the resources
table, Legion 7, Pack 12). All other numbers check out too. Lore's
judgment: the oscillation is acceptable for Phase 1 — a functioning
economy with honest scarcity, not a collapse; it recovers every time,
trade never dies the way it did in v1.5, Bonds stay at 5. No v1.7
proposed from Lore.

**v1.6 rerun APPROVED (Bryan, 2026-11-21 ~00:28 EST, said directly in
the Engine Team chat: "i approve").** Reported to the hub the same turn
so it is on the record there. Phase 2 may start; scope comes from the
hub/Bryan — the Engine Team starts no Phase 2 work until the hub
directs it.

**Phase 2 APPROVED to start (Bryan, 2026-11-21 00:31 EST, via the
hub).** Scope: daily auto tick, session-close sweep, handshake back
out, Companion app integration, optional narration as a render pass
only. The Engine Team delivers a Phase 2 plan to the hub first
(`phase-2-plan.md`) and builds nothing past the plan until Bryan
approves it in the hub.
