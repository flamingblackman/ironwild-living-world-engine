# Fork B 1,000-tick measurement — 2026-11-22

Read-only. Fresh Fork B world from `seed/fork-b.internal.json`, 1,000
continuous ticks on a COPY (`runs/audit-step0/fork-b/sim-1000.sqlite`).
Same method and same "significant event" definition as the Step 0 audit
item 16 (Fork A). Fresh seed, so it runs under the new RNG scheme v2
(the passed rng is ignored; per-actor streams govern). Report:
`runs/audit-step0/fork-b/report-1000.json`. Invariants clean. 7,002 events.

## Verdict

**Passes the letter of the Step 4B balance test, fails the spirit.**
Significant events never drop to zero: 62–74 per 100 ticks in every
window (Fork A had 18 in ticks 1–100, then 0 forever). But after tick
4, **every single significant event is one two-action loop**: the
Breaker chief nets Ashfang, Pike repairs him, repeat. Nothing else
significant happens for the remaining 996 ticks.

## Significant events per 100 ticks

| ticks | events | significant |
|-------|--------|-------------|
| 1–100 | 700 | 69 |
| 101–200 | 700 | 68 |
| 201–300 | 700 | 68 |
| 301–400 | 701 | 66 |
| 401–500 | 700 | 62 |
| 501–600 | 700 | 70 |
| 601–700 | 700 | 63 |
| 701–800 | 701 | 69 |
| 801–900 | 700 | 74 |
| 901–1000 | 700 | 69 |

## What the significant events actually are (all 1,000 ticks)

- net_ambush: 338 (all status flips netted)
- repair_engine: 337 (all status flips field-patched)
- claim_dust_baron: 1, claim_nest_keepers: 2
- Total: 678.

Ticks 101–1000: **only** net_ambush (305) and repair_engine (304).
The status flips are a perfect 1:1 ping-pong after the first net:
netted → field-patched → netted → field-patched, 337 cycles.
net_ambush fired 492 times; 154 of those were no-ops (Ashfang already
netted). repair_engine fired 337 times and every one flipped, because
it only fires while Ashfang is netted.

## The clocks never move

- engine_awakening: 1/6 → 1/6. dust_baron_retaliation: 0/6 → 0/6.
  caravan_route: 0/6 → 0/6. **Zero clock advances, zero completions
  in 1,000 ticks.** No action's clock_add ever applied. The
  clock-driven story is dead from the start, same as Fork A (whose
  only completion was great_basin_recovery at tick 3).
- Clocks completed: none.

## Raids never land

- 1,505 raid events (raid_captain 999, raid_chief 506). **Zero gained
  Salvage.** Every raid is blocked by the Great Basin fortification
  (seeded fortified), so the resource ops are skipped entirely.
  Salvage created from nothing: 0.
- Every raid event carries two notes: "raid blocked: Great Basin
  fortified" (applied) and "raid blocked: Great Basin patrolled"
  (skipped). Patrol fired 55 times but never actually blocks a raid —
  the audit item 11 finding carries over (patrollers act after
  raiders, so the patrol note is always skipped). The rumor false
  positive (item 14) carries over too: a fully-blocked raid still
  yields a "raiders struck" rumor.

## Actions that stopped or never fired (of 20)

- Never fired: trade_concord, evacuate, scavenge_dust_baron,
  claim_breakers, claim_great_basin.
- Stopped: claim_dust_baron (tick 1), scout_wreck (tick 1),
  claim_nest_keepers (tick 4), scavenge_breakers (tick 6),
  dream_share (tick 12 — Bond capped at 5, then the action stops
  being chosen).
- Still firing at tick 1000: hunt, rest, feed_burn, tend_den,
  feed_engine, scavenge_dunes, net_ambush, repair_engine, patrol,
  raid_captain, raid_chief. legacy fired twice (era boundaries 365,
  730).
- evacuate: 0 events (the concord_camp flag is never set — same dead
  content as Fork A). pack_merge is absent in Fork B (0).
- Territory and Cores: never changed by any op (same as Fork A).
- Locations at tick 1000: rust_dunes contested (nest_keepers),
  northern_trench nest_keepers, leviathans_ribs dust_baron_remnants.
  Both still carry the status string "unmapped" after being mapped
  and claimed (the display wart from audit item 12).
- Skipped ops: 6,199 of 7,002 events carry skipped ops — the world
  spends most of its time attempting blocked actions.

## What this means for WorldRenewal (Step 4B)

The balance test passes on the letter, so WorldRenewal's priority
does **not** drop — it rises in one specific sense: the only
renewable significant content Fork B has is the net↔repair loop,
and **StoryOwned turns net_ambush into a hook, not an applied
change**. Under StoryOwned, Fork B's significant-event rate after
tick 4 is 0. The loop is masking how thin the seed is: no clock
ever advances, no raid ever lands, no trade ever happens, 5 of 20
actions never fire. WorldRenewal (repeatable clocks, entropy, waking
the dead clocks, stagnation meter, pressure-driven goals, mortality
and succession, era turnover, frontier pool) is still the fix — it
just has to replace the loop with real renewable content, not merely
keep the count above zero.
