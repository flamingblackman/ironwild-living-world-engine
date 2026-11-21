# Living World Engine — Phase 2 Plan

**Team:** Living World Engine Team
**World:** Ironwild (Fork A first; live world only after Turn 136 resolves)
**Status:** APPROVED by Bryan in the Fiction & Worldbuilding hub chat, 2026-11-21 00:40 EST, with the recommended answers: 1 tick per day, Fork A ticks daily first (live waits), sweep review-before-apply, handshake pasted in by Bryan for the test with auto-deliver later, narration deferred, no LLM picked yet. Building now.
**Date:** 2026-11-21

## 1. What Phase 2 proves

Phase 1 proved the loop on a fork: seed in, ticks out, event log and world view out, deterministic and honest. Phase 2 connects that loop to the way Bryan actually plays: the world keeps moving between sessions, a finished session lands in the engine as events, the next session starts from what the engine knows, and the Companion app shows the real world instead of a static proof.

Phase 2 is five items, in build order. Items 1–4 are the scope. Item 5 is optional and last.

1. **Daily auto tick.** The world ticks every day on its own, background only.
2. **Session-close sweep.** A finished Gemini session's Turn state block is parsed into engine events and fed into the world.
3. **Handshake back out.** The next session starts from an engine-generated handshake: what moved off-screen, what rumors are live, what clock is about to fire.
4. **Companion app integration.** The static world view becomes the real Companion view.
5. **Narration layer, optional.** Prose over the finished event log only. The engine still never writes state with an LLM.

## 2. Hard rules, carried over from Phase 1

- **Rules first, LLM second.** The tick loop is pure deterministic code. No LLM call ever writes state. The session-close sweep parses a state block; it does not let an LLM decide what happened. Narration is a separate render pass over the finished event log, and it is optional.
- **State database is the single source of truth.** One SQLite file per world. The event log stays append-only: a correction is a new event, never an edit.
- **The engine never invents canon.** Every actor, action, trigger, and material effect comes from Lore-supplied seed data or from a Turn state block Bryan played. If the engine needs a rule that is not in the seed or the block, it stops and asks.
- **The freeze is absolute.** Crown of Cold Iron is at Turn 136, vFINAL.5, with the Krov ambush decision pending. No Turn 136 state enters any engine world until Bryan resolves it. The auto tick never runs on a world with a pending player decision, and the sweep refuses a block from an unresolved Turn.
- **The engine never writes to canon files.** It reads the bibles, codices, and registry. It writes only inside `living-world-engine/`, plus the world-view exports the Companion app reads (section 6).
- **Open mysteries stay open.** Seed Core origins, the Deepmaw migration, a pilot whose Engine dies — the engine never resolves these, and neither the sweep nor the handshake may resolve them either.
- **The engine never writes the Companion app's database.** Integration goes through an export the Companion app reads (section 6). Direct writes to `app.db` are out of scope.

## 3. Item 1 — Daily auto tick

**What it is.** A scheduled runner that ticks the world once per day, headless, with no narration and no render until the end. One tick is one in-world day, so one tick per day keeps world time in step with real time.

**Which world ticks.** Fork A only, until the live world exists. The live world is seeded by Lore from the resolved Turn 136 state (same seed format as Fork A, new world_id) and starts auto-ticking only after that seed lands. The auto tick never starts on live canon before then.

**Guards.** Before every scheduled tick the runner checks two things and refuses to tick if either fails:
- No pending player decision on that world (the freeze guard). A world with an open decision does not tick.
- No session is currently open (the session flag, set by the hub/Lore when a session starts and cleared at session close — see section 9).

**What it records.** Each auto tick writes its events to the log, updates the state hash, and appends one line to a daily run log (`runs/auto/<date>/`) with tick number, event count, and any refused-tick reason. A refused tick is a normal outcome, not an error.

**What it never does.** It never ticks twice to catch up after a missed day (no catch-up ticks — a missed day is a quiet day, and the log says so). It never calls an LLM. It never touches the live Turn 136 scene.

## 4. Item 2 — Session-close sweep

**What it is.** Bryan plays a session in Gemini, the session ends, and the Turn state block from that session is parsed into engine events and fed into the world. This is the only way played story enters engine state.

**How it works, in order:**
1. **Input.** The Turn state block, in Lore's canonical format (section 9), plus the Turn number and the session's open/close markers.
2. **Parse.** A deterministic parser maps state-block fields to engine events: resource changes, location control changes, clock changes, NPC status changes, Bond changes, new actors or locations if the block names them. The parser is code, not an LLM. Fields it cannot map are listed as unmapped, never guessed.
3. **Validate.** Before anything lands: every referenced actor, location, faction, and clock must exist in the DB (or be declared new by Lore); no resource may go negative; no Bond may leave 0–5; no clock may exceed its max; no event may reference the frozen Turn 136 scene or resolve an open mystery. A failed validation stops the whole sweep — nothing partial lands.
4. **Review.** The parsed events are shown to Bryan/Lore as a plain list (what changed, old value → new value, per event). They land only on approval. This is the single biggest corruption risk in Phase 2, so the review step is not optional.
5. **Apply.** Approved events append to the log in one transaction. The sweep records its source (Turn number, session date, who approved) in the run log.

**What it never does.** It never applies a sweep from an unresolved Turn. It never invents an event for a state-block line it cannot parse. It never edits an existing event.

## 5. Item 3 — Handshake back out

**What it is.** Before the next session, the engine generates a handshake from the DB alone: a short summary the Gemini DM reads at session start so the story continues from where the world actually is.

**What it contains, and only what it contains:**
- **What moved off-screen.** Events since the last session, in plain language: which actors acted, what changed, territory flips, clock completions.
- **Rumors live.** Derived from events only, each marked as a rumor, never as confirmed fact. Rumor rules come from Lore (section 9).
- **Clocks about to fire.** Any clock within 1 of its max, with its current value and what fires on completion.
- **World state snapshot.** Current tick and era, Pack and Bond table, resource totals — the same numbers the world view shows.

**What it never does.** It never invents an event, a rumor with no source event, or a clock value. It never names an era (Lore names eras). It never resolves an open mystery. The handshake is generated, shown to Bryan/Lore for a glance, and handed to the DM — it is not canon until Bryan plays it.

## 6. Item 4 — Companion app integration

**What it is.** The Companion app (`~/workspace/ts-spaces/campaign-companion`, a TypeScript space with client + server + `app.db`) shows the real world: event feed, timeline, faction dashboards, clocks, Pack and Bond table, resource totals. The Phase 1 static HTML view becomes the live in-app view.

**How it connects.** The engine publishes a stable export per world after every tick and sweep — a JSON snapshot (`runs/<world>/world-view.json`) plus the event feed — and the Companion app reads it through its own actions. The engine never writes to `app.db` directly and never edits the Companion app's code outside its declared actions. The export format is a contract: the engine owns the fields, the Companion owns the display.

**Discovery step first.** Before building, the engine maps the Companion app's current state: what views exist, what its server actions already read, and how a world-view feed plugs in. If the app needs a change the engine cannot make through its declared actions, that change is a hub question, not something the engine improvises.

**What Phase 2 shows, and what it does not.** Phase 2 shows location and territory changes as data — tables, feed entries, timeline markers. The DYNAMIC MAP (a wiped-out continent, flipped territory, fallen den visible on the map) is Phase 4, not Phase 2, per Bryan's Phase 1 ruling. Phase 2 records the state the map will later render; it does not build the map.

**Fallback.** The static HTML world view keeps generating after every run, so the world is always viewable even if the Companion integration is down.

## 7. Item 5 — Narration layer, optional

**What it is.** A render pass that turns the finished event log into prose for Bryan to read — the same events, in sentences. It runs after a tick or sweep completes, over the log only.

**Rules.** The narrator reads events and writes prose. It never writes state, never edits the log, never adds an event. Its output is labeled narration, not canon. It uses the LLM the hub picks (see open question 5); the engine does not pick it. If the hub defers narration, Phase 2 ships without it and nothing else changes.

## 8. File layout (additions to Phase 1)

All under `~/workspace/giant-robot-multiverse/living-world-engine/`:

```
living-world-engine/
  phase-2-plan.md         — this plan
  src/
    auto_tick.py          — scheduled runner: guards, tick, daily run log
    sweep.py              — state-block parser + validator + applier
    handshake.py          — handshake generator from the DB
    export.py             — world-view JSON export for the Companion app
    narrate.py            — narration render pass (item 5 only, if built)
  runs/
    auto/<date>/          — one folder per auto-tick day: tick log, hash
    sweeps/<turn>/        — one folder per sweep: parsed events, review, approval
    handshakes/<turn>/    — generated handshake + what the DM received
    <world>/world-view.json — Companion export, regenerated after every tick/sweep
  tests/
    test_auto_tick.py     — guards refuse a pending decision / open session; no catch-up ticks
    test_sweep.py         — real state block parses to exact events; bad block fails validation, nothing lands
    test_handshake.py     — handshake contains only DB facts; rumors marked; clocks within 1 flagged
    test_export.py        — export matches the DB; Companion reads it (fixture)
    test_narrate.py       — narration changes no state (item 5 only)
```

Stack stays Python 3 + SQLite, standard library only, plus the existing scheduler (cron) for the daily tick. No new services.

## 9. What the Engine Team needs from the Lore Team

Nothing in items 2–3 starts until these land. Item 1 can be built and validated on Fork A without them.

1. **Canonical Turn state block format.** The exact fields, their types, and what each one means — plus 2–3 real sample blocks (Turn 131 vFINAL and two recent Turns) so the parser is built against real data, not a guess.
2. **Handshake format.** What the Gemini DM expects at session start: the shape it reads, which fields it needs, and how long it should be.
3. **Rumor rules.** What the engine may surface as a rumor, what it must never rumor, and how a rumor is worded so it is never mistaken for fact.
4. **Live-seed trigger.** Confirmation that once Bryan resolves Turn 136, Lore supplies a live seed in the Fork A format (new world_id), and that the auto tick starts on live only then.
5. **Session open/close signal.** How the engine knows a session is live so the auto tick stays out — who sets the flag, where it lives, what happens if it is never cleared.
6. **Companion app.** What Lore knows about who owns the Companion app build and how the engine's export should reach it (file the app reads, or an action the app calls).

## 10. Acceptance checks (frozen before build)

Phase 2 is done when all of these pass, with zero canon files touched and the freeze intact:

- [ ] Auto tick: a scheduled run ticks Fork A once, logs the tick, and refuses a world with a pending player decision and a world with an open session. A missed day produces no catch-up tick. Determinism holds (same seed, same events).
- [ ] Sweep: a real Turn state block parses into engine events that reproduce the block's numbers exactly. A block with an unknown actor, a negative resource, or a Bond outside 0–5 fails validation and nothing lands. A sweep from an unresolved Turn is refused.
- [ ] Sweep review: parsed events are shown as old → new before applying, and nothing applies without approval.
- [ ] Handshake: generated from the DB alone; every line traces to a logged event; rumors are marked as rumors; every clock within 1 of max is flagged; no invented canon, no named era, no resolved mystery.
- [ ] Companion: the Companion app shows the live world view (event feed, timeline, faction dashboards, clocks, Pack and Bond table, resource totals) from the engine export. The engine never writes `app.db` directly. The static HTML view still generates as fallback.
- [ ] Narration (only if built): prose is generated from the event log only; state is byte-identical before and after narration.
- [ ] No canon writes: the bibles, codices, registry, and gem files are byte-identical before and after every Phase 2 run.

## 11. What Phase 2 is not

- Not the dynamic map. Location and territory changes are shown as data; the map is Phase 4.
- Not a DM replacement. The engine hands the DM a handshake; the DM still runs the session. The ChatGPT DM test stays the Lore Team's track.
- Not the live timeline yet. Fork A ticks daily first. Live starts only after Bryan resolves Turn 136 and Lore seeds it.
- Not a rewrite of Phase 1. The tick loop, scoring, clocks, eras, and append-only log do not change. Phase 2 adds runners and readers around them.

## 12. Open questions for Bryan (hub decides)

1. Daily tick rate: 1 tick per day (world time = real time). Keep, or a different rate?
2. Which world ticks daily first: Fork A only until the live world is seeded, or wait and start on live?
3. Session-close sweep: review-before-apply as written, or auto-apply on a trusted format? (Engine recommends review — one bad parse can corrupt the live DB.)
4. Handshake delivery: does the DM get it automatically at session start, or does Bryan paste it in?
5. Narration: build it in Phase 2, or defer it to Phase 3? If built, which LLM narrates?

## 13. Approval

APPROVED (Bryan, 2026-11-21 00:40 EST, in the hub). The five open
questions answered:
1. Tick rate: 1 tick per day. Keep.
2. Which world ticks daily first: Fork A only until the live world is
   seeded. Live waits.
3. Session-close sweep: review-before-apply. Keep.
4. Handshake delivery: pasted in by Bryan for the test, auto-deliver
   later.
5. Narration: deferred. No LLM picked yet.

Build is underway. The shared-state test harness (items 2–3, ChatGPT
DM + Muse controller, Fork A only) was delivered first; see section
14. Item 1 (daily auto tick) and item 4 (Companion integration) are
the next build steps under this approval.

## 14. Build status

**Plan delivered (2026-11-21 ~00:31 EST).** Phase 2 approved to start by Bryan in the hub, 2026-11-21 00:31 EST. Plan written and reported to the hub; Lore asked directly for the six inputs in section 9, hub copied. Build waits on Bryan's approval of this plan in the hub.

**Guard question DECIDED (Bryan, 2026-11-21 00:48 EST): keep the
pending-decision guard as written.** The world freezes on a pending
decision. This overrules Lore's recommendation to narrow it to the
Turn 136 freeze only (Lore's read arrived ~00:59 EST, after Bryan's
decision). No plan change; the code already implements the guard as
approved. Lore confirmed the same decision directly (~00:59 EST) and
withdrew the narrowing recommendation; the guard is as built, and the
Turn 136 freeze stays absolute as a separate rule. Auto tick stays
DISABLED until the first test session opens,
then ticks Fork A once per day under that guard and logs the guard
state every run.
Against `state/ironwild-fork-a-test.sqlite`: world ironwild-fork-a,
source Turn 131 vFINAL (v3.00.2), rng seed 131, tick 0; four fork
clocks all 0/6 running; Bonds sledge 3 (pilot Brigus), skytalon 5,
razor-back 3, goliath 5, strider 5 (only Brigus–Sledge pilot assigned,
as in the seed); 0 events; all five Engines exhausted; session flag
closed. The Fork A handshake in `chatgpt-fork-a-start.md` Part B
matches the DB exactly. Lore confirmed all six setup answers and
restated the five harness answers (restart from the fork; handshake
split with Vance from the DB; Bryan pastes, Part A into the Project
instructions first; checkpoint list with four additions; hub owns the
flag). The test world is ready for the first turn. Remaining blockers:
Bryan pasting the start pack, the guard question, enabling the
auto-tick schedule.
Lore answered all five: restart from the fork (Turn 132,
ForkA-vFINAL.1; Turn 137–138 timeline closed; four fork clocks only;
fresh from the v1.6 seed at tick 0; the demo Bond rewind is expected
and the review catching it is the system working); handshake split
confirmed, plus actor locations from the DB — implemented DB-first in
`src/handshake.py` with tests (carried only as a fallback); Bryan
pastes, Part A into the Project instructions by Bryan in the ChatGPT
UI, Part B as the first message in a new chat; checkpoint format
confirmed plus four additions — implemented in `src/checkpoint.py`
(resources incl. seed+event replay, Pack + actor locations, state
version, rumors with source event ids) and re-rehearsed (acceptance
still PASS; replay 0 mismatches); session flag confirmed as hub-owned.
**Territory limitation surfaced:** no event op updates Territory on a
location flip, so Territory rows are seed values (Breakers 0 while
controlling 2, Dust Baron 0 while controlling 1, in the rehearsal).
The checkpoint shows the staleness plainly; fixing it is an
engine/seed change for a future version, not a silent patch to the
accepted v1.6 run. The resources verdict is separate from the
acceptance verdict. **84 tests pass.** Remaining blockers to the first
turn: Bryan pasting the start pack (Part A into the Project
instructions, Part B as the first message), the guard question, and
enabling the auto-tick schedule. Next build step: item 4 (Companion
integration, discovery first).

**First real sweep — revised Turn 132 (2026-11-21 ~01:00 EST).**
Bryan played "Divide the work!" in the Ironwild Handshake chat;
ChatGPT replied with a REVISED Turn 132 proposal (still
ForkA-vFINAL.1, Turn 132 — a same-turn revision, not Turn 133). The
block reached the Engine Team as a summary only, not as text; the
literal block was recovered from the hub's browser-task handoff and
saved to `runs/sweeps/turn-132/revised-block.txt`. **Process
correction, stated plainly:** the hub told Bryan the sweep was "in
flight" and Turn 132 was "being applied" before the Engine Team had
the block or ran anything — neither had happened. The test DB was
still tick 0, 0 events, Recovery 0/6, Legion Salvage 12. Bryan's
earlier "i approve" was given on the hub's summary, not a sweep
review. The formal dry run below is the first review; nothing is
applied until Bryan approves THIS review. **Parser fixes the real
block exposed:** (1) `_parse_clocks` split only on `|`, but the DM
uses `;`, and a "(proposed, pending approval)" parenthetical broke
the match — the first dry run flagged NO_CLOCKS_PARSED and saw no
changes; fixed to split on `|` and `;`, parse matching segments,
carry prose segments as text, allow any parenthetical (only
Complete/Detonated count as status). (2) `_parse_bonds` split only
on `;`/`.`, so the "Five Engines, all exhausted and battered:"
preamble made the first Bond name "Five Engines" (ENGINE_UNKNOWN);
fixed to treat `:` as a boundary. 3 new tests; **87 tests pass.**
Corrected dry run: Turn 132 ForkA-vFINAL.1, 1 change (Great Basin
Recovery 0 → 1), Findings: none, Bonds all match, decision resolved
(none), trade-off carried, resolved prose clocks carried as text.
**Open question for Bryan/Lore:** the first proposal's Legion
Salvage 12 → 11 is NOT restated in the revised block, and the V2
block has no Resources field — the sweep cannot confirm or apply a
resource change. Is the expenditure still intended (and if so, how
does it land), or dropped? Also: the session flag was never set open
around the ChatGPT session (closed throughout; no harm, auto-tick
disabled, nothing ticked) — the hub must set it around the next
session. The rehearsal's `runs/sweeps/turn-132/applied.json` +
`carried.json` were renamed to `*-rehearsal.json` so they no longer
falsely claim an application; the rehearsal record lives in
`runs/harness-demo/checkpoint-rehearsal/`.

**All open items closed (Lore, 2026-11-21 ~00:59 EST).** The Fork A
handshake is supplied (Part B, delivered 00:40 EST, in the
[SYSTEM_STATE_OVERRIDE] wrapper, verified against the pristine tick-0
test DB); `lore-phase-2-inputs.md` section 1 is the canonical V2 spec
and the start pack's Part A is the same spec adapted for ChatGPT;
rejection handling confirmed as implemented (incl. the continuity
piece: a flagged narrative inconsistency is corrected only in the
flagged part, and the next diff must show it); handshake split, who
pastes, checkpoint format with four additions, hub ownership of the
flag, and the guard decision are all confirmed. No further action is
needed from Lore. The remaining steps are Bryan's: Part A into the
Project instructions, Part B as the first message in a new chat, and
the first test session opening — then the auto-tick schedule enables.

**Alignment question answered YES + start pack fixed (Lore, 2026-11-21
~01:00 EST).** The DM's first block carries the four fork clocks in
`Name value/max` form (all 0/6 at tick 0) so the sweep tracks them.
Lore confirmed the catch was correct — the handshake had listed only
the resolved campaign clocks in prose, and the DM would not have
known the four fork clocks exist — and fixed `chatgpt-fork-a-start.md`:
Part B now lists the four fork clocks (all 0/6) alongside the resolved
campaign clocks (marked resolved, do not reopen), and Part A clarifies
the state block's Clocks field carries the four running fork clocks.
Verified in the file. The distinction: Turn 131's block carries the
resolved campaign clocks (campaign-end state); Fork A Turn 132's block
carries the four fork clocks (the fork's running state). All four asks
confirmed done by Lore (readiness report delivered; rejection handling
in full incl. NO_VERSION and STALE_PROPOSAL; checkpoint rehearsed
PASS; test DB still pristine).
Lore delivered `chatgpt-fork-a-start.md` (V2 spec Part
A + initial handshake Part B); verified against the seed snapshot
(Bonds 3/5/3/5/5, Pack, Vance at Great Basin, Rift-King dead,
Skytalon adult, Sledge Titanium-Cestus, Goliath mortar pod destroyed
Turn 112 — all match; no Turn 136 state, no new canon). Versioning
`ForkA-vFINAL.<k>` parses and stores cleanly. Rejection rule
implemented in full: `STALE_PROPOSAL` (older Turn refused) plus
`NO_VERSION` (a block with no State-Version refused); staleness
judged by Turn, version string recorded and shown. Every sweep now
persists its review (`runs/sweeps/turn-<n>/review.json`; parse
failures go to `runs/sweeps/rejected/`) so the checkpoint can count
schema obedience. Checkpoint built as the formal acceptance test
(`src/checkpoint.py`: schema, mechanical, continuity incl. a
freeze-term scan, no-unapproved-state incl. hash chain + known-action
set + sweep-source records). Rehearsed end to end on a test-DB copy:
ForkA-vFINAL.1–.3, 3 sweeps + 6 ticks, acceptance PASS on all four
checks. **79 tests pass.** Readiness report updated: the handshake is
supplied and no longer gating; the remaining blocker to the first turn
is Bryan pasting the start pack into the Test Project chat. One
alignment question to Lore: the fork clocks in the DM's first block.
Next build step: item 4 (Companion integration, discovery first).
ChatGPT agreed to the architecture (DM under Muse-as-controller,
Fork A only, strict isolation, V2 compliance, propose-never-apply,
checkpoint every 3 turns, player agency) and raised one issue:
rejection handling. Confirmed as specified — mechanical errors get a
revised block retaining valid scene events, continuity errors get a
targeted correction without silently rewriting other events,
unresolved disagreements go to Bryan, approved changes commit and
produce the next handshake. Implemented: `STALE_PROPOSAL` error (an
older Turn never overwrites newer approved state), same-turn re-sweep
stays a review flag, and every review prints "Based on: Turn N vX |
Last approved: Turn M vY". `readiness-report.md` written: status READY
FOR THE FORK A HANDSHAKE, readiness checks, seven unresolved
approvals/open items (gating: Lore's handshake not yet supplied),
rejection handling, and the first three-turn checkpoint defined as a
formal acceptance test (schema obedience, mechanical accuracy,
continuity, no unapproved state changes — actual failures recorded, no
subjective score). **77 tests pass** (75 + 2 sweep). Lore asked for:
the Fork A handshake (gating), V2 spec handover confirmation, the
rejection handling, and the remaining open items. Next build step:
item 4 (Companion integration, discovery first).
`src/auto_tick.py` + CLI (`auto-tick` subcommand): ticks Fork A once
per day, headless, no LLM, no catch-up ticks, at most once per day
per world (meta `last_auto_tick_date`). Guards as approved: refuses
when a session is open (`state/session.json`), when a pending player
decision is recorded in meta (`pending_decision`, set by the sweep at
apply time and cleared when a later block resolves it), and when the
world already ticked today. RNG seeded from rng_seed + tick number, so
each day is deterministic but distinct. Each run writes
`runs/auto/<date>/tick.log` plus a world view on success; a halt
exits 2 like the manual tick. **75 tests pass** (71 + 4 auto-tick).
Demo on a test-DB copy: tick 1, 0 → 11 events; same-day rerun
refused. Schedule saved as `ironwild-fork-a-daily-tick` (daily,
runtime picked ~6:04 PM ET) but DISABLED until the first test session
is set up — ticking now would move the world under Lore's starting
handshake. Enable condition: Lore's Fork A handshake lands and the
first test session opens, or Bryan says go. **Guard consequence,
flagged for the hub:** as approved, the pending-decision guard freezes
the world whenever a turn ends with an open decision — which is most
turns. The runner logs the guard state every run so the question can
be answered from the log. Whether the guard should narrow to the Turn
136 freeze only is Bryan's call. Next build step: item 4 (Companion
integration, discovery first). Lore's six
setup questions answered (hub copied). Fresh test DB created and
verified: `state/ironwild-fork-a-test.sqlite`, v1.6 seed, tick 0,
source Turn 131 vFINAL, four fork clocks at 0/6, Bonds 3/5/3/5/5,
0 events, hash chain OK, invariants clean. Fresh start confirmed —
NOT a continuation of the Turn 137–138 test timeline; the DM must be
briefed the world is Fork A with the four fork clocks. Checkpoint
built: `src/checkpoint.py` + CLI, `runs/checkpoints/turn-<n>/` with
state.sqlite, audit.md, state.json, carried/; proved end to end on a
DB copy (synthetic Turn 132 sweep applied, 2 changes, audit all MATCH,
0 drift; live test DB still pristine). **71 tests pass.** Session flag
`state/session.json` in place and closed; the sweep enforces it now,
the auto tick (not yet built) will check it before every tick per the
approved plan. Remaining Lore items: the handshake split, who pastes /
DM prompt change, checkpoint format confirmation, hub ownership of the
flag. Next build step: item 1 (daily auto tick).
Bryan's call in the hub: set up the simple shared-state version —
ChatGPT is the DM, Muse is the campaign controller, the engine is the
shared ledger; Fork A test world only, existing Ironwild Test Project
on ChatGPT Plus (paccman360), NOT live Gemini canon, NOT Turn 136. No
live browser link, no custom two-agent app, no auto-apply. Built:
`src/sweep.py` (V2 `[TURN STATE]` parser — literal labels only,
pipe-joined fields, Bond extraction, clock-name mismatch flagged
never reconciled, clock decreases are errors, Turn 136 vFINAL.5
refused outright — plus validator, old-to-new diff, and an
approval-gated apply in one transaction), `src/handshake.py`
(10-section generator from the DB + carried state, rumors from logged
events only, deduplicated, always labeled "Rumor (unverified):",
clocks within 1 of max flagged as warnings, ~400–600 words),
`src/session.py` + `state/session.json` (flag file, currently closed;
hub/Lore sets and clears it, the engine never does),
`tests/test_sweep.py` + `tests/test_handshake.py` (18 tests),
`test-harness.md` (the turn loop, the checkpoint rule, the first test
turn). **70 tests pass** (52 Phase 1 + 18 harness). Demo
(`runs/harness-demo/`): all three Lore samples dry-run against the
v1.6 400-tick DB, nothing applied — Sample A parses clean (clocks are
prose, carried as text), Sample B refused as frozen live, Sample C
flags five unknown clocks; all three show a Bond rewind (Sledge and
Razor-Back 5 → 3) that the review caught, because the 400-tick DB
restored both to 5 while the blocks record the historical 3. Demo
handshake from the v1.6 DB: 518 words, all 10 sections, 2 rumors,
0 clocks about to fire. The demo handshake proves the generator; the
real first-turn handshake waits on Lore confirming where the test
timeline resumes. Open items with Lore: test-timeline resumption point
and which clocks the harness tracks, the handshake split, who pastes
and whether the DM needs a prompt change, the checkpoint audit format,
and hub ownership of the session flag. Next build steps under the
approved plan: item 1 (daily auto tick), then item 4 (Companion
integration). Item 5 (narration) deferred by Bryan.

**Turn 132 APPLIED + Turn 133 handshake delivered (2026-11-21
~01:03 EST).** Bryan approved the revised Turn 132 review (00:56
EST): Recovery 0 → 1, Legion Salvage 12 → 11, decision resolved,
trade-off carried. Applied in ONE transaction via the new
`--resource-change` path (the V2 block has no Resources field, so
the approved Salvage move lands as an explicit resource change,
validated against the DB's current value, one `sweep_resource`
event with applied_qty -1; 2 changes, 3 events, hash chain OK,
last_swept_turn 132, pending_decision ''). Then 3 ticks (tick 3,
invariants clean, 37 events) and the Turn 133 handshake generated
(`runs/handshakes/turn-133.md`, 515 words, 3 rumors, 0 clocks about
to fire). **Handshake fixes the first live handshake exposed:**
(1) skipped ops rendered as if they applied — the first draft
claimed the tick-3 raid was "blocked" although it had LANDED (the
when clauses passed before the Basin was fortified at tick end);
`_effect_text` now returns None for skipped ops and both callers
filter them. (2) the resolved list and watchlist read "not recorded"
(the V2 block has no such fields) — they now default to Lore's
stated constants from the Phase 2 inputs. (3) the PC line cut
mid-word ("Gold Sledg") — it now cuts at a word boundary. (4) the
move op rendered as raw JSON — it now reads "high_baron:
great_basin -> rust_dunes". 3 new tests; **92 tests pass.**
World after Turn 132 + 3 ticks: Recovery 6/6 Complete (Basin
fortified), Retaliation 1/6, Legion Feed 4 / Salvage 1, Pack Feed 4 /
Salvage 4, Bonds 3/5/3/5/5. Note (not a bug, per the adapter notes):
the Pack's share of fortify costs never landed — the Legion pays
first, the Pack only when the Legion holds none, and the Legion held
Salvage on all five fortifies. The automatic-loop question is
separate: Bryan flagged it, approval gate unchanged, nothing
auto-applied. Next: Turn 133 in ChatGPT; first 3-turn checkpoint
after Turn 134. **Lore re-confirmed at ~01:08 EST** (duplicate of
the earlier report): five harness answers implemented, Territory a
known wart for v1.7, applied_qty fix correct. Told Lore directly
the timeline has moved on — Turn 132 applied, Turn 133 handshake
delivered, the "remaining blocker" (Bryan pasting) already passed.

**Salvage correction (2026-11-21 ~01:08 EST).** Bryan's 01:03 EST
approval of the formal review was clock-only ("salvage stays at
12"); the 00:56 EST approval it superseded had included Salvage
12 → 11, and that -1 had already been applied (event 2). Corrected
append-only: Legion Salvage +1 (events 38–39: sweep_resource with
applied_qty +1, source_turn 132, plus a note event explaining the
reversal), recorded in `runs/sweeps/turn-132/correction.json`.
Legion Salvage now 2 — the correct clock-only value after 3 ticks.
Replay proof the tick history is unaffected: the +1 offset changes
no trigger or score (the tick-3 scavenge fired at Salvage 0 and
would fire at 1, both < 4; every fortify/trade threshold passed
under both bases). The clock was NOT applied twice (event 1 stands;
a re-apply would refuse with CLOCK_DECREASE, Recovery 6/6 vs the
block's 1/6). Ad-hoc checkpoint run (`runs/checkpoints/
turn-132-applied`): schema obedience PASS, no unapproved changes
PASS, resource replay 0 mismatches — but acceptance FAIL on 2
drift lines, both legitimate tick movement after the sweep
(Retaliation 0 → 1, Recovery 1 → 6). **Open item for the formal
3-turn checkpoint:** the drift check must distinguish tick movement
(expected) from unexplained drift, or it fails every live
checkpoint. Handshake fix: sweep-actor events no longer leak into
"What moved off-screen" (the correction events briefly did); the
Turn 133 handshake is unchanged at 515 words. **93 tests pass.**

**Rebuild after the clock-only approval (2026-11-21 ~01:11 EST).**
The hub stopped the paste: two defects. (1) Salvage: the +1
correction fixed the LEVEL but not the HISTORY, and my "identical
history" claim was WRONG — the re-run proves it. The hub demanded
the 3 ticks re-run from the corrected state, and the re-run
genuinely differs: Vance chose repair_engine at tick 2 (instead of
hunt), which completed Recovery a tick early (tick 2, not 3),
field-patched Goliath, and left the tick-3 raid BLOCKED (Retaliation
0/6, not 1/6). The +1 Salvage changed Vance's choice through
scoring, which my trigger-only replay did not check. The hub was
right to demand the re-run. Rebuilt: the erroneous DB + applied
record are preserved (`runs/sweeps/turn-132/
test-db-before-rebuild.sqlite`, `applied-erroneous.json`,
`correction.json`), then re-seeded from v1.6, applied clock-only
(1 change, 2 events, Recovery 1/6, Salvage 12), ticked 3. Corrected
state: tick 3, 36 events, Recovery 6/6 Complete (tick 2),
Retaliation 0/6, Legion Feed 4 / Salvage 3, Pack Feed 3 / Salvage 4,
Bonds 3/5/3/5/5, hash chain OK, invariants clean. (2) PC line: the
200-char cap cut it at "Gold" — removed; the handshake now carries
the FULL Player line, verified verbatim against the revised Turn 132
block. Corrected handshake: 589 words, 3 rumors, 0 clocks about to
fire, 19 off-screen lines (word budget trimmed the oldest tick-2
line). The ad-hoc checkpoint from the old DB is superseded by the
rebuild; the formal checkpoint still runs after Turn 134. **Lore
verified the rebuilt state independently at ~01:13 EST and corrected
its own stale record on it** (tick 3, 36 events, Retaliation 0/6,
Recovery complete at tick 2 event 25, Legion Salvage 3, tick-3 raid
blocked with ops skipped, applied.json clock-only). Remaining
blocker: hub confirms the corrected handshake, then Turn 133 is
played in ChatGPT.

**Stage 1 approved + 1A built and passed (2026-11-21 ~01:15–01:22
EST).** Bryan approved Stage 1 keeping review-before-apply, split
into 1A (Engine-side automation) and 1B (ChatGPT integration, only
after 1A passes, demonstrated E2E on his account). Design in
`stage-1-plan.md`. 1A built: Drive inbox/outbox folders under the
Ironwild Canon folder (personal Gmail); `src/drive_io.py` (Drive CLI
wrapper); `src/proposals.py` (proposal registry, unique ID
prop-<turn>-<hash8>, Fork A identifier check — Universe Ironwild +
State-Version ForkA-vFINAL.<k>, intake-only so the manual sweep
path keeps accepting the historical samples; approval binding:
apply by proposal ID only, approver must be Bryan, Drive file
re-hashed at apply, held-then-restored revives on re-intake);
`run.py` intake + apply-proposal commands, handshake --outbox
upload, env-scoped runs/proposals dirs for tests. **1A acceptance
PASSED on a scratch DB:** synthetic Turn 133 proposal through
intake → tamper refusal (hash mismatch, no state) → revive → atomic
apply (Retaliation 0 → 1, binding recorded) → 3 ticks → handshake
generated + uploaded to the outbox (578 words). Live test DB
untouched (tick 3, 36 events); test files trashed; inbox/outbox
empty again. **103 tests pass.** Poll cron created ENABLED:
`ironwild-fork-a-proposal-intake`, every 15 min, first run ~01:31
EST — it is the primary intake for 1A (no Drive webhook exists in
the connector surface); it stays as the recovery net if 1B adds an
event-driven path. Known wart: re-uploading a handshake creates a
duplicate in the outbox (upload always creates, never updates).
1B mechanism undecided, investigation pending after 1A (ChatGPT
Drive connection first, then GPT Actions, then browser UI as a last
resort). **Lore verified the corrected Turn 133 handshake at ~01:23
EST** against the live DB (589 words, tick 3, all sections match;
tick-3 raid correctly BLOCKED, Recovery complete at tick 2, rumors
trace to events 30/29/27). One note, not a blocker: the off-screen
list covers the most recent 20 events (ids 17–36), so tick 1 is not
in "what moved" — the state sections carry the full current state.
Recorded as a known limitation, not a defect.

**Design objective (Bryan, 2026-11-21 01:18 EST): Story-First,
Automation-Heavy RPG.** The player plays; ChatGPT is the primary
DM; Muse is controller and auditor; the Engine owns persistent
state; Lore owns the mechanics specs. State tracking, validation,
clocks, resources, continuity, handshakes, error recovery, and
session records move toward automatic, so the player never
transports V2 blocks, manages DB updates, or approves trivial
bookkeeping. **The approval gate does NOT change:** every apply
still needs Bryan's explicit tap, bound to the exact proposal
revision, until he defines and approves limited standing
permissions for routine changes — and major/irreversible changes
keep explicit approval even then. Exception-first interface (admin
info only when something needs attention); three-turn audits stay.
Recorded as section 0 of `stage-1-plan.md`, governing Stage 1
design. Turn 133 priority and Fork A scope unchanged.

**Turn 133 applied + Turn 134 handshake (2026-11-21 ~01:24 EST).**
Bryan approved Turn 133; applied in one transaction, 0 changes
(the block matched the DB), sweep note event 37, last_swept_turn
133 ForkA-vFINAL.2, pending decision recorded verbatim. Then 3
ticks (tick 6, 70 events, invariants clean, hash chain OK): Sledge
Bond 3 → 4 (Dream Share), Razor-Back field-patched, clocks
unchanged, Legion Feed 4 / Salvage 3, Pack Feed 3 / Salvage 4.
Turn 134 handshake generated (589 words, 2 rumors, 0 clocks about
to fire) and uploaded to the Drive outbox. **Correction sent to the
hub the same turn:** my first paste of the handshake re-typed the
off-screen list and added a phantom "Tick 6 — kaelen feed_engine"
line plus duplicated tick-6 lines; the file was correct, my message
was not. The corrected text (17 off-screen lines) was sent
immediately. Lesson, same as the Salvage stop: never re-type a
handshake — copy the file text exactly.

**Stale Bond in the Turn 134 handshake — fixed at the generator
(Lore caught it, 2026-11-21 ~01:28 EST).** The PC line said Sledge
Bond 3/5 while the DB and the Engines section said 4/5 (Dream
Share restored +1 at tick 5, event 51, Pack Feed −2, after Turn 133
was swept). My "designed split" framing was wrong — two values for
one Bond is a defect. Fix in `src/handshake.py`: the generator now
draws the PC line's Bonds from the DB (first "Bond N/5" after each
engine's name, before the next engine's name), and drops the
carried "All Engine Bonds unchanged." claim when a Bond moved.
105 tests pass (2 new). Regenerated: 597 words, 18 off-screen
lines, Sledge 4/5 in both places, verified by diff (only the PC
line + one more tick-5 line changed). Stale outbox copy trashed;
the outbox holds exactly one turn-134.md, the corrected one.
