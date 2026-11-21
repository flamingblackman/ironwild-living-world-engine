# Canon guard for the auto-apply class — Lore Team

Bryan APPROVED, 2026-11-21 09:30 EST: 0-change proposals auto-apply, tick, and drop the next handshake in the outbox. Everything else still comes to Bryan for approval.

**Bryan DECIDED, 2026-11-21 14:55 EST (supersedes the Lore-call routing above): Bryan is hands off with Lore approval. Lore approves the narrative flags — SCENE_CHANGE, NEW_PC_FACT, and the rest — without Bryan. Bryan approves ONLY the important things: mechanical changes, new or resolved pending decisions, sealed mysteries, resurrections, new mechanics, anything Lore escalates. If something in the story is wrong, Bryan will tell us himself. No more asking Bryan for a Lore-call approval.**

## The problem the guard solves

"0-change" in the sweep sense means the block matches the DB mechanically (changes [], findings []). But a 0-change block can still carry narrative changes the sweep cannot validate. Turn 134 was a 0-change block (sweep: changes none, findings none) AND it resolved a pending decision narratively (Brigus chose the rapid-response force), recorded a new intent in the PC line, and carried a trade-off. The sweep cannot tell whether that narrative is canon-clean. Lore can. So the auto-apply class is narrower than "sweep shows 0 changes."

## The line

### AUTO-APPLY — no Lore call, no Bryan approval

A proposal where the sweep shows changes [] and findings [], AND the block is a pure carry-over: every field identical to the last approved block except the State-Version/Turn increment. Same Clocks, same Scene (location, tension, trade-off), same PC line (verbatim), same Unresolved Decisions (verbatim). The DM's narrative adds no new rumor, no new callback, and does not narrate Brigus making a choice. This is routine bookkeeping — the DM echoed the state and advanced the story without changing any recorded fact.

### LORE CALL — does NOT auto-apply; Lore approves the narrative flags without Bryan

A 0-change proposal (sweep changes [] and findings []) where ANY of (b)–(e) hold. Lore reviews the field diff and the full reply, then returns APPROVE (apply it) or ESCALATE (to Bryan, if something is wrong or uncertain). **Lore's APPROVE on (b)–(e) is final — no Bryan approval is needed. No more asking Bryan for a Lore-call approval (Bryan, 2026-11-21 14:55 EST).** If something in the story is wrong, Bryan will tell us himself.

(a) **Pending decision resolved or introduced — goes to BRYAN, not Lore.** The Unresolved Decisions field differs from the last approved block (a pending question was answered, or a new question was added). Lore verifies: did Bryan actually make this choice (in chat, or by an approved test move)? Does the resolution match what Bryan chose and match canon? Lore verifies and forwards it to Bryan for approval. Bryan approves new or resolved pending decisions (Bryan, 2026-11-21 14:55 EST). If the DM chose for Brigus (player agency violation) or the resolution contradicts canon, Lore flags drift and it goes to Bryan.

(b) **Scene change.** The Scene field differs from the last approved block (new location, new tension, or new trade-off). Lore verifies: is the location real and reachable? Does the tension match the fiction? Is the trade-off valid (carried, or a legitimate new one)? If yes, Lore approves it for apply (final, no Bryan approval needed). If it contradicts canon, Lore flags drift and it goes to Bryan.

(c) **New PC fact.** The Player character field adds text beyond the carried facts (a new choice, intent, condition, rumor, or callback). Lore verifies it against canon. If it matches canon and Bryan's intent, Lore approves it for apply (final, no Bryan approval needed). If it invents a fact or contradicts canon, Lore flags drift and it goes to Bryan.

(d) **New rumor or callback in the narrative.** The DM's reply narrative introduces a rumor not in the handshake's Rumors live list, or a callback not in the handshake. Lore verifies it traces to a logged event (rumor) or established canon (callback). If yes, Lore approves it for apply (final, no Bryan approval needed). If it was invented, Lore flags drift and it goes to Bryan.

(e) **Any other narrative addition the sweep cannot validate.** Lore approves it for apply if it is canon-clean (final, no Bryan approval needed). If it contradicts canon, Lore flags drift and it goes to Bryan.

### BRYAN — never auto-applies

- Any proposal with changes non-empty (mechanical change).
- Any proposal with findings non-empty.
- Any proposal that resolves or introduces a pending decision (Bryan approves new or resolved pending decisions — Bryan, 2026-11-21 14:55 EST).
- Any proposal Lore flags as drift.
- Any unresolved disagreement (Lore flags it, Bryan decides).
- Any proposal that touches a sealed mystery, Turn 136 content, a resurrection, or a new mechanic.
- Any proposal where the DM narrated Brigus making a choice Bryan did not make (player agency violation).
- Anything Lore escalates.

## Engine implementation

For each 0-change proposal, compare the block fields to the last approved block and flag which of (a)–(e) apply. If none apply, auto-apply. If (a) applies (pending decision resolved or introduced), send it to Bryan for approval (Lore verifies first and forwards it). If only (b)–(e) apply, send to Lore for a call with the field diff and the full reply. Lore returns APPROVE (apply it — final, no Bryan approval needed) or ESCALATE (to Bryan). The Engine must NOT auto-apply a flagged proposal, even if the sweep shows 0 changes. A flagged proposal that Lore approves is recorded as Lore-approved, not as a pure auto-apply, so the audit trail shows who cleared it. **The lore-approved record must carry Lore's submission ID (not a hub-relay ID) for traceability.**

## Lore's post-apply audit

Lore verifies the first auto-applied turn after it lands (post-apply audit, flag any drift). After that, the formal 3-turn checkpoint covers auto-applied turns (schema, mechanical accuracy, continuity, no unapproved state changes). If drift is found post-apply, Lore flags it to the hub and the Engine rolls back or Bryan decides. No seed change. Fork A stays at v1.6. Freeze intact.
