Checkpoint — Turn 132
Tick 3 | events 39 | state 5c27714a2de9 | last swept turn 132

Bonds (block value vs DB now):
  Gold Sledge: block 3, DB now 3 — MATCH
  Skytalon: block 5, DB now 5 — MATCH
  Razor-Back: block 3, DB now 3 — MATCH
  Goliath Dreadnought: block 5, DB now 5 — MATCH
  Surveyor-Strider: block 5, DB now 5 — MATCH

Clocks (block value vs DB now):
  Dust-Baron Retaliation: block 0/6, DB now 1/6 — DRIFT
  Concord Blockade: block 0/6, DB now 0/6 — MATCH
  Legion Cohesion: block 0/6, DB now 0/6 — MATCH
  Great Basin Recovery: block 1/6, DB now 6/6 — DRIFT

Locations (current controllers):
  chalk_canyons: nest_keepers
  concord_camp: caravan_concord
  great_basin: ironwild_legion
  leviathans_ribs: breakers
  northern_trench: dust_baron_remnants
  rust_dunes: breakers
  salt_flats: ironwild_legion

Pending decision (verbatim): none

Drift lines: 2

Acceptance test:
  1. Schema obedience: 3 proposal(s) reviewed, 0 parse failure(s), 0 validation-error block(s)
     PASS
  2. Mechanical accuracy: 2 drift line(s)
     FAIL — 2 value(s) differ from the block
  3. Continuity: 0 frozen-term event(s), 2 drift line(s)
     FAIL — frozen-term event(s): none; drift: 2
  4. No unapproved state changes: hash chain OK, 0 unknown action(s), 0 sweep event(s) without an approved record
     PASS
Acceptance: FAIL (2 failure(s))

World state (Lore's checkpoint additions):
  Resources: 0 negative row(s)
  Resource replay (seed + event deltas): 0 mismatch(es)
  Territory breakers: 0 — STALE (controls 2)
  Territory caravan_concord: 1
  Territory dust_baron_remnants: 0 — STALE (controls 1)
  Territory ironwild_legion: 2
  Territory nest_keepers: 1
  Territory pack: 0
  Territory rust_choir: 0
  Territory: 2 stale row(s) — the engine does not maintain Territory on location changes
  Resources: 2 problem(s)
  Pack: Vance, Tull, Queen Kaelen, Nest-Keeper
  Actor locations (DB):
    Breaker Poacher Chief (role label): Chalk Canyons
    Brigus: Great Basin
    Caravan Master (Concord): Concord Camp
    Dust-Baron Captain (role label): Rust Dunes
    High Baron: Rust Dunes
    Queen Kaelen: Great Basin
    Legion Captain (role label): Great Basin
    Nest-Keeper: Chalk Canyons
    Tull: Great Basin
    Vance: Great Basin
  State version: ledger Turn 132 ForkA-vFINAL.1 vs last approved block Turn 132 ForkA-vFINAL.1 — MATCH
  Rumors live (from logged events):
    [event 37] Rumor (unverified): word is the Great Basin Recovery has run its course.
    [event 30] Rumor (unverified): word from the road says raiders struck near Great Basin.
    [event 29] Rumor (unverified): the caravan hears trade is moving again on the road.
