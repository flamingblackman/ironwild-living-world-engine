# Stage 1 plan — Fork A test automation

## 0. Design objective (Bryan, 2026-11-21 01:18 EST): Story-First, Automation-Heavy RPG

The player should spend nearly all their time playing the RPG,
making character decisions, and experiencing the story. ChatGPT is
the primary DM. Muse is the controller and auditor. The Engine owns
persistent state. Lore owns the approved mechanics specifications.

Build toward a system where state tracking, rules validation,
clocks, resource calculations, continuity checks, handshakes, error
recovery, and session records happen automatically. The player
should not need to manually transport V2 blocks, manage database
updates, or approve trivial bookkeeping every turn.

**What does NOT change — the approval policy is preserved until
Bryan explicitly defines and approves limited standing permissions
for routine changes.** Every apply still needs Bryan's explicit tap,
bound to the exact proposal revision. Major and irreversible changes
must retain explicit approval, even after standing permissions
exist. Nothing in this objective authorizes auto-apply, and nothing
in Stage 1 builds it.

**Exception-first interface:** show administrative information only
when something important requires attention. The intake poll already
stays silent when nothing is new; hub reports carry reviews,
rejections, halts, and drift — not routine confirmations. Keep the
three-turn audits, but do not interrupt the narrative unnecessarily.

**Success criterion:** the player can complete a multi-turn RPG
session focused on story and decisions, with minimal administrative
interruptions and a reliable, auditable campaign state.

**Scope discipline:** prioritize the Turn 133 handshake and the
existing Fork A test. Add these capabilities incrementally, without
risking live Gemini canon. This objective governs Stage 1 design
(1A first, then 1B); it does not change the approval gate, the Fork
A scope, or the Turn 133 priority.

**Lore's role under this objective (Lore, 2026-11-21 ~01:23 EST):**
the approved mechanics specifications the automation validates
against — the registry IW-42–IW-85, the V2 spec
(lore-phase-2-inputs.md section 1), the Fork A seed v1.6. No spec
change now. If the Engine needs the specs in a different form for
validation, that is a future ask, not a change to the specs
themselves. (Not needed now: 1A validates against the DB the seed
built plus the Fork A identifier check.)

## 1. Approval and roles

**APPROVED by Bryan, 2026-11-21 01:15 EST.** Review-before-apply
approval gate KEPT: nothing is applied without Bryan's tap.

Roles for the Fork A test, fixed:

- **ChatGPT is the DM.** It plays turns and proposes V2 state blocks.
- **Muse is the controller.** It validates, reviews, applies approved
  changes, ticks, and generates handshakes.
- **The Engine owns authoritative state.** The test DB
  (`state/ironwild-fork-a-test.sqlite`) is the ledger; the event log
  is append-only; the handshake is generated from the DB alone.
- **Bryan retains final approval.** Every apply needs his tap, bound
  to the exact proposal revision (see section 4).
- **Live Gemini canon stays live in Gemini.** Stage 1 does not migrate
  the live DM, the live world, or Turn 136. Fork A only.

**Priority order (hub, 2026-11-21 01:15 EST): Turn 133 is the
immediate priority.** The Salvage and PC corrections are done and the
authoritative 589-word handshake is delivered and confirmed by Lore.
Automation work must not interfere with the Fork A test: the 1A
acceptance test runs against a scratch copy of the test DB, never the
live one, until the pipeline is proven.

## 2. The split (ChatGPT's adjustment, adopted by Bryan)

Stage 1 is two stages, built in order:

- **1A — Engine-side automation.** A proposed V2 block placed in
  Drive moves through validation, approval, atomic commit, and
  handshake generation **without manual file handling**.
  1A passes when that path works end to end.
- **1B — ChatGPT integration.** The actual ChatGPT Project
  conversation submits a V2 proposal and retrieves the resulting
  approved handshake **without manual copying**.
  1B passes only when demonstrated end to end on Bryan's account
  (paccman360 Plus, Ironwild Test Project). Do NOT assume 1B works
  until it is demonstrated there.

1B starts only after 1A passes.

## 3. 1A pipeline

Drive folders (personal Gmail — fiction lives there; the connected
Drive already holds the Ironwild Canon folder):

- **Inbox:** `Ironwild Fork A — Proposals` (new folder, under the
  `Ironwild - Canon` folder).
- **Outbox:** `Ironwild Fork A — Handshakes` (new folder, same place).

A proposal is a plain-text `.txt` file in the inbox whose contents
are one V2 `[TURN STATE]` block — the same file the sweep's `--block`
flag takes today. The filename is a convenience only; identity comes
from the file, never the name.

### 2.1 Intake (poll)

There is **no webhook for Drive in the connector surface** — the
Drive CLI offers list/get/upload/create, no watch or push. So 1A's
intake is a scheduled poll, stated plainly rather than assumed
otherwise. The poll command:

```
python3 -m src.run intake --inbox <folder-id> [--db <db>]
```

For each file in the inbox not yet in the registry (by Drive file ID
+ content hash), intake:

1. Downloads the content.
2. Parses it with `sweep.parse_state_block` (strict literal markers
   and labels — the same parser the manual path uses).
3. Validates it with `sweep.validate` plus the new Fork A identifier
   check (section 4).
4. Writes the review (`review.json`) and the carried state into
   `runs/proposals/<proposal-id>/`.
5. Records the proposal in the registry
   (`runs/proposals/registry.json`) with status `reviewed` — or
   `rejected` with the findings, if validation fails.

Intake writes **registry + review files only, never the DB**. It is
idempotent: re-running it skips files already in the registry with
the same file ID and hash. A file whose content changed (same file
ID, new hash) is a **new proposal revision** with a new ID; the old
revision keeps its own status, and an approval bound to the old hash
cannot land on the new content (section 4).

### 2.2 Review (gate kept)

Intake never applies. The review is surfaced to the hub exactly as
the manual dry-run review is today (changes old → new, findings,
based-on / last-approved lines). Bryan's tap approves a proposal
**by its proposal ID**. No ID, no apply.

### 2.3 Approval binding + atomic commit

The apply step takes `--proposal-id` and verifies, before touching
the DB:

1. The registry entry exists and its status is `reviewed`.
2. The Drive file's current content hash matches the hash recorded
   at intake (re-download and hash; mismatch = refuse, status
   `held`, reason recorded).
3. The approver is Bryan (the `--approved-by` value must be Bryan).

Then the existing `apply_sweep` runs — **one transaction**, the same
atomic commit the manual path uses — and the registry entry moves to
`applied`, with the approval record (approver, timestamp, proposal
ID, content hash) written into `applied.json` alongside the change
record. A second apply of the same proposal ID is refused (status is
already `applied`).

### 2.4 Tick + handshake out

After a successful apply, the pipeline ticks as needed (3 ticks, the
Turn 132 precedent — the count is the Engine Team's call per turn,
recorded in the run record) and generates the handshake from the DB
alone. The handshake is:

- Written to `runs/handshakes/turn-<n>.md` (+ `.json` meta), as today.
- Uploaded to the Drive outbox as `turn-<n>-handshake.md`.
- Reported as text to the hub, as today — the hub still hands it to
  Bryan until 1B lands.

### 2.5 Failure halts

Every failure halts safely **without advancing state**:

- Parse failure → proposal `rejected`, review record kept, no DB
  write. (Same rule as the manual path's `rejected/` records.)
- Validation error → proposal `rejected` with findings.
- Hash mismatch at apply → `held`, no apply, reason recorded.
- Missing or mismatched approval → refuse, no apply.
- Drive error / missing file → intake or apply fails open (proposal
  stays `received`/`reviewed`), nothing applied.

No partial applies are possible: the commit is one transaction, and
intake never writes the DB.

## 4. The four safeguards (plus approval binding)

1. **Unique proposal ID.** `prop-<turn>-<first 8 of sha256(content)>`,
   plus the Drive file ID recorded. Unique per (turn, content); a
   revised file gets a new ID. The registry is the single record of
   which proposals exist and what happened to each.
2. **Base state version.** The proposal's State-Version and Turn must
   follow the last approved version: Turn = last_swept_turn + 1 with
   version `ForkA-vFINAL.<turn - 131>`, or the same Turn as a
   same-turn revision (the Turn 132 revised precedent — new proposal
   ID, fresh approval required). A Turn below last_swept_turn is
   STALE_PROPOSAL and refused; a missing State-Version is NO_VERSION
   and refused. Both already exist in `sweep.validate`.
3. **Strict Fork A identifier.** NEW validation: Universe must be
   `Ironwild`; State-Version must match `^ForkA-vFINAL(\.\d+)?$`;
   the block's Base, when present, must be a ForkA version. Anything
   else is refused with a `NOT_FORK_A` error finding — no Turn 136
   block, no live-canon block, no other fork can enter the pipeline.
   (The V2 block carries no world field; the identifier is the
   Universe + the ForkA version string.)
4. **Atomic approval-and-commit process.** Approval binds to the exact
   proposal revision (proposal ID + content hash + approver +
   timestamp, recorded in `applied.json`); the commit is the existing
   one-transaction `apply_sweep`. No approval, no commit; a changed
   file, no commit; a second apply of the same ID, no commit.

## 5. Cron role

- **1A intake is a scheduled poll** (no webhook exists for Drive via
  the CLI). Poll interval: every 15 minutes. The poll IS the primary
  intake for 1A, and its re-list also serves as the recovery net:
  a file the poll missed is picked up on the next run, because the
  registry reconciles against the folder listing every run.
- **The 15-minute cron as recovery, not primary, applies to the 1B
  event-driven path if one is built:** if 1B adds an event-driven
  intake, the 15-minute poll stays as its recovery net and never
  becomes the way proposals normally arrive.
- The daily auto-tick cron (`ironwild-fork-a-daily-tick`, DISABLED)
  is a different job — the world tick, not proposal intake. It stays
  disabled until Bryan says otherwise.

## 6. 1A acceptance test

1A passes when a V2 block placed in the Drive inbox moves through
validation, approval, atomic commit, and handshake generation with
no manual file handling — **on a scratch copy of the test DB**, so
the live Fork A test is untouched. Steps:

1. Place a synthetic Turn 133 proposal (built from the live DB's
   state, Recovery 6/6 already complete, so a clock change that
   cannot fire — or a fresh clock movement the DB can accept) in the
   inbox.
2. Run intake: proposal registered, review written, status
   `reviewed`, no DB change.
3. Approve by proposal ID (test approval, recorded as such).
4. Run apply: one transaction, status `applied`, approval record
   bound to ID + hash.
5. Tick + handshake: handshake generated and uploaded to the outbox.
6. Verify: the scratch DB's state matches the proposal, the hash
   chain verifies, the outbox holds the handshake, and the live test
   DB is untouched (tick 3, 36 events).

A re-run of the acceptance test with a tampered file (content
changed after review) must refuse at apply with a hash mismatch and
advance no state — that is part of the pass criteria, not an extra.

## 7. 1B — investigation plan (starts after 1A passes)

1B's mechanism is **not chosen yet**. Do not build it blind. The
investigation, in order:

1. **Can the ChatGPT app connect Google Drive on Bryan's account?**
   ChatGPT Plus surfaces a Google Drive connector in some clients.
   If the Ironwild Test Project GPT can read the outbox folder and
   write to the inbox folder through that connection, 1B is a
   configuration + instruction change, not a build. This needs
   Bryan's account access (browser task) — it cannot be tested from
   the Engine side alone.
2. **GPT Actions against a hosted endpoint.** A custom GPT Action
   needs a public HTTPS endpoint to call. This VM has none. Building
   one is a hosting decision (and a new surface to secure), not a
   quick patch — only if option 1 fails, and only with Bryan's call.
3. **Browser-driven UI automation.** A browser task driving the
   ChatGPT UI to upload/download files is the fallback of last
   resort: it is brittle, and it is still copying by machine rather
   than integration. It counts as demonstrated only if it runs
   unattended end to end on Bryan's account — a person pasting does
   not count.

**1B acceptance:** demonstrated end to end on Bryan's account
(paccman360 Plus, Ironwild Test Project) — the DM submits a V2
proposal and retrieves the resulting approved handshake with no
copy-paste by Bryan or by any person. A demonstration that needs a
person in the loop is a fail, not a pass.

## 8. Open items

- ~~Inbox/outbox folder IDs (to be created by the build; design
  records them here when they exist).~~ **Done 2026-11-21 ~01:17
  EST:** inbox `1urZHns0Vc487ve_OMilbN4lCnzhivbTR` ("Ironwild Fork
  A — Proposals"), outbox `1Sq4U3jocH4IuPL7Rxg_ujzg2fxftwtG-`
  ("Ironwild Fork A — Handshakes"), both under the Ironwild Canon
  folder on the personal Gmail Drive. Also recorded in
  `runs/proposals/config.json`.
- ~~Poll cron: create (enabled) once intake is built and the
  acceptance test passes on scratch; the live inbox stays empty
  until then, so the poll cannot touch the live test.~~ **1A
  COMPLETE (Bryan's go-ahead, 2026-11-21 01:27 EST).** 1A passed
  its acceptance test (~01:22 EST, record
  `runs/acceptance-1a/acceptance.json`); the poll cron
  `ironwild-fork-a-proposal-intake` was created ENABLED (every 15
  min, first run ~01:31 EST). The live inbox is empty, so the poll
  cannot touch the live test until a real proposal lands. **1B
  investigation starts now** (browser task: can the ChatGPT app on
  Bryan's account connect Google Drive, and can the Ironwild Test
  Project GPT read Drive files?).
- 1B mechanism: undecided pending the investigation in section 7.
- The Turn 133 live sweep still goes through the manual path
  (hub → Engine Team) until 1A is proven; the pipeline must not
  intercept it.
- Known wart: re-running the handshake upload creates a duplicate
  file in the outbox (upload always creates; it never updates in
  place). A future improvement: check for an existing file by name
  and update it instead.
