# Step 1 slice 1 — build plan (approved 2026-11-22)

Scope: transaction boundaries, applied_turns, UNIQUE prev_hash,
halt rollback. No RNG change (slice 2), no seed change, no
behavior change to scoring or tick order. All 172 existing tests
must keep passing.

## 1. BEGIN IMMEDIATE per tick (`tick.run_ticks`)

Each tick iteration opens its own immediate transaction
(`conn.execute("BEGIN IMMEDIATE")`) before `set_tick`, commits
on success, and rolls back on any failure. A second writer now
blocks up to the busy timeout (5s, set explicitly in
`db.connect`) and then fails loudly with "database is locked"
instead of interleaving and forking the chain. Precondition:
no open transaction on the connection when a tick starts (true
for every caller: cmd_tick, attempt_auto_apply, auto_tick, the
turn wrapper, and the tests — seeding commits).

## 2. BEGIN IMMEDIATE per sweep (`sweep.apply_sweep`)

`BEGIN IMMEDIATE` before the existing `with conn:` block, which
then commits (or rolls back on exception) the immediate
transaction. The `diff()` is still computed before the
transaction opens; the absolute writes and the applied_turns
row (below) land inside it.

## 3. applied_turns table

```sql
CREATE TABLE IF NOT EXISTS applied_turns (
    turn INTEGER PRIMARY KEY,
    content_hash TEXT NOT NULL,
    state_version TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    approver TEXT NOT NULL,
    source TEXT NOT NULL,
    proposal_id TEXT
);
```

- Lives in `state/schema.sql` (single source of truth).
- Existing DBs get it via `db.init_schema(conn)`, which is
  idempotent (every statement is IF NOT EXISTS). It is called
  at the start of every apply entry point (`apply_proposal`,
  `apply_registered`, `cmd_sweep` apply branch) and by a new
  `migrate` CLI command for manual use. No new migrate function.
- `apply_sweep` takes optional `content_hash`, `proposal_id`,
  `source`; when a hash is given it inserts the row in the same
  transaction as the sweep and returns `applied_at` in the
  result, which the callers reuse for the approval binding
  (one timestamp). Callers: Drive path (source from the
  registry entry), local path (source "local-file"), manual
  sweep (source "manual-sweep", proposal_id None).
- `applied_turns` is NOT added to `STATE_TABLES`: the migration
  alone must not change any state hash (an empty table would
  not, but the row writes must not either — the event log
  already records the applies).
- The gate (`check_apply_gate`) consults applied_turns when the
  table exists OR the registry when an entry is marked applied.
  Both stores are checked: the table starts empty on a migrated
  DB, so pre-migration applies live only in the registry.
  No backfill (the registry remains the record for old applies).

## 4. UNIQUE index on events.prev_hash

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_prev_hash
ON events(prev_hash);
```

Verified safe: the live Fork A DB (240 events) and Fork B DB
(22 events) have zero duplicate prev_hash values (genesis is
"GENESIS", every later prev_hash is a unique prior event hash).
A second writer that somehow inserts with a duplicate prev_hash
now gets an IntegrityError instead of a silent chain fork, and
the enclosing tick/sweep transaction rolls it back.

## 5. Halt rolls back the tick, writes only a halt record

`run_ticks` on EngineHalt now rolls the partial tick back
(including the tick-number advance) and appends exactly one
halt event — actor "engine", action "halt", effect note
"halt at tick <attempted>: <reason>" — at the last completed
tick number, in its own transaction, then re-raises. A retry
re-runs the SAME tick (previously each retry consumed a new
tick). Non-halt exceptions also roll back explicitly instead
of relying on `conn.close()` to discard the open transaction.
Docstrings updated (`run_ticks`, `_run_one_tick` — the old "a
halt can commit the partial log" line is now wrong).
`auto_tick`'s halt branch is unchanged in shape: it records
outcome "halted" with the (now un-advanced) tick number.

## File changes

- `src/db.py`: busy_timeout 5000 in `connect`.
- `state/schema.sql`: applied_turns table + unique prev_hash index.
- `src/tick.py`: run_ticks immediate transactions + halt rollback
  + halt record + docstrings.
- `src/sweep.py`: apply_sweep BEGIN IMMEDIATE + applied_turns
  insert + applied_at in result + datetime import.
- `src/proposals.py`: apply_proposal migrates + passes binding
  info + reuses result applied_at.
- `src/apply_adapter.py`: apply_registered migrates + passes
  binding info + reuses result applied_at; gate checks
  applied_turns OR registry.
- `src/run.py`: cmd_sweep migrates + passes binding info;
  new `migrate` subcommand.
- New: `tests/test_step1_slice1.py`, this plan doc.
- No change to scoring, RNG, seeds, or the turn wrapper's
  behavior (it calls apply_registered, which migrates).

## Test list

- A second writer holding an immediate transaction makes
  run_ticks fail loudly (OperationalError, "database is locked")
  and leaves the DB unchanged.
- A non-halt error mid-tick rolls everything back: tick number
  unchanged, no partial events, no partial state.
- A halt rolls the tick back and writes exactly one halt
  record (action "halt", reason in the text, tick = last
  completed tick); a retry re-runs the same tick.
- applied_turns row written in the same transaction as the
  sweep (turn, hash, version, approver, source).
- applied_turns alone blocks a re-apply after the registry
  entry is reset to reviewed.
- UNIQUE prev_hash index exists after migrate; a duplicate
  prev_hash insert raises IntegrityError.
- Migrate is idempotent and safe on a ticked DB (events count
  and state hash unchanged).
- All 172 existing tests keep passing.

## Acceptance

Live Fork A and Fork B DBs migrated (migrate command), state
hashes unchanged by the migration, applied_turns table and
prev_hash index present, suite green.
