# Step 1 slice 2 — build plan (approved 2026-11-22)

Scope: one RNG scheme for every driver. No seed-content change,
no scoring change, no tick-order change. All 180 existing tests
must keep passing (the wrapper tests pin their DBs to v1 — see
below).

## The problem (audit item 5, confirmed)

Three drivers, two schemes. The manual `tick` command and the
turn-driven tick both re-seed `Random(rng_seed)` per call, so
every turn replays the same draw sequence. `auto_tick` seeds
`Random(seed + tick)`, a second scheme, and it collides
(seed 5 tick 3 = seed 3 tick 5 = Random(8)). Chunked ticking
does not equal one continuous run. Adding one NPC shifts later
tie-breaks for everyone, because the draws come from one shared
stream. Fork A has 24 of 25 actions at weight 5, so tie-breaks
are the main decision-maker.

## The scheme (v2)

`rng_for(rng_seed, actor_id, tick)` in `src/tick.py`: a
`random.Random` seeded from `sha256("seed|actor_id|tick")`,
first 8 bytes as a 64-bit int. The tuple is hashed, never
added, so the seed 5 / tick 3 vs seed 3 / tick 5 collision is
gone. Each actor's draws for a tick come from its own stream,
so adding or removing an NPC changes no one else's draws, and
chunked ticking equals one continuous run (the stream depends
only on seed, actor, tick — never on call history).

## Versioning (`rng_scheme` meta)

- `load_seed` writes `rng_scheme = seed.get("rng_scheme", "v2")`.
  New DBs default to v2. A seed may pin "v1" explicitly.
- The tick path reads `rng_scheme` with a missing-key default
  of "v1". The live Fork A and Fork B DBs have no key, so they
  keep the old scheme and replay identically. The existing
  seed files are NOT modified.
- Under v1, `run_ticks` behaves exactly as today: the passed
  `rng`, or `Random(rng_seed)` re-seeded per call. Under v2
  the passed `rng` is ignored (the scheme is authoritative —
  that is what makes the drivers agree) and `_run_one_tick`
  derives a per-actor stream for each actor that acts.

## File changes

- `src/tick.py`: `rng_for()`; `run_ticks` reads the scheme and
  threads `rng_seed` + `scheme` into `_run_one_tick`;
  `_run_one_tick` gains `rng_seed`/`scheme` kwargs and picks
  the per-actor stream under v2 (shared stream under v1);
  `_act` and `_pick_action` unchanged (they receive whichever
  rng they are given); module docstring updated.
- `src/seed.py`: `load_seed` writes the `rng_scheme` meta.
- `src/auto_tick.py`: RNG paragraph in the docstring updated
  (under v2 the per-actor streams govern and the drivers
  agree; the passed rng is the v1 driver). No code change.
- `src/turn.py`: docstring updated (the "re-seeds
  `Random(rng_seed)`" lines are v1-only now; under v2 the
  per-actor streams govern). No code change — the wrapper
  still calls `run_ticks(conn, 3)` with no rng.
- `tests/test_turn.py`: setUp pins its DBs to v1 (the wrapper
  tests verify wrapper mechanics against the recorded v1
  tick outcomes — Bond 2/5, the net — not the RNG scheme).
- New: `tests/test_step1_slice2.py`, this plan doc.

## Test list

- Per-actor streams are stable (same seed/actor/tick gives the
  same draw sequence) and independent (different actor, tick,
  or seed gives a different stream; seed 5 tick 3 != seed 3
  tick 5).
- Chunked equals continuous under v2: 10 ticks in one call,
  5+5, and 1x10 on fresh DBs give identical event logs and
  state hashes.
- Adding an NPC changes no one else's draws: a new NPC that
  sorts first by id, with tied no-op actions, acts first; the
  original actors' picks in that tick are identical with and
  without it.
- Same seed, same world across drivers under v2: `run_ticks`
  with an explicit `rng=Random(999)` equals `run_ticks` with
  no rng (identical logs and hashes).
- New DBs default to v2; a seed pinning "v1" gets v1.
- v1 replays identically (golden hashes recorded before the
  change, on the old code): Fork A fresh 30 ticks
  `Random(131)` -> `09ecd8f5f3881aa8831fab4715009470261a3adc2990a2ca04c4e93a312c9790`;
  fixture fresh 400 ticks `Random(131)` ->
  `e998132eeb3166d1d7984aac7d0dc4a92e510b3cdae91cae74bb23f95924c566`;
  Fork B fresh 3 ticks no rng ->
  `72ed813c751d87abcc2d52bef1327e7bfd346ae5e1e2189eea8ef5adede43d5c`.
  Each is reproduced by a DB with the `rng_scheme` meta row
  deleted (the exact situation of the live DBs).
- All 180 existing tests keep passing.

## Acceptance

Suite green; the wrapper verification script re-run on copies
of the live Fork B DB still matches the pipeline hashes
(v1 path untouched); the Fork B 1,000-tick measurement (next
item) runs under the new scheme on a fresh copy.
