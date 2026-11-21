# Stage 2 plan — Automatic loop (Fork A)

**Status:** APPROVED by Bryan in the Fiction & Worldbuilding hub chat, 2026-11-21 14:59 EST. Build now.
**Date:** 2026-11-21
**Supersedes:** Stage 1's approval note ("approval policy is preserved until Bryan explicitly defines and approves limited standing permissions"). Bryan has now defined and approved the boundary below.

## 0. Design objective (Bryan, 2026-11-21 14:55 EST)

Simplify and automate. The current way is convoluted and confusing. Everything reads each other more seamlessly, with the engine triggering automatically, not waiting on manual steps. Bryan plays a turn (story only). Everything else happens on its own. Bryan approves ONLY the important things.

## 1. The loop (automatic)

1. ChatGPT reads the latest handshake from the Drive outbox on its own (Project instructions Drive handoff rule, live 2026-11-21 14:40 EST, + Drive plugin). No Bryan paste.
2. Bryan plays a turn. Story prompt only, in the ChatGPT chat. This is the only thing Bryan types.
3. ChatGPT writes the [TURN STATE] block to the Drive Proposals inbox as turn-<N>.txt on its own (same Project instructions rule + Drive plugin). No Bryan write instruction.
4. The Engine intake (15-minute poll, automatic) picks up the new file and sweeps it.
5. Pure carry-over (0 changes): auto-apply, tick 3, next handshake to the outbox. No human in the loop.
6. 0-change with narrative flags: Lore approves (or escalates to Bryan). On APPROVE, apply, tick 3, next handshake. Bryan is hands off.
7. Changes, findings, or a pending decision / mechanic / mystery issue: hold for Bryan. Bryan decides.
8. The next handshake lands in the outbox. ChatGPT reads it for the next turn. Loop repeats.

## 2. Approval boundary (recorded plainly, Bryan 2026-11-21 14:55 EST)

**Auto-applies, no human:** pure carry-overs. 0 changes, 0 findings, correct turn/version sequence (turn == last swept turn + 1, State-Version == ForkA-vFINAL.<turn-131>), Base matches when present, pending decision unchanged, session flag closed. (Bryan's standing approval, 2026-11-21 09:30 EST, 0-change only.)

**Lore approves, Bryan hands off:** 0-change proposals with narrative flags (SCENE_CHANGE, NEW_PC_FACT, STATUS_MISMATCH, NO_BASELINE, pending decision resolved/introduced as a narrative flag). Lore's APPROVE is the binding; the apply is recorded as Lore-approved. Bryan trusts Lore's call and is hands off here. Bryan will tell us himself if something in the story is wrong.

**Bryan decides, still needs him:** mechanical changes (Bonds, clocks, resources, locations change); new or resolved pending decisions; sealed mysteries; resurrections; new mechanics; anything Lore escalates. Anything with changes/findings goes to Bryan.

## 3. What changes from Stage 1

- ChatGPT leg becomes automatic (Project instructions Drive handoff rule). No more Bryan pasting handshakes or typing write instructions.
- Engine leg is already automatic (15-minute intake poll triggers on its own when a turn lands). No change needed there.
- Lore's approval is explicitly sufficient for narrative flags. No per-turn Bryan approval for Lore-cleared proposals.
- The approval boundary is written down here, so there is no ambiguity about what needs Bryan.

## 4. What stays the same

- The freeze: live Turn 136 sequel stays frozen (Crown of Cold Iron, Krov ambush decision pending). The engine never advances it.
- The session flag: only hub/Lore set or clear it. The Engine never sets or clears it.
- Drive folders are the single source of truth (Proposals inbox, Handshakes outbox, Canon).
- The seed (Fork A v1.6), the tick rule (3 ticks per played turn), the DB.
- No live tick (live world does not exist yet).
- No LLM ever writes state (rules first, narration second, narration deferred).

## 5. ChatGPT leg — test result and fallback

**Turn 138 test (2026-11-21): the auto-save did NOT work for Turn 138.** Checked the Proposals inbox live at 14:59 EST: no turn-138.txt. Bryan played Turn 138 story-only and ChatGPT did not save the block. The Project instructions Drive handoff rule is live, but ChatGPT does not follow it reliably.

**The auto-save is intermittent, not dead.** The same live inbox check found turn-145.txt (saved 14:48:56 EST) and turn-147.txt (saved 14:51:36 EST) — ChatGPT saved those two on its own, but not turns 138-144 or 146. So the rule works sometimes and not others. That is worse than fully broken for a system that must run on its own.

**Fallback (Stage 2, approved design):** when a turn's block is not in Drive, the Engine pulls it read-only from the ChatGPT chat and files it as turn-<N>.txt, then runs the pipeline. Used for Turn 137 (Reply B) and Turn 138 (second reply, "The Road Calls", the consolidated state). This keeps the loop moving but adds a manual Engine step. Longer-term fallback if the intermittency persists: a custom GPT with a Drive Action that saves on every turn.

**Out-of-sequence files:** turns 145 and 147 are in the inbox and registered (prop-145-910cbb96, prop-147-7b01cb62; reviewed, 0 changes, 0 findings) but out of sequence — they wait until the pipeline catches up through Turns 138-144 (and 146, which is not in Drive). They are not applied out of order.

## 6. Checkpoint freeze-scan fix (2026-11-21)

The 3-turn checkpoint for Turns 135-137 first ran FAIL on continuity: 1 frozen-term hit, event 139. Verified false positive. Event 139 is the Turn 136 sweep note (the engine's own bookkeeping): "sweep Turn 136 ForkA-vFINAL.5: 0 change(s), Lore-approved". The freeze scan matched the separate substrings "turn136" and "vfinal5", which the Fork A test Turn 136 label ("Turn 136 ForkA-vFINAL.5") also contains. No live sequel content (Krov, Mother Bulwark, Rider Army, Crown of Cold Iron, Sanctuary Integration, Outer Siege Ring, Northern Pass) appears in any event. One-time collision, only Turn 136 can trigger it.

Fix (src/checkpoint.py): match the live label as one contiguous term, "turn136vfinal5", instead of the two separate substrings. The live frozen label "Turn 136 vFINAL.5" normalizes to "turn136vfinal5"; the Fork A label normalizes to "turn136forkavfinal5", which does not contain it. All 146 tests pass. The Turns 135-137 checkpoint now PASSES (0 failures), completing the proof gate (3 consecutive live turns: 135, 136, 137).

## 7. Validation

- Turn 138 test: auto-save FAILED for Turn 138 (see section 5). Fallback used; Turn 138 is in the pipeline (prop-138-21644a4b, LORE-CALL sent to the hub).
- Proof gate: Turns 135-137 checkpoint PASSES after the freeze-scan fix (section 6). Gate complete.
- End-to-end: verify one live turn through the automatic loop once Turn 138 applies (apply, tick 3, Turn 139 handshake to the outbox).

## 8. Build plan (after approval — in progress)

1. Confirm the Turn 138 test result. DONE (auto-save failed for 138; intermittent — 145/147 saved).
2. Fix the checkpoint freeze scan. DONE (contiguous "turn136vfinal5"; checkpoint PASSES; 146 tests pass).
3. Write the approval boundary into the run docs. DONE (this file, section 2).
4. Verify end-to-end with one live turn through the automatic loop. PENDING (Turn 138 in the pipeline; Lore verdict awaited).
5. Report back to the hub, one batched message, when Stage 2 is live. PENDING.
