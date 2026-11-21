# Upgrades plan — Story-First, Automation-Heavy RPG

## 0. Approval and objective

**APPROVED by Bryan, 2026-11-21 01:29 EST: add the six upgrades
from ChatGPT, in the priority order below.** They sit under the
design objective (stage-1-plan.md section 0): Story-First,
Automation-Heavy RPG — the player plays, ChatGPT is the primary DM,
Muse is controller and auditor, the Engine owns persistent state,
Lore owns the approved mechanics specs.

**Nonnegotiable rule:** the engine never sacrifices correctness to
keep the story moving. If an important state update fails
validation, the game pauses at a safe point rather than pretending
it succeeded. Minor presentation issues do not block play, but
missing authoritative state must.

**Proof gate (do not build everything simultaneously):** first prove
three consecutive turns with correct persistent state and minimal
administrative work, then expand immersion systems. Turns 132–134
already prove three consecutive turns on the MANUAL path (all
applied, hash chains OK, handshakes delivered). The gate for the
automated path is three consecutive live turns through 1A/1B with
correct persistent state and minimal admin work — that gate is
still ahead, because no live turn has run through the pipeline yet.

**Scope discipline:** the Turn 134 handshake fix (PC Sledge Bond
4/5, generator draws PC Bonds from the DB) was the immediate
priority and is DONE. Upgrade work must not interfere with the
Fork A test. Fork A only; live Gemini canon untouched.

## 1. The six upgrades (priority order)

### First — Invisible Game Master Console + reliable turn handoff

All technical output — V2 blocks, validation logs, clock
calculations, handshakes — goes into the engine, not the gameplay
chat. The player sees narration and only the mechanical info needed
to make decisions.

- **Already built (do not rebuild):** the 1A pipeline (Drive inbox
  intake, proposal registry, approval binding, atomic commit,
  handshake to the outbox, intake poll cron); the sweep review (old
  → new, findings); the handshake generator (state sections from
  the DB, rumors labeled, clocks about to fire); the checkpoint
  audit. The technical output already lives in the engine
  (`runs/`, the registry, Drive) — the gameplay chat receives only
  the handshake, which is state, not technical output.
- **Missing (to build):** 1B — the ChatGPT Project conversation
  submits a V2 proposal and retrieves the approved handshake without
  manual copying (demonstrated end to end on Bryan's account only).
  The "reliable turn handoff" is 1A + 1B + the proof gate above.

### Second — NPC Memory and Motivation Engine + Living World Scheduler

**NPC Memory and Motivation Engine.** Important NPCs retain
relationships, promises, grudges, injuries, goals, and knowledge.
Behavior changes because of previous events, not because the DM
needs them to act a certain way. Hidden NPC info stays separate
from what the character knows.

- **Already built:** NPCs, factions, and locations exist as state
  tables; the event log records every action with actor, score, and
  effect; the handshake carries Pack membership and actor locations
  from the DB. No memory/motivation layer exists yet.
- **Missing (to build):** an NPC memory/motivation layer — a table
  (or tables) for relationships, promises, grudges, injuries,
  goals, and knowledge, keyed by NPC, with a hidden/known flag per
  item (hidden NPC info never enters the handshake; what the
  character knows is a separate, smaller set). Scoring inputs read
  it (an NPC with a grudge scores differently than one without) —
  the exact scoring hooks are a Lore + Engine design question, not
  a silent patch to the v1.6 seed.

**Living World Scheduler.** Factions pursue goals while the player
is doing something else. Enemy plans, resource shortages, political
developments, and opportunities progress on clocks and triggers.
The world should not freeze whenever Brigus leaves a location.
Simulated events only become canon through authorized state
changes.

- **Already built:** the tick engine (clocks advance, completions
  fire, resources move); the auto tick (one tick per day, guards);
  the fork clocks (Retaliation, Blockade, Cohesion, Recovery) are
  the scheduler's first subjects.
- **Missing (to build):** a scheduler that runs faction-goal ticks
  between player turns (or on the daily tick), advancing clocks and
  triggers for factions the player is not interacting with — with
  every simulated event recorded as an event, and canon only
  through the same authorized state changes (sweep apply / tick).
- **CONFLICT — needs Bryan's call, not just a build:** the
  pending-decision guard (Bryan's decision, 2026-11-21 00:48 EST)
  freezes the world — including the auto tick — while a player
  decision is pending. The scheduler wants the world to keep moving
  while the player is elsewhere. The question for Bryan: may
  scheduler ticks run while a decision is pending (never resolving
  the decision itself), or does the scheduler also pause on
  decisions? And does "the world should not freeze whenever Brigus
  leaves a location" cover movement during a pending decision, or
  only movement between turns? Do not build the scheduler's
  tick-during-decision behavior until he answers.

### Third — Adaptive Pacing Director + Automated RPG Quality Testing

**Adaptive Pacing Director.** Track unresolved threats, scene
tension, combat duration, and recent player choices. Use those
signals to help balance exploration, dialogue, combat, and
downtime. Influence presentation only — never secretly change dice
results, difficulty, or predetermined outcomes.

- **Already built:** the signals exist as state (pending decision,
  SCENE_TENSION, clocks within 1 of max, event counts per tick,
  recent actions in the event log). The handshake already surfaces
  "clocks about to fire" and the pending decision.
- **Missing (to build):** a pacing read over those signals that
  shapes the handshake's presentation (which rumors surface, how
  the off-screen list is ordered, a tension note) — presentation
  only, never state. No dice, difficulty, or outcome is ever
  touched.

**Automated RPG Quality Testing.** The Engine runs simulated cases
involving clock completion, Bond boundaries, inventory conflicts,
contradictory events, and stale handshakes. Expose problems in the
registry before they disrupt gameplay.

- **Already built:** 105 tests (unit + fixture runs + the 1A
  acceptance test); the fixture proof runs (30/400 ticks,
  invariants-clean); the checkpoint audit (schema obedience,
  mechanical accuracy, continuity/freeze scan, no unapproved
  changes, resource replay).
- **Missing (to build):** registry-specific simulated cases — a
  test harness that runs a case per registry mechanic (or per
  mechanic class) and reports which ones break, rather than the
  current suite, which tests the engine's own rules. Scope note:
  the "87-mechanic registry" is the CROSS-UNIVERSE index total
  (registry-index.md, 87 adapted mechanics: Ironwild 16 + Ashen
  Accord 19 + Veldt City 52). The Fork A test uses the Ironwild
  registry only — 16 entries (IW-42 to IW-54, IW-83 to IW-85). The
  quality-testing harness starts with the Ironwild 16; the 87 is
  the full index, not the Ironwild scope.

## 2. What is already built (do not rebuild it)

- Auto tick (Phase 2 item 1, built; its cron is DISABLED until
  Bryan says go).
- Append-only event log + hash chain (events.py, DB triggers).
- Snapshots (snapshots table; the auto tick records one per tick).
- checkpoint.py (the 3-turn audit: schema obedience, mechanical
  accuracy, continuity/freeze scan, no unapproved state changes,
  resource replay, Territory staleness, state version, rumors).
- STALE_PROPOSAL / NO_VERSION refusals (sweep.validate).
- 1A tamper test (proposals.py + tests: hash-mismatch refusal,
  held-then-restored revive).
- 105 tests (was 103 before the Turn 134 PC-Bond fix added 2).
- The handshake generator (10 sections, DB-first Engines/clocks/
  locations, rumors from events only, word budget).
- The session flag (state/session.json, hub-owned, closed default).
- The pending-decision guard (auto tick refuses while a decision
  is recorded).

## 3. Build order (per the approval)

1. **First:** Invisible console + reliable turn handoff — finish
   1B, then prove three consecutive live turns through the pipeline
   (the proof gate). No immersion-system build until the gate
   passes.
2. **Second:** NPC memory + living world simulation — the memory/
   motivation layer first, then the scheduler (after Bryan answers
   the guard-conflict question in section 1).
3. **Third:** Adaptive pacing + automated quality testing — the
   pacing read (presentation only) and the registry-case harness
   (Ironwild 16 first).

## 4. Open items

- 1B investigation (in progress): can the ChatGPT app on Bryan's
  account connect Google Drive, and can the Ironwild Test Project
  GPT read Drive files? (Browser task, read-only.)
- Scheduler vs pending-decision guard: needs Bryan's call (see
  section 1, Second). Do not build tick-during-decision behavior
  until he answers.
- NPC memory scoring hooks: Lore + Engine design question (which
  memory items move scores, and by how much) — not a silent seed
  patch.
- Quality-testing harness scope: Ironwild 16 first; the 87 is the
  cross-universe index.
- Standing permissions for routine changes: still to be defined
  and approved by Bryan; the gate is unchanged until then.
