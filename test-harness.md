# Shared-State Test Harness — ChatGPT DM + Muse Controller

**Status:** BUILT and tested (2026-11-21). 84 tests pass (52 Phase 1 +
17 sweep + 6 handshake + 5 checkpoint + 4 auto-tick).
**World:** Fork A test world ONLY (`ironwild-fork-a`, seed v1.6). NOT
live Gemini canon, NOT Turn 136.
**DM:** the existing Ironwild Test Project on ChatGPT Plus, account
paccman360.
**Controller:** Muse, as the campaign controller. The shared campaign
ledger is the engine.
**Test world DB (fresh, live):** `state/ironwild-fork-a-test.sqlite`,
seeded from the v1.6 seed (`seed/fork-a.internal.json`). Verified:
tick 0, source Turn 131 vFINAL, world `ironwild-fork-a`, four fork
clocks at 0/6, Bonds 3/5/3/5/5, 0 events, hash chain OK, invariants
clean. This is the DB the test plays on. The v1.6 400-tick run DB
(`runs/fork-a-v16-400/fork-a.sqlite`) is the demo/acceptance record
only — the test does NOT continue from it.

## Starting state (confirmed with Lore)

The test starts FRESH from Fork A (Turn 131 vFINAL), NOT a
continuation of the existing Turn 137–138 test timeline in the
Project. The DM must be briefed on that: the world is Fork A, and its
clocks are the four fork clocks (Dust-Baron Retaliation, Concord
Blockade, Legion Cohesion, Great Basin Recovery), not the five sequel
clocks. A block carrying sequel clocks will flag every one as unknown
in Fork A — correct behavior until Lore says otherwise.

## The deal, in one paragraph

ChatGPT DMs a turn and proposes a Turn state block in the V2 format.
Muse sweeps it, validates it against the registry, the clocks, the
Bonds, and the engine DB, flags any drift or rule break, and shows
old-to-new for review. Nothing lands without Bryan's approval in the
hub. The engine applies approved changes to Fork A, ticks as needed,
and generates the handshake back out for the next ChatGPT turn.
Checkpoint every 3 turns: Muse audits, ChatGPT corrects genuine
mistakes and continues. No mid-turn debate on every sentence.

## What is NOT built (by Bryan's order)

- No live browser link to Muse.
- No custom two-agent app.
- No auto-apply of state. The sweep is review-before-apply, always.

## The turn loop, step by step

1. **Session opens.** The hub sets `state/session.json` to open
   (world `ironwild-fork-a`, turn being played, who opened it). While
   it is open, the auto tick stays out and the sweep refuses to apply.
2. **Handshake in.** Bryan pastes the engine-generated handshake into
   the Ironwild Test Project chat (handshake delivery for the test is
   paste-in by Bryan; auto-deliver comes later). ChatGPT echoes it
   back and plays from that state.
3. **ChatGPT DMs one turn** and ends with a V2 `[TURN STATE]` block,
   in full, plus a `[SESSION CLOSE]` block at session end.
4. **Session closes.** The hub clears `state/session.json` and hands
   the final `[TURN STATE]` block to the sweep.
5. **Sweep (dry run first).** Muse runs:
   `python3 -m src.run sweep --db <fork db> --block <block file>`
   The parser takes literal labels only. Validation checks: the frozen
   Turn 136 vFINAL.5 block is refused outright; clock values never
   decrease silently; a clock-name mismatch is flagged for Lore
   review, never silently reconciled; Bonds must be 0–5 and name an
   engine in the DB; Unresolved Decisions are carried verbatim, never
   resolved. The review prints old-to-new changes plus findings.
6. **Bryan approves in the hub.** Only then Muse runs the same command
   with `--apply --approved-by Bryan`. The apply runs in one
   transaction: clock and Bond updates plus one append-only event per
   change, each with old and new values and the source Turn. If a
   clock reaches its max, the next tick fires its completion effects;
   the sweep never fires them itself. The applied record and the
   carried state land in `runs/sweeps/turn-<n>/`.
7. **Tick as needed.** The engine ticks Fork A forward (manual tick
   for the test; the daily auto tick is Phase 2 item 1, next build
   step) and re-renders the world view.
8. **Handshake out.** Muse runs:
   `python3 -m src.run handshake --db <fork db> --carried <carried file> --out <file> --since-tick <last close tick>`
   The handshake is generated from the DB alone plus the carried
   state, in Lore's 10-section shape, ~400–600 words. Bryan pastes it
   into the next ChatGPT turn.
9. **Checkpoint every 3 turns.** After every 3rd swept turn, Muse
   runs:
   `python3 -m src.run checkpoint --db <test db> --carried <the last 3 carried.json files> --out runs/checkpoints/turn-<n>/ [--seed <seed>]`
   What is saved: `state.sqlite` (a copy of the test DB), `audit.md`
   (Bonds and clocks, block value vs DB value now, MATCH / DRIFT per
   line; the latest pending decision verbatim; tick, event count,
   state hash), `state.json` (the same summary machine-readable), and
   `carried/` (copies of the three swept blocks' carried state). The
   audit also runs the four acceptance checks (schema obedience,
   mechanical accuracy, continuity incl. a freeze-term scan, no
   unapproved state changes) and Lore's four additions: resources
   (non-negative; Salvage/Feed/Cores replayed seed + event deltas when
   `--seed` is given; Territory rows shown against the locations each
   holder controls), Pack membership and actor locations, state
   version (ledger vs last approved block), and rumors live with their
   source event ids. Bryan reviews `audit.md` in the hub. A DRIFT
   line means the DB moved after the sweep — it is reported, never
   silently reconciled. ChatGPT corrects genuine mistakes and
   continues. No mid-turn debate on every sentence.

   **Known limitation the checkpoint surfaced (2026-11-21): Territory
   is a seed value the engine never maintains.** No event op updates a
   Territory row when a location's controller flips, so a holder's
   Territory can read 0 while it controls 2 locations (Breakers and
   Dust Baron in the rehearsal). The checkpoint shows the staleness
   plainly (STALE markers + controlled counts) rather than hiding it.
   Fixing it means a claim updating Territory — an engine/seed change
   for a future version, not a silent patch to the accepted v1.6 run.
   The resources verdict is separate from the acceptance verdict: the
   rehearsal passed acceptance on all four checks while reporting 2
   Territory problems.

## Session flag status

`state/session.json` is in place, currently closed. The sweep already
refuses to apply while it is open (built and tested). The daily auto
tick does not exist yet (Phase 2 item 1, next build step); when built
it checks the flag before every tick, per the approved plan. Until
then there is no auto tick running, so no live risk. The hub sets and
clears the flag around each ChatGPT test session.

## What the demo proved (runs/harness-demo/)

Dry runs of Lore's three real samples against the v1.6 400-tick DB.
Nothing was applied.

- **Sample A (Turn 131 vFINAL):** parses clean. Clocks are prose, not
  `Name value/max`, so they are carried as text and change no clock.
  Bonds match the seed. Diff on the 400-tick DB: Sledge 5 → 3 and
  Razor-Back 5 → 3 — a rewind, because Dream Share restored both to 5
  over 400 ticks while the block records the historical 3. The review
  caught it; nothing was applied. In live use the sweep applies to a
  world whose Bonds match the last played turn, so diffs are real
  changes, not rewinds. This is the review step earning its keep.
- **Sample B (Turn 136 vFINAL.5):** parses, then the validator refuses
  it outright — FROZEN_LIVE. All five sequel clocks flag as unknown in
  Fork A (correct: Fork A has the four fork clocks). The pending Krov
  decision is carried verbatim and never resolved.
- **Sample C (Turn 138 vFINAL.7, test timeline):** parses, five
  unknown-clock flags, no errors, same Bond rewind note as Sample A.
- **Handshake demo** (`handshake-fork-a.md`, from the v1.6 400-tick DB
  with Turn 131 carried state): 518 words, all 10 sections, 2 rumors
  (trade + raid near Great Basin, each labeled "Rumor (unverified):"
  and traced to a logged event), 0 clocks about to fire. This proves
  the generator. It is NOT the real first-turn handshake — the real
  one waits on Lore confirming where the test timeline resumes (see
  open items).

## Rejection handling (confirmed 2026-11-21, ChatGPT's recommendation)

Three kinds, handled differently. Full text in `readiness-report.md`.

- **Mechanical error.** The sweep refuses the block (validation
  error). ChatGPT revises the proposed state block while retaining the
  valid scene events, and resubmits. The review names exactly which
  fields failed.
- **Continuity error.** The block parses and validates, but the
  narrative contradicts established story. Muse flags the specific
  inconsistency in the hub review. ChatGPT corrects the affected
  narrative or state proposal WITHOUT silently rewriting other events
  — the correction must be visible in the next diff.
- **Unresolved disagreement.** Muse flags it in the hub with both
  sides stated. Bryan decides. Nothing applies until he does.

**State version on every proposal.** Every block carries its Turn and
State-Version. A proposal with a Turn OLDER than the last approved
turn is refused outright (`STALE_PROPOSAL` — an old proposal cannot
overwrite newer approved state). A proposal with NO State-Version is
refused outright (`NO_VERSION`). A same-turn re-sweep is a flag for
review. The review prints "Based on: Turn N vX | Last approved: Turn
M vY" on every run.

## Readiness

`readiness-report.md` is the standing readiness report: what is
ready, unresolved approvals and open items, the rejection handling,
and the first three-turn checkpoint defined as a formal acceptance
test (schema obedience, mechanical accuracy, continuity, no unapproved
state changes — actual failures recorded, no subjective score). The
checkpoint is built (`src/checkpoint.py` runs all four checks) and
rehearsed: a 3-turn loop on a test-DB copy (ForkA-vFINAL.1–.3, sweep +
tick + checkpoint) passed all four
(`runs/harness-demo/checkpoint-rehearsal/audit.md`). Note: the
rehearsal refreshed `runs/sweeps/turn-132/` with rehearsal records,
replacing the earlier synthetic demo record there; the demo checkpoint
keeps its own copies under `runs/harness-demo/checkpoint-demo/`.

## Open items (with Lore, hub copied)

All five harness questions ANSWERED by Lore (2026-11-21 ~00:53 EST):

1. **Where the test timeline resumes.** Restart from the fork: Fork A
   Turn 132 (ForkA-vFINAL.1), based on Turn 131 vFINAL. The Turn
   137–138 test timeline is closed (a DM capability test based on Turn
   136, which Bryan excluded). The harness tracks the four fork clocks
   only; the five sequel clocks do not exist in Fork A and the sweep
   correctly flags them as unknown. The test world starts FRESH from
   the v1.6 seed at tick 0 (Bonds Sledge 3, Razor-Back 3), NOT from the
   400-tick run DB. The Bond rewind in the demo is expected (historical
   blocks against a 400-tick DB) and the review correctly caught it —
   the system working, not a defect. **The DM's first block carries the
   four fork clocks in `Name value/max` form (all 0/6 at tick 0)** —
   they are the established clocks in Fork A (V2 spec: established
   clocks only, as `Name value/max`). **Confirmed YES by Lore
   (2026-11-21 ~01:00 EST), and the start pack fixed:**
   `chatgpt-fork-a-start.md` Part B now lists the four fork clocks
   (all 0/6) alongside the resolved campaign clocks (marked resolved,
   do not reopen), and Part A clarifies the state block's Clocks field
   carries the four running fork clocks — the resolved campaign clocks
   are context only, not running clocks. Verified in the file.
2. **Handshake split.** CONFIRMED: Engines, Pack, clocks, what moved,
   rumors, and clock warnings from the DB; scene, pending decision,
   resolved list, and watchlist carried from the last swept block.
   Plus: Vance location (and actor locations generally) come from the
   DB — implemented DB-first in `src/handshake.py` (carried only as a
   fallback when the DB has no location), with tests.
3. **Who pastes, and DM prompt change.** Bryan pastes for the test.
   Part A goes into the Project instructions (Bryan does this in the
   ChatGPT UI — he owns the account), then Part B as the first message
   in a new chat. Part B uses the `[SYSTEM_STATE_OVERRIDE]` wrapper.
4. **Checkpoint audit format.** CONFIRMED, plus four additions, all
   implemented: resources (non-negative; replay vs seed; Territory vs
   controlled counts), Pack membership and actor locations, state
   version (ledger vs last approved block), rumors trace to logged
   events (same extraction the handshake uses).
5. **Session flag for the test.** CONFIRMED: the hub owns setting and
   clearing `state/session.json` around each ChatGPT test session.

## What still needs building (approved Phase 2 plan, 2026-11-21 00:40 EST)

The Phase 2 plan is APPROVED, with Bryan's answers: 1 tick per day,
Fork A ticks daily first (live waits), sweep review-before-apply,
handshake pasted in by Bryan for the test with auto-deliver later,
narration deferred with no LLM picked yet. Under that approval:

- **Item 1, daily auto tick** — approved, not yet built. Next build
  step after this harness.
- **Item 4, Companion app integration** — approved, not yet built.
  Discovery step first (map the app's views and server actions).
- **Item 5, narration** — DEFERRED by Bryan. No LLM picked. Not built.

## Files

- `src/sweep.py` — V2 block parser, validator, diff, apply.
- `src/handshake.py` — 10-section handshake generator.
- `src/session.py` — session flag helpers (read; the engine never
  sets or clears the flag).
- `src/checkpoint.py` — every-3-turns audit (audit.md + state.json +
  state.sqlite + carried/).
- `state/session.json` — the flag file, currently closed.
- `state/ironwild-fork-a-test.sqlite` — the live test world DB
  (fresh v1.6 seed, tick 0, verified).
- `tests/test_sweep.py`, `tests/test_handshake.py`,
  `tests/test_checkpoint.py` — 19 tests.
- `runs/harness-demo/` — the three Lore samples, sweep reviews,
  carried state, the demo handshake, and the demo checkpoint (applied
  to a COPY of the test DB; the live test DB is still pristine).
- `src/run.py` — `sweep`, `handshake`, and `checkpoint` CLI
  subcommands.
