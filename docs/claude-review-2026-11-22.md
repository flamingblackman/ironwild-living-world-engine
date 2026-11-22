# Claude review of the Living World Engine — 2026-11-22

Pasted by Bryan from Claude. Claude read sweep.py, tick.py, proposals.py, auto_apply.py, resources.py (1,497 lines) by eye and ran nothing. `schema.sql` didn't come through in that chat, and Claude had not seen `db.py`, `events.py`, `actions.py`, `run.py` or the tests. Where a finding depends on those, Claude said so.

Engine verification (same day, in the Engine chat): the review is largely accurate. Confirmed against the code: RNG restart on the manual tick path, tie-only RNG draws, halt committing a partial tick, hardcoded Ironwild content (FROZEN_TURN, "Ironwild"/"Bryan", dream_share, Instinct Feed +2 / Hunger 4), no skip-ahead check in validate(), silent clock drops, diff-outside-transaction, DB/registry non-atomicity, registry stale-snapshot clobbering, approvals attested not enforced, _norm duplication, auto_apply reaching into handshake._STATUS_RE. Corrections: auto_tick.py DOES pass an RNG (Random(seed + tick), a second scheme distinct from the manual path); schema.sql was attached and exists at state/schema.sql (133 lines); the seed file is seed/fork-a.internal.json, not seed/fork-a.json; the halt-commit is deliberate by design, not an accident. The check-then-write race and crash windows are real but currently unreachable in practice (single writer, intake never writes the DB, daily auto-tick cron disabled).

## 1. Architecture

**Good:** `tick.py` is a clean, readable pipeline. The fixed step order, the halt-and-ask rule and the `_run_one_tick` split are all sound. `move_qty` (resources.py:31) moves only what exists, so transfers conserve resources. In `proposals.py`, re-downloading the Drive file and re-hashing it at apply time (279-287) closes a real race, and the proposal ID includes the content hash.

**Coupled:**
- `sweep.py` is five modules in one: parser, validator, differ, renderer and applier. It also writes bonds and clocks directly (529, 549), bypassing the Bond-increase guard that `tick.py:138` enforces.
- The proposal registry is a JSON file beside SQLite, so you have two sources of truth. `carried.json` (the auto-apply baseline) is also a file outside the DB.
- Ironwild is hardcoded in the core: `FROZEN_TURN` (sweep.py:37), `"Ironwild"` and `"Bryan"` (proposals.py:63, 273), `"dream_share"` (tick.py:138), and the Instinct rule, with Feed +2 and Hunger 4 (tick.py:212-234), which sits outside the catalog. That contradicts "every effect comes from the seed" and blocks your bare-bones goal.
- Smaller issues: `from src import` in some modules and `from .` in others. `_norm` is duplicated (sweep.py:56, auto_apply.py:256). `auto_apply` reaches into `handshake._STATUS_RE` (242).

## 2. Fragile spots

- **The RNG restarts on every `run_ticks` call** (tick.py:168-169). At 3 ticks per turn, each turn replays the same random sequence from the seed. Chunked ticking therefore differs from your 400-tick proof run, so "same seed, same world" only holds for uninterrupted runs. This assumes `auto_tick.py` doesn't pass in a persisted RNG, and I haven't seen it.
- **Draws happen only on ties** (tick.py:103), so the draw count depends on world state. Adding one NPC shifts every later tie-break.
- **A halt leaves a half-ticked world.** It commits the partial tick (185-192), and the tick number was already advanced (180). The actors who hadn't acted yet are skipped, and a resumed run never replays them.
- **Per-tick cost:** `_substitute` copies the whole catalog for every actor every tick (113). That is the first performance wall. Balance will break sooner, though: your own README shows Legion Feed hitting 0 on 74 of 400 ticks.

## 3. Apply pipeline: looks safer than it is

- **Out-of-order turns:** only the auto path enforces "next turn" (auto_apply.py:110). `validate()` rejects older turns (sweep.py:371) but has no check for skipping ahead, and an equal turn is only a flag (382). A Bryan-approved apply of Turn 145 when 138 was last swept will pass.
- **Silent drops look like carry-overs.** A malformed clock such as `Engine Awakening 2 / 6` becomes text with no finding unless all clocks fail (123-147, 323). The block then shows 0 changes and 0 findings and can auto-apply, with the real advance lost.
- **Check-then-write race.** The diff is computed outside the transaction (524), the transaction opens at 526, and `UPDATE ... SET value = ?` writes absolute values. A tick landing in between gets overwritten.
- **DB and registry aren't atomic.** The DB commits at proposals.py:296, but the registry is marked `applied` at 310-312. A crash in between lets the proposal be applied again.
- **Registry clobbering.** `registry` is loaded at 264 and saved at 312 as a stale snapshot, so anything the 15-minute poll registered meanwhile is lost. `intake_folder` does the same at 217/237.
- **Approvals are attested, not enforced.** `approved_by != "Bryan"` is a string compare (273). `lore_approval` is never checked against `record_lore_approval`'s file.

## 4. Tests I'd want (I haven't seen yours)

Chunked vs continuous tick equivalence. Turn-gap, duplicate-turn and revised-turn applies through the Bryan path. A mixed block with one malformed clock. Crash between DB commit and registry write. Concurrent poll during apply. Halt mid-tick, then resume. A golden-hash run of the real `seed/fork-a.json`. Bond 1→5 in one sweep.

## 5. Priorities

**Risks**
1. The RNG reset (tick.py:169, 97-103). It undermines determinism and your variable-tick plan.
2. The non-atomic apply: sweep.py:524-526 and proposals.py:296-312, 264/312.
3. Silent drops and missing gap checks: sweep.py:123-147, 371-387.

**Improvements**
1. Per-actor, per-tick RNG streams keyed on seed, actor ID and tick. Persist nothing.
2. Make apply one guarded unit. Take a write lock, re-validate inside it, make a turn gap an error, and put applied proposal IDs in a DB table with a unique constraint. The registry then becomes derived data.
3. Fail loudly on anything that looks like a clock or Bond but doesn't parse, and move the Ironwild constants into the seed.

If you send `db.py`, `events.py`, `actions.py`, `auto_tick.py` and `schema.sql`, I can confirm or retract the items marked as assumptions.
