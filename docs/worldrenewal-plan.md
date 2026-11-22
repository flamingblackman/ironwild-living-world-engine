# WorldRenewal (Step 4B) — plan and test list

Status: PLAN ONLY. No code changed, no seed changed, no live DB touched.
Each build needs its own approval of this plan first (roadmap rule),
and each build's seed pack needs Lore's approval before it is applied.
Fork A's seed is never modified.

## Goal

The world must not run out of story. The engine only chooses among
pre-approved content; it never invents canon. New content arrives as
seed packs Lore approves. Everything stays deterministic on the Step 2
per-actor RNG streams (plus a world stream for world-level drift, same
`rng_for` function, key "world"). Any effect touching a story-owned
actor becomes a hook, not an applied change (StoryOwned owns that
rule; this plan does not build it).

## Acceptance (milestone)

A 2,000-tick run on the revised Fork B seed:
- significant events > 0 in every 100-tick window, to tick 2,000;
- verify_invariants passes; deterministic across repeat runs;
- all existing tests pass.
"Significant event" uses the Step 0 audit definition, CONFIRMED by
Bryan 2026-11-22 (roadmap decision 4, resolved): a clock advancing
or completing, a place changing hands, a raid actually gaining
something, a new place being claimed, a status changing, a bond
changing — PLUS a location destroyed or ruined (build I). A
ruination is already a status change and a controller change, so it
counts under the old definition too; the plan names it explicitly
and the meter reports it as its own kind, so it cannot hide inside
generic status changes. That definition is now decided, not
proposed.
The acceptance measurement EXCLUDES status flips on story-owned
engines (the Ashfang net↔repair loop): under StoryOwned those become
hooks, so they must not prop up the count. The exclusion is a filter
in the measurement, not an engine change, until StoryOwned lands.

## Ground truth (from the Fork B 1,000-tick measurement)

- Significant events never drop to zero (62–74 per 100 ticks), but
  after tick 4 every one is the net↔repair loop (337 each).
- Clocks never move. Fork B has ZERO working clock_add sources:
  repair_engine points at great_basin_recovery, a Fork A clock that
  does not exist here (the third seed diff, pending); raid_captain
  points at dust_baron_retaliation but its `when` requires NOT
  fortified AND NOT patrolled, and Great Basin is permanently
  fortified, so the gate never opens. engine_awakening and
  caravan_route have no source at all.
- Raids never land (1,505 blocked, 0 Salvage gained). Trade never
  fired before the approved diffs (now fixed). Five of twenty actions
  never fire.
- Legacy already works: era boundaries fire legacy rules at ticks
  365 and 730; retire_age is null, era_names is ["The Rust Dunes
  Discovery", null]; NPC age and successor columns exist; LR-01
  aging and LR-03 succession for the dead already exist.
- Unmapped frontier: leviathans_ribs, northern_trench.

## Dependencies

- StoryOwned (roadmap milestone 5) removes the net loop. This plan's
  acceptance excludes the loop from the count, so WorldRenewal is
  proven on new content, not on the loop. The acceptance run is
  re-run after StoryOwned lands.
- The repair_engine dead op was DROPPED 2026-11-22 per Bryan's
  direct "drop the dead piece", so engine_awakening still has no
  source; build C must supply a new one (see C).
- The significance definition (roadmap decision 4) is CONFIRMED by
  Bryan 2026-11-22, including ruination as a meaningful event. It
  is decided, not proposed.

## Build A — repeatable clocks

What: a clock that completes, fires its on_complete, and starts over
instead of stopping dead.
Mechanism: a clock entry may carry `"repeatable": true`
(seed-declared). In `clocks.check_completions`, when a repeatable
clock reaches max: fire on_complete, reset value to 0, keep status
running (never mark complete). Each completion is logged as a
"complete" event, so the cycle count is derivable from the event log;
no schema change, no meta key. Same on_complete every cycle.
Seed: Lore marks which clocks repeat (proposed: dust_baron_retaliation
and caravan_route; engine_awakening only if Lore wants the awakening
to cycle).
File changes: `src/clocks.py` (reset instead of complete for
repeatable clocks). No seed file change in this build (the marking is
a seed pack for Lore).
Test list: a repeatable clock completes twice in a run, on_complete
fires twice, value resets to 0, status stays running; a
non-repeatable clock completes once and stays complete; the existing
complete-event and checkpoint tests still pass.
Build acceptance: on the revised seed, a 500-tick run shows each
repeatable clock completing at least twice (once its source exists —
depends on C).

## Build B — entropy

What: a slow, deterministic drift that keeps the world from settling
into a fixed point.
Mechanism: a world-level drift step in `tick.py` (new step, after the
NPC/engine steps, before the era check): every K ticks (seed-declared
`entropy_every`, proposed 30), one entropy event fires from a
seed-declared entropy table (small effects, e.g. a faction loses 1
Feed to spoilage, a location's status degrades one step). The choice
among table entries uses the world stream `rng_for(seed, "world",
tick)` — the same `rng_for` as the per-actor streams, no new RNG
scheme. Effects never touch story-owned actors: the table may only
reference factions, locations, and resources, never the party's
actors or engines (enforced by Lore's review of the pack; the
validator check lands with StoryOwned's story_owned set).
Seed: an `entropy` section (interval + table). Lore approves the
table and its fiction.
File changes: `src/tick.py` (entropy step), `src/seed.py` (store the
entropy table in meta at seed time, like "actions", so the tick can
read it without the seed file).
Test list: entropy fires on schedule (every K ticks); deterministic
across two runs; never changes a story-owned actor's state; the drift
actually moves resources (no faction's Feed stays pegged at max
forever).
Build acceptance: a 1,000-tick run shows entropy events at the
expected ticks and a measurable resource drift.

## Build C — wake the dead clocks

What: give every clock a working source, so clocks move at all.
Mechanism: mostly seed work. Engine: a clock-coverage report (extend
`tools/check_seed.py` with a `--coverage` mode) that lists, per clock,
its clock_add sources (action + op) and flags zero-source clocks. The
`when` gates are reported verbatim for Lore's judgment; the engine
does not decide whether a gate can ever hold.
Seed diffs (each needs Lore approval): (1) engine_awakening needs a
new source — repair_engine's clock_add is GONE (dropped 2026-11-22
per Bryan), so propose dream_share advancing it when Ragnus dreams
with Ashfang, or a new repair-adjacent action; Lore picks the
fiction; (2) trade_concord's effect gains a clock_add on
caravan_route (each successful trade advances the route); (3)
raid_captain's retaliation `when` gate relaxed (NOT-fortified can
never hold while Great Basin is fortified — propose: the clock
advances when a raid is attempted, or when the raider's Salvage is
low; Lore picks the fiction).
File changes: `tools/check_seed.py` (coverage mode). No core change.
Test list: coverage report lists zero-source clocks correctly on both
seeds (Fork A: concord_blockade, legion_cohesion; Fork B before the
diffs: engine_awakening, caravan_route, and the gated
dust_baron_retaliation); after the seed diffs, a 500-tick run shows
all three Fork B clocks advancing at least once.
Build acceptance: no Fork B clock has zero working sources; the
coverage report is clean.

## Build D — stagnation meter

What: a measurement that says, per 100 ticks, whether the world is
still producing story — and what kind.
Mechanism: a reusable function (new `src/stagnation.py`:
`significant_per_window(conn, start_tick, end_tick, window=100)`
reusing the audit's significant definition, plus
`stagnation_report(conn, ticks)`) returning per-100 significant
counts, the last-significant tick, and the composition by action. A
run is STAGNANT if any full 100-tick window has 0 significant events.
The meter is a reporting tool only; it does not change tick behavior.
The balance simulator (below) calls it for pass/fail.
File changes: new `src/stagnation.py`; a CLI or tool entry to run it
against a DB.
Test list: on the recorded Fork A sim DB, the meter reports
stagnation after tick 100 (18 then 0); on the recorded Fork B sim DB,
it reports no stagnation but flags that 100% of significant events
after tick 4 are the net loop; the meter reproduces the audit item 16
numbers exactly on both recorded sim DBs.
Build acceptance: the meter's numbers match the audit report on both
recorded sim DBs, to the event.

## Build E — pressure-driven goals

What: NPC goals that change with world pressure, so a faction under
strain acts differently from a comfortable one.
Mechanism: the seed declares pressure rules (a `pressure` section:
list of {condition, faction or actor, goal_tag, bonus}). At tick time,
`scoring.py` applies a +bonus to actions whose goal_tags match a
currently-pressured goal. The rules are stored in the DB at seed time
(meta "pressure_rules", like "actions") so the tick can read them
without the seed file. Rules may only target world NPCs and factions,
never story-owned actors (the validator check lands with StoryOwned's
story_owned set; until then Lore reviews the pack for it).
Seed: a `pressure` section (Lore approves the rules and the fiction
for each: e.g. when a faction's Feed is low, its feeding and trading
actions score higher).
File changes: `src/scoring.py` (pressure bonus), `src/seed.py` (store
the rules in meta).
Test list: a pressured NPC picks the pressured action over the
baseline; no pressure → baseline picks; deterministic; no pressure
rule in the seed pack targets the party.
Build acceptance: in a 500-tick run with a pressured faction, that
faction's pressured action fires measurably more often than in the
unpressured baseline.

## Build F — mortality and succession

What: NPCs age out and hand over, so the cast turns over instead of
acting forever.
Mechanism: extends the existing legacy rules. LR-01 already ages
(+1 per era for NPCs with an established age) and retires at
retire_age (currently null, so nothing retires). LR-03 already moves
Bonds and holdings to a named successor when an NPC DIES, and halts
if there is no successor. What is missing: succession for RETIREES.
New in this build: when an NPC retires, if they have a named
successor, the successor flips from 'dormant' to 'active' (successors
are seeded dormant; the tick only acts on status LIKE 'active%', so
a dormant successor never acts early) and takes over the role. A
retiree with no successor simply stops acting; no halt, no crash —
retirement is routine, death is the crisis. Bonds and holdings do
NOT transfer on retirement (unlike death): the retiree keeps them,
dormant; the successor acts with their own capabilities. The party
ages normally and retires (DECIDED — Bryan, 2026-11-22 17:13 EST:
Option 5, hand over to a new hero; see "The hero aging hole"
below). Lore gives the PC and the companion an age (NOT NULL) plus
a retire_age; at the boundary they age +1/year and retire at
retire_age (retirement, not death — no action kills by aging). On
retirement the story hands over to a successor hero (seeded dormant,
flips active, becomes the new PC). The old hero retires alive,
possibly as a mentor. Multi-generation saga.
Seed: Lore fills in ages, retire_age, and successors (a seed pack).
File changes: `src/eras.py` (retiree succession), possibly none
elsewhere — LR-01 and the age/successor columns already exist.
Test list: an NPC with retire_age 1 retires at the first era
boundary; the named successor flips dormant→active and acts from
then on; a retiree with no successor stops acting and nothing
crashes or halts; the PC and Pike age and retire at retire_age, and
the successor flips dormant→active and becomes the new PC
(Option 5, decided); deterministic.
Build acceptance: a 400-tick run (past one era boundary) with a
retiring NPC shows the retirement and succession events and the
successor acting.

### The hero aging hole (Bryan, 2026-11-22)

The current design leaves the PC and the companion with age NULL:
they do not age on paper, never retire. That is deliberate — the
engine will not end the player's story by itself — but it is a hole
over a long story: at 1 tick = 1 day, 1,000 years is 365,000 ticks,
and the world would age around a hero who never changes. There is a
second mechanical reason the design does this: LR-03 halts the
engine if an NPC dies with no successor, and the PC has no successor
named, so aging the PC into death would stop the engine. Options
(Bryan's call; no code until he picks):
1. Age normally, retire like everyone else. Seed gives Ragnus and
   Pike ages plus a retire_age; at the boundary they age +1/year and
   retire at retire_age (retirement, not death — no action kills by
   aging). The game then needs a successor: who plays next, and
   does Ashfang bond to the new hero or does the new hero bring a
   new engine? Lore and Bryan decide. The engine enforces a number
   Bryan picked, so it is his call, but it still ends Ragnus's story
   on a schedule.
2. Age slower. Seed gives the hero an aging_rate (e.g. +1 every 10
   eras); eras.py applies the rate. The hero outlives everyone but
   not forever. The number is arbitrary; Bryan and Lore pick it.
3. Frozen. Nothing changes in the code. Time skips are narrative,
   not simulated: the story jumps forward and the hero is the same
   age because the story says so. The world ages around him; he
   does not. Free, but a hand-wave — it works only if Bryan accepts
   "the hero is ageless in the story" as a genre rule.
4. The Bond keeps them young. Canon rule (Lore writes it): the Seed
   Core sustains its bonded pilot, so a bonded pilot does not age.
   Engine rule (eras.py): LR-01 skips aging for NPCs who pilot an
   engine (Bond > 0). Sub-question: Pike has no engine — does the
   Bond sustain the whole Pack (both stay young) or the pilot only
   (Pike ages and retires while Ragnus stays young)? Bryan decides.
5. Hand over to a new hero. The hero ages normally and retires, and
   the story hands over to a successor hero (seeded dormant, flips
   active on retirement, becomes the new PC). The old hero retires
   alive, possibly as a mentor. This is build F's succession applied
   to the PC. It turns the game into a multi-generation saga — the
   most story work (a new hero, a Bond decision, a PC handoff), and
   the only option where aging is real and the game continues.
Recommendation (Engine): option 4. It gives the agelessness a
reason instead of a gap, it keeps the game going, and it costs
almost nothing to build (one rule in LR-01 plus a canon line). The
Pike sub-question is the one call inside it. Option 5 is the saga
option if Bryan ever wants a generational story; option 1 is the
worst fit unless he explicitly wants an ending on a schedule.
Recommendation (Lore): option 5. Canon says Seedborns age normally
(the Seedborn price is feral instincts, not youth; the Bond is
trust, not youth), and the Engines and Cores outlive any one pilot,
so the story handing over to a new hero is the natural Ironwild
shape.
DECIDED (Bryan, 2026-11-22 17:13 EST): Option 5 — hand over to a
new hero. Ragnus ages and retires, the story hands over to a
successor hero (a new character, waiting in the wings, who becomes
the new player character). Ragnus retires alive, maybe as a mentor.
Multi-generation saga. The Engine's option-4 recommendation is
superseded by Bryan's decision.
Needed next (before Build F's seed pack is written): (1) Ages —
Lore proposes an age for Ragnus and for Pike (Ragnus is "a young
scavenger" in Fork B canon; Lore proposes a number, Bryan
confirms). (2) Retirement age — Lore proposes a retire_age for
Ragnus and for Pike (a human retirement age in this world; the
world is grim, so it may be earlier than a modern one), Bryan
confirms. (3) Successor hero — Bryan creates them when the time
comes (his story, his character); the successor is seeded dormant
in the pack (name, description, Seedborn status are Bryan's), flips
active on Ragnus's retirement, becomes the new PC. Lore reviews
the successor for canon. (4) Bond handover decision — when Ragnus
retires, does Ashfang bond to the new hero (the Bond transfers —
the new hero becomes Ashfang's pilot), or does the new hero bring
a new Engine (a new Core wakes for them, Ashfang retires with
Ragnus or goes feral)? Bryan and Lore decide (when the time comes,
or now as a standing rule). (5) When the successor is created —
Bryan creates them when the time comes, not now; the pack seeds
them dormant so the engine knows them, but their story and
character are Bryan's, made when Ragnus is near retirement (or
when Bryan wants to introduce them).
Build F now uses option 5. The test list changes: the "PC and Pike
never age or retire" test is replaced by "the PC and Pike age and
retire at retire_age, and the successor flips dormant→active and
becomes the new PC".

## Build G — era turnover

What: at each era boundary the world turns over — new era name,
clocks and resources reset toward seed-declared baselines — instead
of the boundary only closing the books.
Mechanism: `eras.apply_legacy` already closes the era and opens the
next (name from the seed's era_names; Fork B's second name is
currently null — Lore names it). Turnover adds seed-declared reset
rules (an `era_turnover` section): e.g. repeatable clocks reset to 0
on the boundary regardless of completion, each faction's Feed resets
toward a baseline (a partial reset, not a wipe). The turnover rules
are applied in apply_legacy, once per boundary (LR-05 already
guarantees exactly-once). Story-owned state is never reset: the rules
only name factions, locations, and clocks, never the party; Bonds and
Ashfang's status are untouched.
Seed: an `era_turnover` section + era_names filled in (Lore names
era 2 and beyond).
File changes: `src/eras.py` (turnover rules in apply_legacy).
Test list: two eras run, era name advances, the turnover rules apply
(clocks reset, Feed baselines), PC state untouched, deterministic,
LR-05 (applied once) still holds.
Build acceptance: an 800-tick run (past two boundaries) shows the era
names advancing and the turnover effects landing exactly once per
boundary.

## Build H — frontier pool

What: new ground to discover, so scouting and claiming never run out
of map.
Mechanism: the seed declares a `frontier_pool` (list of location
entries, Lore-approved, beyond the starting map). A step at the era
boundary (in apply_legacy): when the world has no unmapped locations
left, reveal the next pool location (insert into locations,
mapped=false, controller null). The reveal order is the pool order
(deterministic, no RNG). The revealed location becomes scoutable
(scout_wreck) and claimable, like the starting unmapped ones.
Seed: a `frontier_pool` section (Lore approves the locations and
their fiction).
File changes: `src/eras.py` (reveal step in apply_legacy).
Test list: a run that exhausts the frontier reveals a new location;
the revealed location is scoutable and claimable; the pool order is
deterministic; no reveal while unmapped locations remain; no crash
when the pool is empty.
Build acceptance: a 1,000-tick run on the revised seed shows at least
one frontier reveal after the starting unmapped locations are
exhausted.

## Build I — ruination (added 2026-11-22, Bryan's call)

What: large pieces of land can be destroyed or ruined, when the
story says so — by NPCs and by the player. The mirror of H: H adds
ground, I takes ground away (temporarily — see the restore path).
Bryan confirmed this is in scope as a meaningful event, for NPCs
and for Ragnus alike.
Mechanism: a location can be RUINED — a status, not a deletion.
The location row stays; its status becomes "ruined", its controller
clears, and it yields nothing and cannot be claimed until restored.
Two paths, both seed-gated:
- World path (NPCs): a seed-declared ruination action (e.g. a "raze"
  action for a faction). The engine only chooses among pre-approved
  content, so no ruination action in the seed means no ruination,
  ever. The action carries a trigger naming the target location and
  the condition, and a cost (e.g. Salvage -3, or a clock advance).
- Player path (Ragnus): Bryan's own turn block can ruin a location
  (a mechanical change in his [TURN STATE] block). It goes through
  the existing turn pipeline and approval routing, like any other
  mechanical change — it is his decision, stated in his block.
Restore path: every ruined location has a seed-declared restore
path (a rebuild action with a cost, e.g. Salvage, that returns the
location to a prior status). Ruination is a state, not a deletion;
nothing is removed from the DB and the history stays append-only.
Guardrails (what keeps it from happening by accident):
1. Seed-gated: no ruination action declared in the seed, no
   ruination ever. The engine cannot invent it.
2. Explicit trigger: the action's trigger must name the target and
   the condition; no trigger, never legal. The validator flags a
   ruination op with no trigger.
3. Cost: ruination always costs the actor, and its weight is low,
   so it is never the default pick.
4. No story-owned targets: the world tick cannot raze the party's
   home or the PC's location — a ruination op aimed there becomes a
   hook, not an applied change (StoryOwned). Only Bryan can ruin his
   own ground, through his block.
5. Pacing: a ruination sets a cooldown (a flag or a clock), so the
   same ground cannot be razed again immediately; or it requires a
   clock to complete first (a "war" clock as the pacing device).
6. Reversible: the restore path exists from the start, so a ruined
   location is a story beat, not a dead end.
7. Visible: ruination is a significant event by the confirmed
   definition and the meter reports it as its own kind; it is also a
   material op, so it surfaces as a rumor in the handshake.
Seed: a ruination action (and the rebuild action) in a seed pack.
Lore approves who can raze, what it costs, what it can target, and
the fiction for each.
File changes: no core schema change (a "ruined" status is a string
in the location status field; a ruination action is an ordinary
action in the catalog). `tools/check_seed.py` gains a ruination
check (a ruination op must have a trigger; must not target a
story-owned location). `src/stagnation.py` (build D) reports
ruination as its own kind.
Test list: a seed with no ruination action ruins nothing in a
1,000-tick run (0 ruination events); a ruination action with an
unsatisfiable trigger never fires; a ruination action with a
satisfied trigger fires, the location's status becomes ruined, its
controller clears, and the event is logged as significant and as a
rumor; the party's home and the PC's location are never razed by the
world tick; a ruined location can be restored via the rebuild action
(cost paid, status restored); a ruination in a player's block is
treated as a mechanical change (approval routing, not auto-applied);
deterministic.
Build acceptance: a 500-tick run on a seed with a live ruination
action shows at least one ruination and at least one restoration,
with no ruination of a story-owned location and no ruination in a
seed that declares none.
Dependencies: the story_owned set (StoryOwned) for the exclusion;
the world-changing-acts tiers (roadmap decision 3, still open) for
the player-path routing.

## Balance simulator

The acceptance harness is `tools/audit_step0.py` (generalized) plus
the stagnation meter (D). Pass/fail rule: significant events per 100
ticks must be > 0 in every window to tick 2,000, with the
story-owned status-flip exclusion applied. Fail a seed if any window
hits zero. The harness runs on COPIES, never on a live or frozen DB.
Each build is verified against the harness as it lands (the meter is
available from the start via the existing audit script; its full
build lands in its slot, D).

## Seed-change policy

Every seed change in this milestone is a diff proposed for Lore's
approval and Bryan's approval before application, exactly like the
trade/scavenge diffs. The seed file is edited only after both
approve; the live DB's catalog meta is synced the same way (the tick
reads the catalog from the DB). Fork A's seed is never modified.
Seed packs (entropy tables, pressure rules, frontier locations, era
names, successors) are Lore's content; the engine implements the
mechanisms only.

## Approval needed

- This plan (Bryan). No code until it is approved. The plan is now
  builds A–I (ruination added 2026-11-22 per Bryan's call).
- The significance definition (roadmap decision 4): CONFIRMED by
  Bryan 2026-11-22, including ruination. Resolved.
- Per-build seed packs (Lore approves content; Bryan approves the
  diffs). The plan does not pre-approve any pack.
- Build order is A–I as listed in the Step 4B addendum, plus I
  (ruination) after H. The meter (D) is the shared harness; its
  measurement function is available from the start, its full build
  lands in its slot.
