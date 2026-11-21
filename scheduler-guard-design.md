# Scheduler guard design — Dwarf Fortress Adventure Mode shape

Bryan's decision, 2026-11-21 10:22 EST (via the hub): take inspiration
from Dwarf Fortress Adventure Mode for the scheduler vs
pending-decision guard. **This is a DESIGN for review. No
tick-during-decision behavior is built until Bryan approves this
design.** No seed change. Fork A stays at v1.6. Freeze intact.

**Cadence DECIDED by Bryan, 2026-11-21 13:22 EST (via the hub):
"Tick only when I play, 3 days per turn, like now."** That answers
design questions 3 and 4 together (see the struck items at the
end): the scheduler runs only as part of a played turn — 3 ticks
per played turn under this guard — no daily auto-tick, no catch-up
for days missed. The daily auto-tick cron stays DISABLED. The
design as now decided waits on Bryan's approval to build.

**Governed by Lore's canon guard** (`lore-df-adventure-guard.md`,
delivered 2026-11-21 ~10:25 EST), which SUPERSEDES the earlier
pending-decision guard (2026-11-21 00:48 EST: "keep the guard as
written. The world freezes on a pending decision"). The world no
longer freezes entirely. This design is written to match Lore's
guard; where the draft below differed from the guard, the guard
governs (the differences are called out in the rules).

## The DF shape

In DF Adventure Mode the world simulates continuously. When the
player is in a location, that location is loaded and the player acts;
elsewhere, the world runs on its own — armies march, towns trade,
history happens. The player's decision is never made by the
simulation. Applied here:

- The player's immediate scene = Brigus's location (Great Basin) +
  the pending decision.
- The off-screen world = everything that is not Brigus's choice:
  other actors, factions, clocks, resources, locations Brigus
  isn't in.
- The scheduler ticks the off-screen world while a decision is
  pending, but never resolves the pending decision, never moves
  Brigus's scene, never spends his choice.

## The guard rules

1. **Brigus's own actions never run during a pending decision.**
   The tick's actor loop skips Brigus entirely (he waits — his scene
   stays open). This is the core: the engine never acts for the
   player. Brigus's location and Wounds never change through
   off-screen simulation (the engine has no tick action that moves
   Brigus or wounds him; Wounds are not a DB field — structural,
   not a new mechanic).
2. **The Pack acts, but only off-screen and only within the frozen
   items.** Vance, Tull, Kaelen, and the Nest-Keeper keep acting
   (hunt, forage, scavenge, trade, bargain) — they are NPCs with
   their own work. A Pack action that would answer or presuppose
   the pending decision is skipped (rule 6), and a Pack action that
   would change a Brigus Engine's status is skipped (rule 4).
3. **Enemy and faction actors act normally, away from Brigus's
   scene.** Dust-Baron Captain, Breaker Chief, Legion Captain, High
   Baron, Caravan Master — raids, claims, trades, bargains all run.
   Clocks advance and complete (Retaliation, Blockade, Cohesion,
   Recovery). Resources move. Locations change hands (away from
   Brigus's scene). A clock's completion effect that would force
   the decision is deferred (logged) until the decision is
   resolved — the clock still advances, the effect waits.
4. **No off-screen action may change the status of one of Brigus's
   five Engines.** (Lore Frozen #4.) A status change is a hostile
   or dramatic event that would force Brigus to respond. This
   freezes repair_engine (Vance's repair, exhausted →
   field-patched) and any other status-changing action during a
   pending decision. Bond numbers and Hunger may still move —
   Dream Share restores a Bond, hunt/feed move Hunger.
5. **No NPC action may enter Brigus's immediate scene.** (Lore
   Frozen #6 — this CORRECTS the draft, which said off-screen
   events could reach Brigus's location.) An NPC moving into
   Brigus's location, or an action whose effect lands in Brigus's
   location, is forbidden while a decision is pending. A raid on
   Great Basin is blocked (fortified) — the blocked attempt is
   logged (flag + note, no state change), which is not a landed
   effect, so it is consistent with this rule. A raid elsewhere
   proceeds, subject to the existing halt rule (a raid on Concord
   Camp halts the engine; Lore names a fallback).
6. **Frozen scope, declared per decision, covers Frozen #5 only.**
   (Lore's guard items are the standing scope; the per-decision
   part is Frozen #5 — an action that would force THIS decision:
   resolve it, make it moot, presuppose an answer, require Brigus
   to act immediately, or change the facts the decision is about.)
   Lore declares any such actions when they verify the decision
   (they already review every new pending decision). The scope is
   stored in meta (`pending_decision_scope`, JSON) beside
   `pending_decision` and cleared when the decision is resolved.
   Example: for the elite-force decision, any action that formed or
   recruited a unit would be frozen — no such action exists in the
   v1.6 seed, so the default sufficed there.
7. **No resource expenditure tied to the decision.** A scheduler
   tick never spends resources on the decision's subject. The
   frozen scope is the mechanism (rule 6).
8. **The session flag still blocks.** A scheduler tick never runs
   while a session is open (live play). The DF shape is about the
   world moving BETWEEN sessions, not during one.
9. **Logging and audit.** A scheduler tick logs each skipped action
   as an event (auditable; the "what moved" list can show it was
   skipped, not silently dropped). A skipped action is a logged
   event but NOT a rumor source (nothing happened) — the build must
   verify the rumor generator excludes skip events.
10. **No override.** While a decision is open the guard is absolute:
    there is no flag to force a full tick past it. (A full tick in
    that window would act for Brigus.) The decision clears only when
    a block answering it is swept and applied.
11. **Cadence (DECIDED by Bryan, 2026-11-21 13:22 EST): tick only
    when Bryan plays, 3 ticks per played turn, like now.** No daily
    auto-tick, no catch-up for days missed. A scheduler tick is one
    of the 3 ticks in a played turn (scheduler mode when a decision
    is pending, full otherwise), never a separate scheduled run.

## What changes in code (the build, after approval)

- `src/tick.py: run_ticks(conn, n, rng=None, catalog=None,
  legacy=None, era_length=365)` gains a `scheduler=False` mode.
  When True, before applying each action the tick checks whether
  it touches a frozen item (Lore's enforcement): the actor is
  Brigus; the action is in the frozen scope (meta
  `pending_decision_scope`, Lore's per-decision Frozen #5
  declarations); any op changes a Brigus Engine's status
  (rule 4); any op's effect lands in Brigus's location (rule 5).
  A touching action is SKIPPED (the actor rests) and the skip is
  logged as an event (rule 9). A clock whose completion effect
  would force the decision still advances, but the effect is
  deferred (logged) until the decision is resolved.
- `src/sweep.py: apply_sweep` records `pending_decision_scope`
  beside `pending_decision` and carries it in the carried record.
  The scope holds Lore's per-decision Frozen #5 declarations only
  (the standing guard items are enforced structurally by the tick,
  not listed per decision) — it is set by the reviewer (Lore) when
  they clear a new decision, never invented by the Engine.
- `src/auto_tick.py: run_auto_tick` — **the mode switch is
  SUPERSEDED by the cadence decision (Bryan, 2026-11-21 13:22
  EST).** The daily auto-tick cron stays DISABLED, so run_auto_tick
  never runs on a schedule; it keeps its pending-decision refusal
  as written. The scheduler mode is driven by the played-turn tick
  (below), not by auto_tick.
- The played-turn tick (the manual `tick` command / the post-apply
  tick step) runs 3 ticks per played turn: scheduler mode when a
  decision is pending, full otherwise (same rule, no override
  flag).

## What does NOT change

- The Turn 136 freeze (absolute, separate rule).
- The sweep's pending-decision recording.
- The auto-apply / Lore-call / Bryan routing (a scheduler tick
  never applies a proposal).
- The append-only log, hash chain, snapshots, checkpoints.
- The daily auto-tick cron stays DISABLED (decided by Bryan,
  2026-11-21 13:22 EST — tick only when he plays, 3 days per turn;
  no daily auto-tick, no catch-up).

## Tests that will prove it (the build's acceptance)

- A scheduler tick with a pending decision: off-screen actions run
  (a raid lands, a clock advances, a claim happens) and Brigus's
  actions never appear in the event log.
- The frozen scope is respected: a frozen Pack action is skipped
  and listed in the note event.
- After the decision clears (a block answering it is applied), a
  full tick runs Brigus's actions again.
- A scheduler tick never writes `pending_decision`, never writes
  the scene, never changes Brigus's Bond/status/location.
- The session flag still refuses a scheduler tick while a session
  is open.

## Open questions for Bryan (in the design, not after the build)

Two are ANSWERED by Lore's guard and struck here for the record:

- ~~1. Is the default frozen scope (Brigus only) right, or should
  the Pack also be frozen during a pending decision?~~ ANSWERED by
  the guard: the Pack acts (Allowed #1), constrained only by the
  frozen items — no wholesale Pack freeze. The most consequential
  constraint is Frozen #4: no repair_engine during a pending
  decision (a status change would force Brigus to respond).
- ~~2. Who declares the frozen scope — Lore when they verify the
  decision (the proposal here) or Bryan each time?~~ ANSWERED by
  the guard: the frozen items are the standing scope; Lore declares
  only the per-decision Frozen #5 additions when they verify the
  decision.

Still open:

~~3. Should scheduler ticks run on the daily auto-tick (1/day) or
   more often while a decision is pending?~~ **ANSWERED by Bryan,
   2026-11-21 13:22 EST: tick only when he plays, 3 days per turn,
   like now. No daily auto-tick, no more-often schedule.**
~~4. DF also simulates while the player is away for days — the
   no-catch-up rule says no. Keep it, or revisit?~~ **ANSWERED by
   Bryan, 2026-11-21 13:22 EST: keep no-catch-up. No ticks for
   days missed.**

No open questions remain. The design as now decided waits on
Bryan's approval to build.
