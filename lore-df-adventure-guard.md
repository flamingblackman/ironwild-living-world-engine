# Canon guard: Dwarf Fortress Adventure Mode shape — off-screen simulation while a decision is pending

Bryan DECIDED, 2026-11-21 10:22 EST. This guard SUPERSEDES the earlier pending-decision guard (2026-11-21 00:48 EST: "keep the guard as written. The world freezes on a pending decision"). The world no longer freezes entirely. It follows the Dwarf Fortress Adventure Mode shape.

## The shape (Bryan's words, paraphrased)

DF keeps the world simulating off-screen while the player is elsewhere — NPCs, armies, factions keep moving, history keeps happening — the player's immediate scene and choice stay open, the world does not wait for the player, but it never makes the player's decision for them.

## What this means for Fork A

The auto-tick no longer refuses outright when a pending decision is recorded. It ticks the off-screen world, but it protects the frozen items. The tick never resolves the pending decision, never advances Brigus's scene, and never takes an action that would force the decision.

## FROZEN while a decision is pending — the tick must not touch these

1. **Brigus's scene.** The DM's scene (location, tension, trade-off) does not advance. The DM does not open a new scene, arc, or Session Zero. (Already in the handshake's first-reply instruction: "Do not advance the scene until Brigus acts.")
2. **The pending choice.** The pending decision stays pending. No NPC, no tick, no DM narration resolves it, answers it, or makes it moot. Only Bryan (the player) resolves it by making the choice.
3. **Brigus's location and Wounds.** Brigus does not move, and his Wounds do not change, through off-screen simulation. (The engine has no tick action that moves Brigus or wounds him; this is a guard, not a new mechanic.)
4. **Brigus's Engines' status.** No off-screen action may change the status of one of Brigus's five Engines (netted, damaged, or any other status change). An Engine's status changes only through Brigus's own actions, a repair Brigus directs, or a DM-played event — never through off-screen simulation while a decision is pending. (Bond numbers and Hunger may still move through the allowed actions below; a status change is a hostile or dramatic event, and it would force Brigus to respond.)
5. **Any NPC action that would force the decision.** Forbidden while a decision is pending:
   - An NPC action that resolves the pending question (e.g., an NPC selects the elite force type).
   - An NPC action that makes the pending question moot (e.g., the engineers, salvage, or labor the decision concerns are destroyed, so there is nothing to decide).
   - An NPC action that presupposes an answer (e.g., an NPC spends salvage on assault-force equipment, assuming the assault force was chosen).
   - An NPC action that requires Brigus to act immediately (e.g., an attack on Brigus's location or Engines that demands a response).
   - An NPC action that changes the facts the decision is about (e.g., the trade-off's engineers/salvage/labor are spent or destroyed).
6. **Any NPC action that enters Brigus's immediate scene.** An NPC moving into Brigus's location, or an action whose effect lands in Brigus's location, is forbidden while a decision is pending. The NPC acts elsewhere or waits.

## ALLOWED — off-screen movement while a decision is pending

The world keeps simulating away from Brigus's scene. All of these are allowed, and their events are logged (so rumors can trace to them):

1. **NPC actions away from Brigus's scene.** NPCs at other locations (Nest-Keeper in Chalk Canyons, Caravan Master at Concord Camp, Dust-Baron Captain in Rust Dunes, Breaker Poacher Chief, High Baron, Legion Captain away from Great Basin) act normally: hunt, forage, scavenge, trade, tend the den, rest, claim (away from Brigus's scene). Their actions change resources, clocks, and their own locations/statuses.
2. **Faction resource movement away from Brigus's scene.** Trade, forage, scavenge, claim, and resource moves continue. Resources move between factions and the Pack.
3. **Clocks advancing.** Clocks (Dust-Baron Retaliation, Concord Blockade, Legion Cohesion, and any future clock) advance when their triggers fire through off-screen actions. A clock firing is a world event, not a player decision. But a clock's completion effect must not force the pending decision (if it would, the effect is deferred until the decision is resolved — see Enforcement).
4. **Raids that are blocked or target elsewhere.** A raid on Great Basin is blocked (fortified) — already the engine's behavior (flag + note, no state change). A raid on another location may proceed, subject to the existing halt rules (a raid on Concord Camp halts the engine; Lore names a fallback — the engine stops instead of improvising).
5. **Dream Share / Bond recovery.** Dream Share restores a Bond (mechanical recovery, Pack Feed -2). It is allowed: it is not a decision, it is the world's simulation (Brigus rests/dreams, a Bond recovers). It changes a Bond number, not a status, not the pending decision.
6. **Hunger and feeding.** Engines' Hunger moves through hunt/feed_engine, including Brigus's Engines (they eat, they get hungry). Hunger is a need, not a decision. A status change (netted, damaged) is NOT allowed (see Frozen #4).
7. **NPC movement away from Brigus's scene.** NPCs may move between locations, as long as they do not move into Brigus's location (see Frozen #6).

## Enforcement — how the tick protects the frozen items

Before applying an action, the tick checks whether it touches a frozen item (Brigus's scene, the pending decision, Brigus's location/Wounds, a Brigus Engine's status, or an action that would force the decision). If it does, the tick SKIPS that action (the actor rests, or the action is deferred until the decision is resolved). The skip is logged as an event (so it is auditable and so the "what moved" list can show it was skipped, not silently dropped). The tick never resolves the pending decision, never advances Brigus's scene, and never applies a forbidden action. If a clock's completion effect would force the decision, the clock still advances but the effect is deferred (logged) until the decision is resolved.

The session-flag rule is unchanged: auto tick still refuses when a session is open. The "already ticked today" rule is SUPERSEDED by the cadence decision below (the engine ticks only on a played turn, 3 ticks, not daily — there is no daily auto-tick to guard against).

## Tick cadence — Bryan DECIDED, 2026-11-21 13:22 EST

Bryan's words: "Tick only when I play, 3 days per turn, like now."

- **Tick only when Bryan plays.** A played turn triggers the ticks. The engine does not tick on its own.
- **3 ticks per played turn.** 3 days per turn, like now (Turn 135 was applied, then ticked 3: tick 9 → 12).
- **No daily auto-tick.** The scheduler does NOT tick daily on its own. The daily auto-tick cron (ironwild-fork-a-daily-tick) stays DISABLED (never ran). The intake poll cron (ironwild-fork-a-proposal-intake) is ENABLED and live — the 15-minute poll that picks up proposals (it is how proposals get picked up, not a tick). Do not conflate the two crons: intake poll ENABLED, daily auto-tick DISABLED.
- **No catch-up for days missed.** If Bryan does not play for days, the engine does not catch up by ticking extra days. The world advances 3 days per played turn, no more.
- **Design questions 3 and 4 are CLOSED.** Question 3 (tick cadence during a pending decision): play-time only, 3 ticks per played turn. Question 4 (no-catch-up): no catch-up, confirmed.
- **The DF guard still applies.** Frozen items protected, skips logged, rumors only from logged events. The cadence changes WHEN the engine ticks, not WHAT the tick may touch.

## How rumors trace to off-screen events only

Rumors in the handshake are generated from logged events only (unchanged rule). Under this shape, off-screen tick events (while a decision is pending) are also logged events, so they are also rumor sources. A rumor must be labeled "Rumor (unverified):" and must trace to a logged event (a tick event or a played-turn event). The DM must not invent a rumor about an off-screen event that was not logged. The handshake's Rumors live list is the only source of rumors for the DM. A skipped action (see Enforcement) is a logged event, but it is not a rumor source (nothing happened; there is nothing to rumor). When the decision is resolved, the DM advances the scene and the off-screen events become history the DM can reference (through the handshake's "what moved" list and Rumors live list, not by inventing new facts).

## When the decision is resolved

The world unfreezes. The DM advances the scene (the pending decision is answered, the scene moves on). Off-screen events that happened while the decision was pending are history: they are in the event log, the "what moved" list, and the Rumors live list. The DM references them through the handshake, never by inventing new facts about them.

No seed change. Fork A stays at v1.6. Freeze intact (the live Turn 136 freeze is unchanged — no Turn 136 state enters any engine world until Bryan resolves it).
