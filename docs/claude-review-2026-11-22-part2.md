# Claude review of the Living World Engine, part 2 — 2026-11-22

Pasted by Bryan from Claude after Claude read db.py, events.py, actions.py, auto_tick.py and schema.sql.

Engine verification (same day, in the Engine chat): the corrections mostly hold against the code on disk. Two of Claude's line-number sets do not match the files (auto_tick.py is 121 lines, events.py is 60 lines; his cites of 373/384/386 and 93-99/112-118/126-131 cannot be right — actions.py and db.py cites do match). The substance checks out. One framing correction: the concurrency hazard is real as a mechanism but not currently reachable (single writer; intake never writes the DB; daily auto-tick cron disabled). The live race is the registry clobbering, not the DB chain fork.

New Engine findings from the same verification: neither seed declares bond_recovery, so the DC-18 Bond gate in actions.py is dormant in both forks. Both forks' raid actions use two separate resource_add ops (Feed -2 from the victim, Salvage +2 to the raider), not resource_move — so raids do not conserve, and when the victim's Feed is clamped at 0 the raider still gains +2 Salvage from nothing.

## Corrections to what I said before

- **The RNG is worse than I described, in a different way.** The auto path seeds per tick (auto_tick.py:373), but the manual path re-seeds from `rng_seed` on every call (tick.py:169). So the same seed gives different worlds depending on the driver: manual, auto, or turn-driven. Adding `seed + tick` is also weak, because seed 5 at tick 3 equals seed 3 at tick 5. Hash the tuple instead.
- **The FK pragma is fine.** It's set per connection in `connect()` (db.py:19). I'm retracting that concern.
- **`created_at` is correctly excluded** from both hashes (db.py:10-11, events.py:93-99). But `score` and `runner_up`, your advertised audit trail, are also outside the chain hash. Dropping the triggers would let someone edit them undetected.
- **Non-halt exceptions roll back cleanly**, because `finally: conn.close()` discards the open transaction. The halt path, which commits a partial tick (tick.py:191), is the odd one out.

## Concurrency is confirmed

`db.connect` uses the default deferred, legacy transactions. `append_event` reads the last hash, then inserts (events.py:112-118). A second writer can sneak in between and fork the chain, and `verify_chain` (126-131) then reports it as tampering. With the poll, the cron tick and the CLI all writing, that is a realistic false alarm. The `apply_sweep` race stands too.

## New findings in `auto_tick.py`

- A halt never sets the once-per-day guard (386 runs only on success). Every retry consumes another partial tick, and the actors before the halting one act again each time.
- `verify_invariants` runs after the tick is already committed (384), so violations are only logged, never prevented.
- `set_meta(last_auto_tick_date)` lands after `run_ticks` commits (386-387), so a crash in between allows a second tick that day. It is the same non-atomic pattern as proposals.py.
- `last_auto_tick_date` is in `meta`, which `state_hash` covers (db.py:12). So the state hash depends on the calendar date, which contradicts the comment at db.py:10-11 and will break any golden-hash test run on different days.

## `actions.py`

Good:
- `when` clauses are evaluated against pre-action state (266-272), which gives each action clean atomic semantics.
- A missing target becomes a visible skipped op, not a silent one (282-287).
- `resource_move` conserves resources (74-78).
- `pack_merge_burn` breaks ties deterministically (135).
- The Bond rule is gated by `meta bond_recovery` (98-100), which is the right pattern for a reusable engine.

Bad:
- The docstring promises the log records "what really happened" (1-3). But `status_set`, `move` and `molt_trigger_set` (185-188, 215-233) log success even when the ID doesn't exist.
- `bond_add_pack` reads the pilot from `bonds.pilot_id` (115), a third place that disagrees with `engines.pilot_id`.
- `sweep.py:549` still writes Bonds directly, bypassing the DC-18 rule this file enforces.

**Open question:** whether a raid actually conserves resources depends on whether the seed's raid action uses `resource_move` or two separate `resource_add` ops. Send `seed/fork-a.json` and I'll check.

## Revised priorities

*Risks*
1. Concurrent writers: events.py:112-118, sweep.py:524-526, proposals.py:296-312, auto_tick.py:386.
2. Three RNG regimes and a shared stream: tick.py:97-103 and 169, auto_tick.py:373.
3. Silent-accept paths: sweep.py:123-147 (dropped clocks) and 371-387 (no gap check), plus actions.py status_set/move on a missing target.

*Improvements*
1. One transaction boundary per tick or sweep: `BEGIN IMMEDIATE`, invariants checked before commit, a halt that rolls back the tick and writes only a halt record, an `applied_turns` table, and a `UNIQUE` index on `events.prev_hash`.
2. One RNG scheme keyed on (seed, actor, tick) for every driver.
3. Strict validation (targets must exist, CHECKs on statuses and resource names), and the Ironwild constants moved into `meta` or the seed.

**New tests worth writing:** two connections appending events concurrently, a halt retried twice, equal state hashes across different dates, and a `status_set` on a typo'd ID.
