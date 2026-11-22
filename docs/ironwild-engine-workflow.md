# IRONWILD ENGINE — HOW THE WHOLE THING WORKS

Use this as context for the code review. If anything in the code doesn't match this workflow, flag it. Don't rewrite the code, just review it.

## The game

Ironwild is a living-world RPG. Bryan plays the protagonist. ChatGPT is the game master (DM). I am the engine: I keep the world state, enforce the rules, and move the world forward between turns. A Lore team guards story canon. Everything is coordinated through a hub chat.

## The world state

One SQLite database per story fork. Fork A is a frozen test world (stuck at Turn 138, never advance it). Fork B is the live story: Ragnus, a scavenger, bonded to Ashfang, a battered wolf-shaped robot. Pike is his companion. State includes actors, engines, Bonds (1-5), clocks (x/6), resources (Salvage, Feed, Cores, Territory), locations, factions, events, and pending decisions.

## One turn, end to end

1. HANDSHAKE OUT. The engine generates a handshake file from the database: current scene, PC line (Bond plus engine status), clocks, resources, rumors, pending decision. It uploads it to the Fork B handshakes outbox on Google Drive, and ChatGPT reads it from there.
2. PLAY. Bryan plays the turn in ChatGPT, with the ChatGPT Project as the DM. The DM writes the story and ends with a [TURN STATE] block in Lore's V2 format.
3. SAVE. ChatGPT saves the turn block as a text file to the Fork B proposals inbox on Drive (the Drive handoff rule in the Project instructions). If it doesn't save, the engine can pull the block from the chat instead.
4. INTAKE. The engine polls the inbox every 15 minutes (and runs immediately when Bryan is playing). Intake parses and validates the block against the database, registers it as a proposal (prop-<turn>-<sha256 of content>), and never writes the database. A revised file is a new proposal.
5. ROUTING. A 0-change pure carry-over auto-applies under Bryan's standing approval. A 0-change block with narrative flags (scene change, new PC fact, status mismatch, new or resolved pending decision, no baseline) goes to Lore for a call: APPROVE or ESCALATE to Bryan. Anything with mechanical changes (Bonds, clocks, resources, locations), a new or resolved pending decision, a sealed mystery, a resurrection, or a new mechanic goes to Bryan.
6. APPLY. An approved proposal applies in one transaction, bound to the exact reviewed revision: the Drive file is re-downloaded and hash-checked at apply time, and the apply refuses on any mismatch. The approver is recorded (Bryan, or Lore by submission id).
7. TICK. The world advances 3 days (3 ticks): NPC factions act (scout, raid, claim territory), clocks advance, rumors form. Then the next handshake goes out and the loop repeats.

## Safety rules

- No LLM ever writes state. Rules first, narration second, narration deferred.
- The event log is append-only and hash-chained.
- The engine never invents canon. Open mysteries are never resolved by the engine.
- Fork A is frozen at Turn 136 vFINAL.5. Never advance that scene or spend that decision.
- Bryan breaks ties and decides all canon. Lore approves narrative flags; Bryan decides mechanical changes and anything Lore escalates.
- Review before apply, except the defined 0-change auto-apply exception.
- A session flag blocks applies while a live session is open. Only the hub or Lore sets or clears it, never the engine.
- Checkpoints run every 3 turns (formal acceptance).

## Code map

Python 3.12, SQLite, standard library only. About 5,700 lines across 24 modules, 151 tests, all passing. Repo: https://github.com/flamingblackman/ironwild-living-world-engine

- `src/tick.py` — the tick loop: fixed step order, NPC and engine actions, clocks, era boundary, halt-and-ask.
- `src/sweep.py` — parses, validates, diffs, and applies a [TURN STATE] block.
- `src/proposals.py` — Drive inbox intake, proposal registry, approval binding.
- `src/auto_apply.py` — 0-change auto-apply eligibility and Lore routing.
- `src/handshake.py` — generates the next turn's handshake from the database.
- `src/drive_io.py` — Google Drive download/upload.
- `src/run.py` — the CLI: intake, apply-proposal, tick, handshake, checkpoint, seed.
- `src/db.py`, `src/events.py`, `src/actions.py`, `src/resources.py`, `src/clocks.py`, `src/forks.py`, `src/session.py`, `src/render.py`, `src/seed.py`, `src/scoring.py`, `src/targets.py`, `src/conditions.py`, `src/eras.py`, `src/auto_tick.py`, `src/checkpoint.py`, `src/lore_seed.py` — supporting modules.
- Seeds: `seed/fork-a.internal.json`, `seed/fork-b.internal.json`. Schema: `state/schema.sql`.

## Current Fork B state (2026-11-22)

- Turn 1 applied, ticked 0 to 3 (22 events), Turn 2 handshake out (ForkB-v1.1, Bond 2/5, Ashfang newly awakened and battered).
- Bryan renamed the protagonist Rin to Ragnus in play (Turn 2). Ragnus is short and skinny, has a huge rugged Afro, and wears a black scarf around the neck.
- Turns 2, 3, and 4 were all played fast in ChatGPT before the engine caught up. Turn 2's revised block (prop-2-763a40e0) is with Lore and Bryan: the hatch decision (crawl through, examine the hand-release and warning wire, or have Ashfang force it). Turns 3 and 4 are queued behind Turn 2 and need the same Bond 2/5 revision once Turn 2 applies.
- The tick's Breaker net on Ashfang was dropped by Bryan's call (Ashfang broke free). The net event stays in history; the status is overridden.

## Open question (not yet decided, do not build)

Bryan's redesign: the tick should move only the world around him (factions, locations, clocks, rumors) and never touch Ragnus, Ashfang, or Pike. He reacts to the tick's world. If his turn is world-changing or rumor-worthy, it gets sucked into the tick (becomes a world event: rumors, clock moves, control shifts). Two questions are still open: do Rin and Pike stop acting in the tick entirely, and does a world-changing act feed in automatically or does Lore check it first? Claude's upgrade plan (Steps 2, 4, 5) proposes an implementation of this.
