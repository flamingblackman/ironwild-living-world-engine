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

**1B's mechanism is not chosen yet — and the investigation (read-only
browser task, 2026-11-21 01:28–01:31 EST) narrowed it.** Findings,
verified live on Bryan's account (paccman360 Plus, signed in):

- **Correction to the premise: "Ironwild Test" is NOT a custom GPT.**
  It is a ChatGPT Project (a folder) with three chats (Ironwild
  Handshake, Echo Turn State, Ironwild Decision Suspended). Projects
  have NO tools/actions configuration — the Project settings dialog
  holds only the name, icon/color, an Instructions text box (the DM
  ruleset; no mention of Drive, file reading/writing, tools, or
  APIs), Memory, and Space access (ChatGPT's internal file Space,
  not Google Drive). The account owns NO custom GPTs at all
  ("No GPTs here yet").
- **No "Apps" / "Connected apps" section exists in Settings.**
  Searching Settings for "Google Drive" returns "No results found".
  The closest equivalent is Settings > Integrations > Plugins:
  "You haven't installed any plugins yet" / "No installed plugins".
- **The Google Drive plugin IS available:** chatgpt.com/plugins
  lists "Google Drive — Drive, Docs, Sheets or Slides" under
  Popular, with a + (add) button. It is NOT installed or connected.
  The investigation did not click it (a state change).
- **GPTs will be retired on December 11** (banner in the account):
  GPTs migrated by their creators remain available as plugins after
  that date. A custom-GPT build would be a dead end; the plugin is
  the forward-compatible route.
- **Judgment on current evidence:** the Ironwild Test setup CANNOT
  submit a V2 proposal to Drive or read a handshake from Drive
  without a person copy-pasting. 1B is unproven until the live test
  passes.

The investigation, in order (updated with the findings):

1. **The Google Drive plugin (replaces the old option 1).** Install
   / connect it on Bryan's account and confirm it authenticates to
   the intended Google account (the personal Gmail, where the
   fiction lives — NOT the business account). Then, in a chat inside
   the Ironwild Test Project, ask it to read a specific Drive text
   file (the outbox handshake) and to write/save a text file to
   Drive (the inbox proposal), verifying the actual Drive contents
   afterward. Confirm the plugin works inside Projects. **This needs
   Bryan's approval — installing/connecting the plugin is a state
   change on his account, and the live test touches his Drive.**
2. **GPT Actions against a hosted endpoint.** Superseded for now:
   there is no custom GPT to carry Actions, and GPTs retire Dec 11.
   Only if the plugin route fails, and only with Bryan's call.
3. **Browser-driven UI automation.** Fallback of last resort, as
   before — counts only if it runs unattended end to end on Bryan's
   account.

**1B acceptance (unchanged):** demonstrated end to end on Bryan's
account (paccman360 Plus, Ironwild Test Project) — the DM submits a
V2 proposal and retrieves the resulting approved handshake with no
copy-paste by Bryan or by any person. A demonstration that needs a
person in the loop is a fail, not a pass.

**1B LIVE TEST PASSED 2026-11-21 ~01:37 EST (Bryan's approval
01:32 EST).** The Google Drive plugin was installed and connected
to frncsbryn54@gmail.com ONLY (Gmail, Calendar and Contacts were
switched off in the connect dialog; the business account was never
offered and never connected; no password or phone tap needed — the
saved Google session was used). In a NEW chat inside the Ironwild
Test Project (auto-titled "Quote Google Drive File"; nothing posted
in the existing chats, no Project instructions changed), the plugin
read turn-134.md from the outbox and quoted its opening lines
exactly, and wrote ironwild-1b-write-test.txt into the Canon parent
folder ("Ironwild - Canon") with the exact marker text. **Engine
verification (Drive CLI, independent of the chat's claim):** the
file existed in the Canon folder (id
1seqKjcefUx1n7hs1ejyRaajSuFKRdJMI, text/plain); its downloaded
content matched the marker text exactly; it was then trashed (0
untrashed copies remain) and the local verification copy removed.
One hiccup, owned: the first download used the wrong CLI flag
(`--download-to`, rejected), so the file was trashed before its
content was read; it was restored, downloaded with the correct flag
(`--output`), verified, and trashed again. **What 1B still needs:**
the full acceptance — a REAL turn in which the DM (in the Ironwind
Handshake chat) submits its V2 proposal to the inbox via the plugin
and retrieves the approved handshake from the outbox, with no
copy-paste. That needs the DM's instructions to include the Drive
steps (a Lore/start-pack question, not an Engine build).

**Lore's call (2026-11-21 ~10:26 EST): keep the Project
instructions as they are; carry the Drive steps per turn message.**
The instructions sit at 7,663/8,000 characters (337 headroom); a
Drive block does not fit without trimming the spec, which Lore will
not do (the spec was already trimmed once, 9,391 → 7,663, and the
required elements — [TURN STATE] layout, narrative style 8 bullets,
hard facts, player agency, strict isolation, propose-never-apply,
rejection handling, checkpoint rule — must stay). The Drive steps are
per-turn context anyway (the file names change every turn), the turn
message carries them, and the Engine generates the turn message
every turn, so it is not a manual step for Bryan. The durable home
for the Drive steps is the turn message (Engine-generated, every
turn) + the full spec in Project Sources if a standing Drive section
is ever added there.

**1B acceptance — Turn 135 no-paste test, PASS on the submit leg
(2026-11-21 ~10:25–10:33 EST).** The DM read turn-135.md from the
outbox via the plugin (did NOT use the older pasted handshake),
played Turn 135 as a quiet day, and wrote turn-135.txt to the
Proposals inbox itself — no paste from Bryan at any step. Engine
verified independently: the file is in the inbox, and the chat block
and the Drive file block are identical line-for-line (7 lines).
Intake: prop-135-0e781bff, reviewed, 0 changes, 0 findings (narrative
flag NEW_PC_FACT — a false positive in substance, per Lore: wording
+ a correctly-dropped false claim). Lore APPROVED (submission
69d73a5f-ee6a-48b0-9a6f-3f5a654f6552). Applied with --lore-approval
after the hub cleared the session flag: 0 changes, last_swept 135
ForkA-vFINAL.4. Ticked 3 (tick 9 → 12, 138 events, invariants clean,
hash chain OK). Turn 136 handshake generated + uploaded to the outbox
(Drive file 1cP_GPBzePx0p-q_tcJTcaNyBQOZJ-5ZP, 597 words). Caveat: mid-
reply the DM requested approval for a Google Drive trash_file call
targeting a Google Doc (not part of the assignment); the browser task
DENIED it, nothing was trashed, the target doc is unidentified (the
reported URL is mangled, the reconstructed id returns 404), and the
inbox/outbox are verified intact. The plugin's approval prompt is the
backstop. The DM retrieving the Turn 136 handshake from the outbox
happens on the next turn (Turn 136); the same read already worked for
turn-135.md. Proof gate (three consecutive live turns through the
pipeline): 1 of 3 done — Turn 135. Turns 136–137 to go.

**Side note from the investigation:** the Project's Instructions
cite "ironwild-mechanic-registry.md" under REGISTRY with no stated
location or Drive link — a Lore item (the DM ruleset), not an
Engine action.

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

## 9. 0-change auto-apply (Bryan, 2026-11-21 09:30 EST)

Standing approval, the first limited standing permission under
section 0: **0-change proposals auto-apply, tick, and drop the next
handshake in the outbox. Everything else still comes to Bryan for
approval.** Built 2026-11-21 ~09:30–09:45 EST. **Narrowed the same
morning by Lore's canon guard (section 10): the auto-apply class is
a pure carry-over, not just "sweep shows 0 changes."** No seed change.
Fork A stays at v1.6. Freeze intact.

### Exact criteria (all must hold)

1. 0 changes — the sweep diff is empty (no clock, Bond, or
   resource change; a block cannot change locations through the
   sweep, so there is no location change to check).
2. 0 findings — no error, no flag.
3. Version sequencing correct — turn == last swept turn + 1, and
   State-Version == the expected next `ForkA-vFINAL.<turn-131>`.
4. Base matches — when the block carries a Base, it equals the last
   approved version. Absent Base is permitted (ChatGPT's blocks
   never carried it); the turn + version checks bind the proposal.
5. Pending decision UNCHANGED — the block's decision == the DB's
   decision, including both empty.
6. Session flag closed.
7. Pure carry-over (canon guard, section 10) — every block field
   identical to the last approved block except the State-Version/
   Turn increment: same Scene (location, tension, trade-off), same
   PC line (Bond numbers and engine statuses are DB-driven and
   masked in the comparison; anything else in the line must match),
   same Unresolved Decisions. The block's engine statuses must
   also match the DB (a status the sweep does not check must not
   hide behind the mask).

### The Turn 134 class: does NOT auto-apply

Turn 134 was 0 mechanical changes but resolved a pending decision
narratively (Unresolved Decisions went from the elite-force
question to none). The sweep's diff does not track the pending
decision (it lives in meta, not in clocks/Bonds/resources), so
"0 changes" alone would let it through — but resolving a decision
clears the auto-tick guard and is a state transition with
consequences, and the resolution's narrative content deserves a
human eye. So a resolved decision, a new decision, or a changed
decision text all come to Bryan. A block that repeats the DB's
pending decision verbatim is also held — validate flags any
carried decision (PENDING_DECISION), so it fails criterion 2
before the decision check is even reached.

### Flow (wired into the intake poll)

Intake every 15 min (`intake --auto-apply`) → for each NEW
reviewed proposal, eligibility is re-checked fresh against the
live DB (the intake-time review is stale the moment anything
ticks) → if eligible, apply in one transaction through the
binding-checked path (Drive file re-downloaded, hash verified),
tick 3, generate the next handshake, upload it to the outbox,
log the auto-apply with proposal ID + hash binding
(`runs/proposals/<id>/auto-applied.json`), mark the registry entry
`auto_applied`, and report one line to the hub (proposal ID, turn,
tick range, handshake file). If not eligible, the proposal is
HELD and its review goes to the hub for Bryan's approval, as
before. The Fork G poll is NOT auto-apply — it stays review-only.

### Failure behavior

The eligibility, fork, hash, and session checks all run before
the first write. Once the apply commits, a later failure (tick
halt, invariant problem, hash-chain problem, handshake upload
failure) leaves the apply standing and the record says so loudly
— no handshake is generated from a halted or suspect state, and
the failure goes to the hub. Nothing is silently retried.

### Test + acceptance

- `src/auto_apply.py` (`check_eligible`) + `src/run.py`
  (`attempt_auto_apply`, `intake --auto-apply --outbox`). Suite:
  129 tests (10 new in `tests/test_auto_apply.py`, incl. the
  Turn 134-class test and a refusal test that proves a held
  proposal leaves the DB untouched).
- Acceptance (record `runs/acceptance-auto-apply/acceptance.json`,
  scratch DB, env-scoped dirs, dedicated Drive test folders,
  trashed after): synthetic clean Turn 135 (0 changes, Base
  ForkA-vFINAL.3) AUTO-APPLIED — tick 9 → 12, 138 events, hash
  chain OK, handshake Turn 136 (ForkA-vFINAL.5 — the FORK's Turn
  136, not the frozen live Turn 136 vFINAL.5) in the test outbox;
  synthetic Turn 135 with a Concord Blockade 0 → 1 change HELD
  ("has 1 change(s)"). Live DB, live inbox, and live outbox
  untouched (tick 9, 104 events, last_swept 134 ForkA-vFINAL.3).
- Intake poll cron `ironwild-fork-a-proposal-intake` body updated
  to the auto-apply flow; same 15-min schedule, still ENABLED.

## 10. Canon guard for auto-apply (Lore, 2026-11-21)

Full text: `lore-auto-apply-guard.md`. The guard narrows section
9: "0-change" in the sweep sense is not enough, because a 0-change
block can carry narrative changes the sweep cannot validate (Turn
134 was 0-change AND resolved a pending decision, recorded a new
intent in the PC line, and carried a trade-off).

### The three classes

- **AUTO-APPLY** (no Lore call, no Bryan approval): sweep shows
  changes [] and findings [], AND the block is a pure carry-over
  (section 9, criterion 7). The DM echoed the state and advanced
  the story without changing any recorded fact.
- **LORE CALL** (does NOT auto-apply; Lore decides APPROVE vs
  ESCALATE to Bryan): a 0-change proposal where any of these hold:
  (a) pending decision resolved or introduced; (b) scene change
  (location, tension, trade-off); (c) new PC fact (a new choice,
  intent, condition, rumor, or callback in the Player character
  field); (d) new rumor or callback in the DM's reply narrative;
  (e) any other narrative addition the sweep cannot validate.
  Lore reviews the field diff and the full reply, then returns
  APPROVE (apply it) or ESCALATE (to Bryan).
- **BRYAN** (never auto-applies): any proposal with changes
  non-empty; any proposal with findings non-empty; any proposal
  Lore flags as drift; any unresolved disagreement; any proposal
  that touches a sealed mystery, Turn 136 content, a resurrection,
  or a new mechanic; any proposal where the DM narrated Brigus
  making a choice Bryan did not make.

### Engine implementation

- `src/auto_apply.py: flag_narrative_changes` compares the block
  against the last approved block's carried record
  (`runs/sweeps/turn-<n>/carried.json`) and flags (a) PENDING_
  DECISION, (b) SCENE_CHANGE, (c) NEW_PC_FACT, plus
  STATUS_MISMATCH (a block status contradicting the DB — a
  mechanical drift the sweep does not check) and NO_BASELINE (no
  prior carried record to compare against). The PC comparison
  masks Bond numbers and engine statuses (both move through
  ticks), then verifies the block's statuses against the DB so a
  wrong status cannot hide behind the mask.
- Routing in `src/run.py: attempt_auto_apply`: pure carry-over →
  auto-apply; a 0-change proposal with narrative flags and no other
  blocker → `LoreCall` (the intake prints a LORE-CALL line with
  the flag codes, details, and the block file path; the poll worker
  sends the field diff + block to Lore); anything else → HELD for
  Bryan.
- A flagged proposal Lore approves is applied through the normal
  path with `--lore-approval <submission-id>` and recorded as
  Lore-approved (`runs/proposals/<id>/lore-approved.json` + the
  registry mark), not as a pure auto-apply.
- Coverage limit, stated plainly: (d) and (e) cannot be checked
  from the block file — the Drive inbox carries only the V2 block,
  not the reply narrative. They are covered two other ways: the
  handshake generator emits rumors only from logged events (an
  invented narrative rumor never enters the next handshake), and
  Lore's post-apply audit of the first auto-applied turn plus the
  formal 3-turn checkpoint cover the narrative.

### Lore's post-apply audit

Lore verifies the first auto-applied turn after it lands (flag any
drift). After that, the formal 3-turn checkpoint covers
auto-applied turns. If drift is found post-apply, Lore flags it to
the hub and the Engine rolls back or Bryan decides.

### Test + acceptance

- Suite: 139 tests (10 new in `tests/test_auto_apply.py` for the
  flag comparison and the Lore-call routing, incl. a Bond-only PC
  change that is NOT flagged and a status mismatch that IS).
- Guard acceptance (record
  `runs/acceptance-guard/acceptance.json`, fresh scratch DB,
  env-scoped dirs, dedicated Drive test folders, trashed after):
  synthetic Turn 135 with a scene change → LORE-CALL
  (SCENE_CHANGE, not applied); synthetic Turn 135 with a Concord
  Blockade 0 → 1 change → HELD for Bryan; synthetic pure
  carry-over Turn 135 → AUTO-APPLIED (tick 9 → 12, 138 events,
  hash chain OK, handshake Turn 136 ForkA-vFINAL.5 in the test
  outbox). Live DB, live inbox, and live outbox untouched.

## 11. Scheduler guard — cadence decided (Bryan, 2026-11-21 13:22 EST)

Bryan DECIDED: **"Tick only when I play, 3 days per turn, like
now."** That answers the scheduler design's questions 3 and 4
together (design doc `scheduler-guard-design.md`, all four
questions now answered):

- Tick cadence is play-time only: the scheduler runs as part of a
  played turn — 3 ticks per played turn under the DF Adventure
  Mode guard (scheduler mode when a decision is pending, full
  otherwise).
- No daily auto-tick. The daily auto-tick cron
  (`ironwild-fork-a-daily-tick`) stays DISABLED.
- No catch-up for days missed.

Consequences recorded in the design doc: the `run_auto_tick`
mode-switch is superseded (it keeps its pending-decision refusal
as written, since it never runs on a schedule); the scheduler mode
is driven by the played-turn tick, not by auto_tick. The guard
itself (Lore's DF guard, `lore-df-adventure-guard.md`) is
unchanged — frozen items protected, skips logged, no override.

**The design as now decided waits on Bryan's approval to build.**
No seed change. Fork A stays at v1.6. Freeze intact.
