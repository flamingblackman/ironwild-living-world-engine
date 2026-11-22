# Two small fixes — plan and test list

Status: PLAN ONLY. No code changed, no seed changed, no live DB touched.
Code changes are already green-lit (Bryan 2026-11-22). The seed diffs
at the end need approval before they are applied — they change what
the live Fork B world does next.

## Fix 1 — preconditions from when/need into trigger

### What the investigation found (checked every action in both seeds)

- Action-level `when` is null on every action in both seeds. There is
  nothing to move from `when`.
- Of the `need` clauses, exactly ONE is a true precondition: Fork A
  `fortify`'s `great_basin_recovery clock < 6`. Once that clock
  completes (tick 3), fortify keeps firing and burns 1 Salvage per
  tick for zero effect — 454 times in the Fork A 1,000-tick run.
  Moving that clause into `trigger` makes fortify illegal once the
  clock is done.
- Every other `need` clause is a genuine preference and STAYS as
  scoring. Moving any of these into `trigger` would be wrong:
  hunt (Feed < 3), feed_engine (Hunger >= 4 — gating on this would
  starve engines at Hunger 1–3), repair_engine / pack_merge
  (netted — already inside their triggers), dream_share (Bond < 5 —
  already inside the trigger's second branch), scout_wreck / trade /
  raid (Salvage < 3), tend_den (Feed < 5).
- The fortify instance lives in the Fork A seed, which is NEVER
  modified (frozen). So fix 1 builds two things instead of editing
  the live seed:
  1. A seed validator that catches the pattern mechanically: a `need`
     clause referencing clock X while the action's effect has a
     `clock_add` on the same clock X means the need is load-bearing
     for a zero-effect outcome — flag it as "precondition in need;
     move to trigger". (New: `tools/check_seed.py`, run against both
     seeds; also callable from `seed.load_seed` as a warning.)
  2. The fortify diff recorded as a proposed diff (docs, not applied
     to the frozen seed): move the clock clause from `need` to
     `trigger` in Fork A's fortify action.

### Found during the investigation — the scavenge trap (seed balance)

Fork B's dust_baron_captain raids 999 times and scavenges 0 times
in 1,000 ticks, even though scavenging is the only way to gain
Salvage. Mechanism, confirmed on a fresh 20-tick copy:
1. Tick 1 the captain claims a location, paying 1 Salvage (3 → 2).
2. From tick 2, raid_captain's need (Salvage < 3) is satisfied, so
   raid scores 6 and scavenge_dust_baron scores 5. Raid wins every
   tick. The tie-break (`rng.choice`) is fair — the actions are
   never tied.
3. Raids are all blocked (Great Basin fortified), so Salvage never
   rises, the need stays satisfied, and raid keeps winning forever.
   Deadlock.
Proposed seed diff (Fork B, needs approval): give scavenge_dust_baron
and scavenge_breakers the same `need` the raid actions have
(Salvage < 3 → +1), so they tie with raid when Salvage is low and
the tie-break lets them fire. scavenge_dunes needs no change (it
fired 335 times).

### Found during the investigation — trade_concord's dead trigger

Fork B's trade_concord trigger requires clock `concord_blockade`,
which does not exist in Fork B. `conditions.clause_holds` returns
False for a missing clock, so the action is never legal — 0 fires in
1,000 ticks. It is a Fork A clock name carried into the Fork B seed.
Proposed seed diff (Fork B, needs approval): point the clause at
Fork B's `caravan_route` clock (0/6), or drop the clock clause.
Either way the caravan_master starts trading. A seed validator check
for references to missing clocks / locations / factions is the
durable fix — include it in the same `tools/check_seed.py`
(SeedHygiene owns the full validator; this is the first two checks).

### Found by the validator, after the build started — repair_engine's dead clock

Fork B's repair_engine effect had a `clock_add` on
`great_basin_recovery`, a Fork A clock that does not exist in Fork B.
`actions.py` returned `applied_qty: 0` for a missing clock, so the op
was silently dead — repairs still worked (the status_set landed, 337
times in the 1,000-tick run), but nothing ever advanced. Same class
of defect as trade_concord's trigger. RESOLVED 2026-11-22: Bryan said
"drop the dead piece" (direct, in the Engine chat), and the op was
dropped from the seed and the live DB's catalog. Note: the hub had
relayed an earlier "point it at the bond counter" (engine_awakening)
from Bryan via Lore's recommendation; the direct "drop" is the later
instruction and governs. Fork B is now validator-clean (0 findings).
The live hash moved 537694e6 → 053517fc32e9 (catalog in meta);
repairs still land; wrapper re-verified PASS with new hashes
(Turn 2: 9451417e30bd, Turn 3: c6e0a4bb5d0b, Turn 4: 9e0aed66b3b5).

### File changes (fix 1)

- NEW `tools/check_seed.py`: checks (a) need-clause-on-same-clock-as-
  effect-clock_add, (b) references to missing clocks, locations,
  factions, engines, NPCs. Exit non-zero on any finding. No DB
  access.
- `docs/two-small-fixes-plan.md` (this file) records the fortify
  diff and the two Fork B seed diffs as proposals.
- No change to `src/scoring.py` (need stays score-only) and no change
  to either seed file in this build.

### Test list (fix 1)

- Validator flags the Fork A fortify pattern (need clock X + effect
  clock_add X) and passes a corrected copy of the action.
- Validator flags a missing clock reference (in-memory seed carrying
  trade_concord's old concord_blockade trigger) and passes once the
  clause points at `caravan_route`.
- Validator on the real seeds reports exactly the known findings and
  nothing else: Fork A = fortify NEED_CLOCK_PRECONDITION only;
  Fork B = clean (0 findings) since the repair_engine dead op was
  dropped 2026-11-22. No false positives on the genuine-preference
  need clauses, and placeholders ({location}, {holder}, {self}) and
  dict selectors are never flagged.
- Fork A 1,000-tick sim on a COPY with the fortify diff applied:
  fortify fires 0 times after the clock completes (was 454 times
  after completion in the v1 audit run). Note: under the current v2
  scheme the clock completes at tick 9, not tick 3 as in the v1
  audit, so the criterion is "after completion", not "after tick 3";
  verified 2026-11-22: fortify ticks [1, 6, 8, 9], completion tick 9,
  0 firings after completion.
- Fork B 20-tick copy with the scavenge diff applied: the captain
  scavenges at least once in 20 ticks (was 0 in 20 and 0 in 1,000).

## Fix 2 — rumors skip actions with no material effect

### Change

`src/handshake.py::_rumor_for_event`: after parsing the effect JSON,
return None when no op in the effect visibly changed the world. A
material op is a resource, clock, location, status, bond, move,
molt-trigger, or standing change that applied (not skipped, and not
clamped to zero). Notes and bookkeeping flags do not count. (Empty
effect lists keep current behavior.)

The naive "all ops skipped" rule does not work: a real blocked raid
carries an APPLIED flag_set (`raid_in_progress:great_basin`) and an
APPLIED note ("raid blocked: Great Basin fortified") beside its
skipped resource and clock ops, so "all skipped" never holds. The
material rule is the correct one: the flag is bookkeeping and the
note is commentary; neither is a visible change. This kills the
"raiders struck near Great Basin" rumor for fully-blocked raids —
1,505 of them in the Fork B 1,000-tick run — and the same for
skipped claims. Clock completions are unaffected (their effects
always carry an applied clock_add).

### Test list (fix 2)

- A blocked raid event (material ops skipped, only a flag_set and
  notes applied) → no rumor.
- A raid event with a real Salvage gain → rumor, unchanged text.
- A raid event whose only op is a flag_set → no rumor.
- A claim event whose location_set was skipped → no rumor.
- A clock-completion event → rumor, unchanged.
- An event with an empty effect list → current behavior, unchanged.
- test_rumors_come_from_events_only fixture updated: its raid event
  is now a realistic successful raid (applied resource ops), so the
  test still expects 3 rumors; the blocked-raid behavior is covered
  by the new unit tests.
- Existing handshake tests still pass; full suite green.
- Verification: regenerate rumors from the Fork B sim DB (1,000
  ticks) and confirm zero "raiders struck" rumors from blocked
  raids.

## Acceptance

- Full suite passes (186 + new tests).
- The validator reports exactly the known findings (Fork A fortify
  only) and nothing else. Fork B is clean.
- No live DB, no seed file, and no recorded history changed by this
  build, except the three APPROVED Fork B seed diffs (trade_concord,
  scavenge need, repair_engine drop) and their sync into the live
  DB's catalog meta.

## Approval needed

- The two Fork B seed diffs (trade_concord clock, scavenge need)
  change what the live world does next. They need Bryan's (and
  Lore's, for canon-adjacent mechanics) approval before application.
  The code + validator need no further approval — green-lit.
- RESOLVED: the Fork B repair_engine dead clock_add was DROPPED
  2026-11-22 per Bryan's direct "drop the dead piece", superseding
  the hub's earlier point-at-awakening relay.
