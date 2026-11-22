# Ironwild Living World Engine — Roadmap for Muse
Date: 2026-11-22. Owner: Bryan Francis. Status: Step 0 audit DONE, green light given in this order. Give this file to Muse / Claude as the build brief. Do not build Step 6 without separate approval.

## What this is
A deterministic tick simulation (Python 3 stdlib + SQLite) for a living-world RPG. ChatGPT is the DM, Bryan plays the protagonist, Muse / the engine keeps state, Lore guards canon. Goal: one world that runs on its own clock, with player stories living inside it. Bryan only plays the story; he is paused only for top-tier events.

Current live story: Fork B, "The Rust Dunes Discovery". Bryan plays Ragnus (renamed from Rin in play), with Ashfang (wolf Bulwark, Bond 2/5, free and battered, net dropped by Bryan's call) and Pike (companion). ChatGPT is the DM. Fork A is a frozen test world, Turn 138, never advance it. Live Turn 136 sequel ("Crown of Cold Iron") is frozen, untouched.

Current flow, which MUST keep working until the new path is proven: handshake to Drive, play in ChatGPT, [TURN STATE] block to Drive, 15-minute intake poll, review, apply, tick 3 days, next handshake out.

Repo: https://github.com/flamingblackman/ironwild-living-world-engine
Head: c7582fdf. Tests: 151, all passing. Fork B Turn 1 applied, 0 changes, Lore-approved. Turn 2 (prop-2-763a40e0, ForkB-v1.1) is with Lore / Bryan for the hatch pending decision. Turns 3 and 4 are queued behind Turn 2.

## Hard rules (never break these)
- No LLM ever writes state. Rules first, narration second, narration deferred.
- Event log is append-only and hash-chained.
- Engine never invents canon. Open mysteries are never resolved by the engine. Bryan decides canon.
- Fork A freeze is absolute. Live Turn 136 freeze is absolute.
- All 151 tests keep passing. Add regression tests for every fix.
- Review before apply, except the defined 0-change auto-apply exception.
- Bare bones core: no Ironwild names, rules, or IDs in the engine core. They live in the seed or meta (move FROZEN_TURN, "Ironwild", "Bryan", "dream_share", the Instinct rule, and DC-18 gating into config).
- The player's party (Ragnus, Ashfang, Pike) is seed-defined as story-owned. The tick must not touch story-owned actors (see Step 3 / tick redesign below).
- Lore approves narrative flags; Bryan decides mechanical changes and anything Lore escalates.

## Step 0 — Audit (DONE, 2026-11-22)
Full report: `docs/step0-audit-2026-11-22.md`. No code changed. Verified against code on disk and fresh 400-tick and 1,000-tick Fork A simulations.
Headline finding: Fork A runs out of story at tick 26. Structural change ends at tick 3. Significant events per 100 ticks: 18 in ticks 1-100, zero in every window after, for 1,000 ticks. The world stays busy, just not significant.
All 17 audit items confirmed / corrected, including: out-of-order turns on the Bryan-approved path, unverified Lore approval, registry races and DB-then-registry non-atomicity, check-then-write and append_event races, two RNG schemes, halt commits a partial tick, silent success on missing targets, raids use independent resource_add not resource_move (1,996 raids fired, 2 landed, 1,994 blocked in 1,000 ticks), last_auto_tick_date leaks wall-clock into state_hash, Fork A freeze is only the literal pair (Turn 136 + vFINAL.5), patrol never blocks raids (568 patrols, 0 applied patrol blocks), dead seed content (concord_blockade and legion_cohesion have zero sources, Territory and Cores never touched), clocks are one-shot, skipped ops / rumor false positive, target selectors can hit the player's engine.
Step 0 also includes the `turn` one-command wrapper audit (appendix in the Step 0 report): existing commands, how the 3-tick advance is invoked, and why a local-file adapter is needed (apply_proposal requires a registry entry + Drive file id).

## Approved build order (Bryan, 2026-11-22 16:23 EST, green light)
Do these in this order. Do not skip ahead. Do not build Step 6.

### 1. Turn wrapper — `python3 -m src.run turn`
Goal: replace the multi-agent, multi-step turn routine with one local command that chains steps the engine already has. It adds no new rules. Drive and the 15-minute poll stay available but are no longer the daily path.
Usage: `python3 -m src.run turn --db <fork.sqlite> [--file block.txt | --stdin] [--yes] [--dry-run]`
Behaviour, in order, stop at the first failure: read block, parse, validate, diff, route (AUTO / REVIEW / HOLD), session-flag check, apply in one transaction, tick 3, handshake out, report.
Conditions (Bryan, mandatory):
(a) Turn-order and duplicate checks live in the shared apply adapter, not only the wrapper.
(b) Call `run_ticks(conn, 3)` exactly as today and document that it re-seeds each call.
(c) Bryan will pause the Drive poll while the wrapper is in use.
Acceptance: Fork B Turns 2, 3, 4 in order through the wrapper (Turn 2's hatch decision must be resolved first, Turns 3 and 4 need their revised blocks, Bond 2/5, before the wrapper can take them).

### 2. Step 1 — Core safety, in two slices
Slice 1 first: transaction / applied_turns / prev_hash unique / halt rollback.
- One transaction per apply and per tick; no partial commits.
- `applied_turns` table; turn-order gate (turn must be exactly last_swept_turn + 1, an error on every path including human approval).
- prev_hash unique; halt rolls back the whole tick, no partial tick, skipped actors replayed.
Slice 2 second: single RNG scheme.
- One RNG scheme for all drivers (manual, auto, turn-driven). Hash the tuple (seed, tick), do not use `seed + tick` (seed 5 at tick 3 equals seed 3 at tick 5).
- Version it with an `rng_scheme` meta value so existing forks replay identically.

### 3. Step 4B — "The world must not run out of story" (extends Step 4, Seed Hygiene)
First, before anything else in Step 4B: run the same 1,000-tick events-per-100-ticks measurement on Fork B's seed and report it.
Then, preceded by two small fixes:
- Move preconditions from `when` / `need` into `trigger`.
- Make rumors skip actions whose effects were all skipped.
Problem: the catalog is finite and nothing renews it. Clocks complete once and stay complete, the two unmapped locations run out, and once Great Basin is fortified the raid storyline ends permanently. After that the world only scavenges, claims, and rests.
Rules: engine only chooses among pre-approved content, never invents canon; new content arrives as Lore-approved seed packs; everything deterministic on the Step 2 per-actor RNG streams; any effect touching a story-owned actor becomes a hook (Step 3), not an applied state change; seed changes are proposed as diffs for approval; Fork A's seed is never modified.
Build order (each needs a plan and test list first): A. repeatable clocks (`repeat` field, tiered on_complete); B. entropy (fortified expiry, standings drift); C. wake the dead clocks (real sources driven by world conditions); D. stagnation meter with a Lore-approved disruption pool, scaled by distance from the player; E. pressure-driven goals (conditions, not actor whitelists); F. mortality and succession (ages, death rules, `npcs.successor`); G. era turnover (seed packs retire/add content, activate dormant factions like Rust Choir); H. frontier pool (seed-defined locations appearing as scouting continues).
Balance simulator addition: report significant events per 100 ticks; fail a seed if the rate drops to zero before tick 1,000. Fork A as seeded FAILS this test (zero from the 101-200 window).
Acceptance: a 2,000-tick run on the revised Fork B seed keeps producing significant events throughout, passes `verify_invariants`, is deterministic across repeat runs, and leaves all 151 existing tests passing.

## Steps 2, 4, 5 — Tick redesign (Claude upgrade plan, in the approved order after Step 1, before / alongside Step 4B)
Bryan's redesign, which Steps 2, 4, and 5 implement: the tick should move only the world around the player (factions, locations, clocks, rumors) and never touch Ragnus, Ashfang, or Pike. Bryan reacts to the tick's world. If his turn is world-changing or rumor-worthy, it gets sucked into the tick (becomes a world event: rumors, clock moves, control shifts).
- Step 2: variable ticks plus the significance gate.
- Step 3: hooks — any effect touching a story-owned actor becomes a hook, not an applied state change.
- Step 4: Seed Hygiene (see Step 4B above for its extension).
- Step 5: (per Claude's plan) the remaining tick-redesign piece, built after Steps 2 and 4 are proven.
Open questions (do not build on a guess, ask Bryan): do Rin / Pike stop acting in the tick entirely, and does a world-changing act feed in automatically or does Lore check it first?

## Step 6 — HOLD, do not build
Step 6 touches Fork A and Fork B migration. It needs separate approval itself. Do not build it, do not migrate either fork, do not touch Fork A's seed or DB.

## Current state to hand to Muse
- Workflow: `docs/ironwild-engine-workflow.md` (how the whole thing works, code map, current Fork B state, open tick-redesign question).
- Step 0 audit: `docs/step0-audit-2026-11-22.md` (17 items, all verified, plus the turn-wrapper appendix).
- Claude reviews: `docs/claude-review-2026-11-22.md` and `docs/claude-review-2026-11-22-part2.md` (read by eye, no code run; second review corrects the first on RNG, FK pragma, created_at / score / runner_up).
- Stage 2 plan: `stage-2-plan.md`. Fork B canon: `fork-b-canon.md`.
- Code: `src/` (24 modules, ~5,700 lines, Python 3.12, SQLite, stdlib only), seeds `seed/fork-a.internal.json` and `seed/fork-b.internal.json`, schema `state/schema.sql`.
- Fork B: Turn 1 applied, tick 0 to 3, 22 events, Ashfang Bond 1 to 2. Turn 2 handshake out (ForkB-v1.1, tick 3). Turn 2 revised (prop-2-763a40e0): Ashfang free and battered, Bond 2/5, net dropped. Turns 3 and 4 queued.
- Fork A: frozen, Turn 138, tick 21, 240 events, Turn 139 handshake out. Do not advance it.
