# Turn wrapper — build plan (approved 2026-11-22)

Goal: one local command chains the steps the engine already has.
It adds no new rules. Drive and the 15-minute poll stay available
but are no longer the daily path. Live Turns 2-4 are NOT applied by
this build: verification runs on copies of the Fork B DB. The live
Turn 2 apply still awaits Bryan's hatch decision.

## Bryan's three conditions, and how each is met

(a) Turn-order and duplicate checks live in the shared apply
adapter, not only the wrapper. New module `src/apply_adapter.py`
holds `check_apply_gate(parsed, conn, content_hash)`. Every apply
path calls it: `proposals.apply_proposal` (Drive path),
`apply_adapter.apply_local_block` / `apply_registered` (local path),
and `run.cmd_sweep --apply` (manual path). `sweep.apply_sweep`
itself is unchanged (it stays the low-level "apply this validated
block in one transaction"); the gate sits at the entry points, so
no existing test that calls `apply_sweep` directly breaks.
(b) The 3-tick advance calls `tick_mod.run_ticks(conn, 3)` with no
`rng` argument, exactly as `attempt_auto_apply` and `cmd_tick` do
today. `run_ticks` then re-seeds `random.Random(rng_seed)` on the
call. This is documented in the wrapper module docstring and in
the step-9 code comment, and the verification script proves the
state hash matches the pipeline path using the same call.
(c) Bryan pauses the Drive poll while the wrapper is in use. The
wrapper does not disable any cron itself. The gate makes the
wrapper safe even if the poll is left running: a poll apply and a
wrapper apply for the same turn cannot both land (the second hits
the turn-order or duplicate refusal).

## The shared apply adapter (`src/apply_adapter.py`)

- `check_apply_gate(parsed, conn, content_hash=None)` raises
  `SweepError` unless the block may be applied now:
  - turn must be exactly last_swept_turn + 1 (or the fork's first
    turn when last_swept is None): "expected Turn N, got Turn M".
  - (turn, content_hash) must not already be applied: "already
    applied". Source of truth today: registry entries with status
    `applied` matching turn + hash. Step 1 slice 1 adds the
    `applied_turns` table; the gate will check it first when it
    exists (registry as fallback).
- `register_local_block(text, conn, name="local-file")`:
  reuses `proposals.intake_file(None, name, content, conn)` —
  writes proposal.txt + review.json + registry entry with
  `drive_file_id` None, `source` "local-file", status
  reviewed/rejected. Never writes the DB.
- `apply_registered(pid, conn, approved_by, flag_path,
  resource_changes, lore_approval)`: verifies the stored
  proposal.txt still hashes to the registered hash (the same
  binding as the Drive re-download, local file in place of Drive),
  runs the gate, calls `sweep.apply_sweep` in one transaction,
  marks the registry entry `applied` + applied_at, writes
  applied.json with the binding (approver, source `local-file`,
  content hash, timestamp). Mirrors `apply_proposal`'s
  post-apply bookkeeping.
- `apply_local_block(...)` = register + apply_registered.

## The wrapper (`src/turn.py`, wired as `run.py` subcommand `turn`)

`python3 -m src.run turn --db <fork.sqlite> [--file block.txt | --stdin] [--yes] [--dry-run] [--queue] [--rollback]`

Order, stop at the first failure:
1. Read the block from --file or stdin. Never from Drive.
2. Refuse if the session flag is open.
3. Parse + validate with the existing functions. Print findings.
4. Turn-order check via the shared gate: "expected Turn N, got
   Turn M". Applies to every path, including a human approval.
5. Print the old-to-new diff and the routing tier:
   AUTO (zero changes, zero findings, pure carry-over — eligible
   per `check_eligible` AND no narrative flags), REVIEW (anything
   else, no errors), HOLD (validation errors).
6. AUTO applies. REVIEW asks for confirmation unless --yes.
   HOLD never applies.
7. Before apply, a SQLite backup via `sqlite3.Connection.backup()`
   to `runs/backups/<fork>-turn-<n>-pre.sqlite`, plus a sidecar
   `<...>-pre.json` with state_hash, tick, turn, proposal_id.
   The fork slug comes from the DB's `world_id` meta
   (`ironwild-fork-b` -> `fork-b`).
8. Apply through the adapter. Approver "Bryan", source
   `local-file`, content hash recorded.
9. Tick 3 days: `tick_mod.run_ticks(conn, 3)` with no rng (see (b)).
   On EngineHalt: report clearly, stop, exit 2, no retry, no
   handshake. `verify_invariants` + `verify_chain` also run; on
   problems the same stop applies (mirrors `attempt_auto_apply`).
10. Next handshake via `handshake.generate_handshake` (same call
    as the auto path), written to
    `runs/<fork>/handshakes/turn-<n+1>.txt` and printed to stdout.
11. Print a short summary: turn applied, changes, ticks run,
    events added, new tick, handshake path, backup path. A record
    file `runs/<fork>/turns/turn-<n>.json` is written (mirrors
    auto-applied.json).

`--dry-run`: steps 1-5 only, writes nothing (no registration, no
backup, no apply). `--queue`: registry entries with status
reviewed/held, ordered by turn, newest revision per turn marked,
with proposal.txt paths; plus .txt files in `runs/<fork>/queue/`
if that dir exists. `--rollback`: restore the most recent pre-apply
backup after confirmation; verifies the restored state hash
against the sidecar, and resets that turn's registry entry from
`applied` back to `reviewed` (applied.json renamed to
`applied.json.rolled-back-<ts>`) so the same block can be
re-applied. The DB file copy is exact (default journal mode,
no WAL).

## File changes

- New: `src/apply_adapter.py`, `src/turn.py`, `tests/test_apply_adapter.py`, `tests/test_turn.py`, `tools/verify_turn_wrapper.py`.
- Edit: `src/proposals.py` (gate call in `apply_proposal`),
  `src/run.py` (gate call in `cmd_sweep`, `turn` subparser),
  `docs/step0-audit-2026-11-22.md` (note: gate now shared, per
  condition (a) — the audit recommended wrapper-level only).
- No change to tick, scoring, RNG, or schema.

## Test list

- Gate: out-of-order refused ("expected Turn N, got Turn M");
  duplicate refused ("already applied"); next turn passes; first
  turn on a fresh DB uses the fork's first turn.
- Adapter: local block registers + applies; stored-hash mismatch
  refused; non-Bryan approver refused; session flag blocks;
  validation errors refuse; Drive path (`apply_proposal`) now
  refuses an out-of-order proposal.
- Wrapper: dry-run writes nothing (DB hash unchanged, no new
  files); AUTO applies a 0-change block; REVIEW waits for
  confirmation (decline applies nothing, accept applies);
  HOLD never applies; backup exists before apply and its sidecar
  hash matches the pre-apply state; rollback restores the exact
  state hash and resets the registry entry; halt stops cleanly
  without a second tick or a handshake; session flag blocks;
  handshake file written with the next turn number.
- All 151 existing tests keep passing.

## Acceptance

Fork B Turns 2, 3, 4 processed in order with `turn` on a COPY of
the live Fork B DB (revised Turn 3/4 blocks created as local
fixtures, Bond 2/5, "newly awakened and battered"), state hashes
match what the current pipeline produces for the same input
(`apply_sweep` + `run_ticks(conn, 3)` + `generate_handshake` on an
identical copy), and all 151+ tests pass. Live Turns 2-4 are
untouched by this verification.
