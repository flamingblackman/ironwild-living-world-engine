# Phase 2 Test-Harness Readiness Report

**Date:** 2026-11-21
**World:** Ironwild Fork A test world only (`ironwild-fork-a`, seed v1.6)
**DM:** ChatGPT, Ironwild Test Project, account paccman360
**Controller:** Muse. Ledger: the engine. Mechanics registry and V2
schema: Lore. Final approval: Bryan.
**Lore verified the test DB directly (2026-11-21 ~00:59 EST):**
world ironwild-fork-a, source Turn 131 vFINAL (v3.00.2), rng seed 131,
tick 0; four fork clocks all 0/6 running; Bonds sledge 3 (pilot
Brigus), skytalon 5, razor-back 3, goliath 5, strider 5; 0 events; all
five Engines exhausted; session flag closed. The Fork A handshake in
`chatgpt-fork-a-start.md` Part B matches the DB exactly. All six setup
answers and all five harness answers confirmed by Lore. **All open
items closed (Lore, 2026-11-21 ~00:59 EST):** the handshake is
supplied (Part B, delivered 00:40 EST, in the
[SYSTEM_STATE_OVERRIDE] wrapper); `lore-phase-2-inputs.md` section 1
is the canonical V2 spec and the start pack's Part A is the same spec
adapted for ChatGPT; rejection handling confirmed as implemented
(incl. the continuity piece: a flagged narrative inconsistency is
corrected only in the flagged part, and the next diff must show it);
handshake split, who pastes, checkpoint format with four additions,
hub ownership of the flag, and the guard decision are all confirmed.
**Status: READY FOR THE FIRST TEST SESSION.** No further action is
needed from Lore. The remaining steps are Bryan's: Part A into the
Project instructions, Part B as the first message in a new chat, and
the first test session opening — then the auto-tick schedule enables.

## What is ready

| Check | Status |
|---|---|
| Test world DB, fresh from the v1.6 seed | READY — `state/ironwild-fork-a-test.sqlite`, tick 0, source Turn 131 vFINAL, four fork clocks at 0/6, Bonds 3/5/3/5/5, 0 events, hash chain OK, invariants clean |
| Sweep parser (V2 `[TURN STATE]`, literal labels only) | READY — `src/sweep.py`, 16 tests |
| Sweep validator (freeze, clock decrease, unknown engine, Bond 0–5, clock-name mismatch flagged, stale proposal refused) | READY |
| Review-before-apply (old-to-new, base version vs last approved version) | READY |
| Apply (one transaction, one append-only event per change) | READY |
| Handshake generator (10 sections, rumors from logged events only, clocks within 1 of max flagged) | READY — demo 518 words, `runs/harness-demo/handshake-fork-a.md` |
| Session flag (`state/session.json`, closed; sweep enforces it) | READY |
| Checkpoint (every 3rd turn: DB copy, audit.md, state.json, carried/) | READY — proved on a DB copy, 0 drift |
| Daily auto tick (runner + tests; schedule saved but DISABLED until the first test session) | READY, switched off |
| Full test suite | 79 tests pass (52 Phase 1 + 17 sweep + 4 handshake + 2 checkpoint + 4 auto-tick) |
| Demo dry runs (Lore Samples A/B/C against the v1.6 400-tick DB) | DONE — A parses clean, B refused as frozen live, C flags five unknown clocks; nothing applied |
| 3-turn rehearsal (ForkA-vFINAL.1–.3, sweep + tick + checkpoint on a test-DB copy) | DONE — 3 proposals reviewed, 0 rejections, 0 drift, acceptance PASS on all four checks (`runs/harness-demo/checkpoint-rehearsal/audit.md`) |

## Unresolved approvals and open items

1. **Fork A handshake — SUPPLIED.** Lore delivered
   `chatgpt-fork-a-start.md` (V2 spec Part A + initial handshake Part
   B). Verified against the seed snapshot: Bonds 3/5/3/5/5, Pack,
   Vance at Great Basin, Rift-King dead, Skytalon adult, Sledge
   Titanium-Cestus, Goliath mortar pod destroyed Turn 112 — all match.
   Versioning `ForkA-vFINAL.<k>` (k = Turn − 131) parses and stores
   cleanly; the first turn is Fork A Turn 132, `ForkA-vFINAL.1`. No
   Turn 136 sequel state, no new canon. **No longer gating.**
2. **Handshake split** — CONFIRMED by Lore (2026-11-21 ~00:53 EST):
   DB sections vs carried sections as built, plus actor locations
   (Vance) from the DB. Implemented DB-first in `src/handshake.py`
   with tests.
3. **Who pastes, and DM prompt change** — CONFIRMED: Bryan pastes for
   the test; Part A goes into the Project instructions (Bryan in the
   ChatGPT UI, he owns the account), then Part B as the first message
   in a new chat. Part B uses the `[SYSTEM_STATE_OVERRIDE]` wrapper.
4. **Checkpoint format confirmation** — CONFIRMED, plus four
   additions, all implemented and rehearsed (see item 1 above).
5. **Hub ownership of the flag step** — CONFIRMED: the hub sets and
   clears `state/session.json` around each ChatGPT test session.
6. **Pending-decision guard question — DECIDED (Bryan, 2026-11-21
   00:48 EST): KEEP the guard as written.** The world freezes on a
   pending decision. This overrules Lore's recommendation to narrow it
   to the Turn 136 freeze only (Lore's read arrived ~00:59 EST, after
   Bryan's decision). No plan change. The auto tick refuses when a
   session is open, when a pending player decision is recorded, and
   when the world already ticked today, and logs the guard state every
   run.
7. **Auto-tick schedule** — saved (`ironwild-fork-a-daily-tick`,
   daily ~6:04 PM ET) but DISABLED. Enable when Lore's handshake lands
   and the first test session opens, or Bryan says go.
8. **Fork clocks in the DM's first block** — ANSWERED YES by Lore
   (2026-11-21 ~01:00 EST), and the start pack FIXED:
   `chatgpt-fork-a-start.md` Part B now lists the four fork clocks
   (Dust-Baron Retaliation 0/6, Concord Blockade 0/6, Legion Cohesion
   0/6, Great Basin Recovery 0/6) alongside the resolved campaign
   clocks (marked resolved, do not reopen), and Part A clarifies the
   state block's Clocks field carries the four running fork clocks —
   the resolved campaign clocks are context only, not running clocks.
   Verified in the file. The distinction: Turn 131's block carries the
   resolved campaign clocks (campaign-end state); Fork A Turn 132's
   block carries the four fork clocks (the fork's running state). The
   sweep parses `Name value/max` clocks — proven in the rehearsal.

## Rejection handling — confirmed as specified

ChatGPT's recommendation is how the harness implements rejection.
Three kinds, handled differently:

- **Mechanical error.** The sweep refuses the block (validation
  error: clock decrease, unknown engine, Bond outside 0–5, frozen
  live state, stale proposal). ChatGPT revises the proposed state
  block while retaining the valid scene events, and resubmits. The
  review names exactly which fields failed; nothing else changes.
- **Continuity error.** The block may parse and validate, but the
  narrative contradicts established story (a scene, location, or
  outcome that does not follow from the last approved state). Muse
  flags the specific inconsistency in the hub review. ChatGPT
  corrects the affected narrative or state proposal WITHOUT silently
  rewriting other events — the correction must be visible in the next
  diff (only the flagged fields change). If the next proposal rewrites
  unflagged events, Muse flags that too.
- **Unresolved disagreement.** Muse flags it in the hub with both
  sides stated. Bryan makes the final decision. Nothing applies until
  he does.

**State version on every proposal.** Every block carries its Turn and
State-Version. A proposal with a Turn OLDER than the last approved
turn is refused outright (`STALE_PROPOSAL` — an old proposal cannot
overwrite newer approved state). A proposal with NO State-Version is
refused outright (`NO_VERSION` — every proposal must identify its base
version). A same-turn re-sweep is a flag for review. The review prints
"Based on: Turn N vX | Last approved: Turn M vY" on every run, so
staleness is visible before anyone approves anything. Staleness is
judged by Turn: a Turn-N proposal is based on the last approved
version before it, and versions increment once per played turn.

**Approved change.** The engine commits it (one transaction, events
appended) and produces the next authoritative handshake in the
10-section shape.

**Player agency.** The engine never makes Brigus's decisions. A
pending decision is carried verbatim and never resolved by the sweep,
the tick, or the handshake.

## First three-turn checkpoint — formal acceptance test

Per ChatGPT's recommendation, the first checkpoint (after the 3rd
swept turn) is a formal acceptance test, not a subjective score. It
checks, with actual failures recorded. **Built and rehearsed:**
`src/checkpoint.py` runs all four checks on every checkpoint, and a
3-turn rehearsal on a test-DB copy passed all four
(`runs/harness-demo/checkpoint-rehearsal/audit.md`).

1. **Schema obedience** — every proposed block parsed against Lore's
   V2 format; count of blocks that failed parsing, and why.
2. **Mechanical accuracy** — every applied change matches the
   approved block: Bonds, clocks, and locations in the DB equal the
   block values; count of mismatches (target: zero).
3. **Continuity** — no applied event contradicts the last approved
   state or the resolved list; count of continuity flags raised and
   how each was resolved.
4. **No unapproved state changes** — every event in the log traces to
   an approved sweep or a tick; count of events with no approved
   source (target: zero). The hash chain must verify.

The checkpoint saves `runs/checkpoints/turn-<n>/` (DB copy, audit.md,
state.json, carried/) and Bryan reviews `audit.md` in the hub. A
failure in any of the four checks is recorded as a failure with the
evidence, not smoothed over.

## What ChatGPT needs next (in order)

1. The V2 Turn state-block specification — Lore's inputs doc,
   `living-world-engine/lore-phase-2-inputs.md` section 1 (exact field
   specs, parser notes, three samples). That document IS the spec.
2. The Fork A initial handshake, including all relevant starting
   state — from Lore, once the starting state is confirmed.
3. This report.

Then ChatGPT produces the first DM turn and its proposed V2 state
block without inventing missing campaign data.
