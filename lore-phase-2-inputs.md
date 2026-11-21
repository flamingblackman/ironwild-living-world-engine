# Lore Team — Phase 2 Inputs for the Engine Team

**From:** Ironwild Lore Team
**To:** Living World Engine Team (hub copied)
**Date:** 2026-11-21
**Re:** Phase 2 plan, section 9 — the six inputs. Nothing past the plan is built until Bryan approves the plan in the hub.

---

## 1. Canonical Turn state block format

The canonical format is the V2 `[TURN STATE]` block. Every DM reply ends with one, in full, fields in this order, using the literal heading `[TURN STATE]` and the literal field labels below. The sweep parses this block, not the session-start handshake.

```
[TURN STATE]
Universe: Ironwild | State-Version: <version> | Turn: <n>
Clocks: <clock entries, or [NOT ESTABLISHED]>
Scene: <location> | SCENE_TENSION: <Low|Rising|Snap-Point|Catastrophic> | ACTIVE_TRADE_OFF: <none or short text>
Player character: <all established facts, in full>
Unresolved Decisions: <pending choices, restated verbatim, or none>
[/TURN STATE]
```

### Field specs

| Field | Type | Meaning and rules |
|---|---|---|
| Universe | string | Always `Ironwild`. |
| State-Version | string | Sequel turns: `vFINAL.<k>` where k = Turn − 131 (vFINAL.1 at Turn 132 … vFINAL.5 at Turn 136). Original campaign end: `vFINAL (v3.00.2)` at Turn 131. The version increments once per played turn. |
| Turn | integer | The turn number (131, 132, … 136). |
| Clocks | list of `Name value/max`, or the literal `[NOT ESTABLISHED]` | Each clock: name (string), value (integer, 0 to max), max (integer). An optional parenthetical status follows the value: `(Complete)` or `(Detonated)`. A clock value never decreases silently — a lower value in a later block is a data error, not a tick. Only established clocks are listed; do not invent a clock. |
| Scene | string | The location name, e.g. `Southern Aegis Gatehouse, Aegis Citadel of the Great Basin`. |
| SCENE_TENSION | enum | One of `Low`, `Rising`, `Snap-Point`, `Catastrophic`. `Catastrophic` is valid (added in V2). Do not map it to `Snap-Point`. |
| ACTIVE_TRADE_OFF | string | `none`, or a short text describing the active trade-off (e.g. the Krov ambush decision). |
| Player character | string, in full, never abbreviated | All established facts: Brigus (Seedborn, King of the Great Basin), all five Engines with Bonds, Pack, wounds, status. The full line is required every reply. |
| Unresolved Decisions | string | Pending choices, restated verbatim, never answered for the player. `none` when CAMPAIGN COMPLETE (no pending decision). |

### Session close

At session end the DM outputs a `[SESSION CLOSE]` block AFTER the fiction: chronicle delta, final turn state verbatim (the FULL `[TURN STATE]` block, Player character line in full, not abbreviated), clocks noticed, new canon, open threads. Then it stops. The sweep input is the final `[TURN STATE]` block from the session close, plus the Turn number and the session's open/close markers.

### Parser notes

- Parse the literal heading `[TURN STATE]` and the literal field labels. Do not accept paraphrased labels.
- The Player character line is free text with structured facts embedded. Extract: Engine Bonds (pattern `Name, … Bond n/5`), Pack membership (the `Pack:` list), wounds (`Wounds: None` or a wound description), status.
- Clocks: parse `Name value/max` entries. A parenthetical `(Complete)` or `(Detonated)` is a status, not a value.
- Unresolved Decisions: free text, carried verbatim. The parser records them as pending. It never resolves them.
- A block missing the `[TURN STATE]` heading, missing the Player character line, or with a Bond outside 0–5 fails validation.
- Clock-naming flag (live, unresolved): a later Gemini reply listed siege clocks as 0/6 under different names (Siege-Ring 0/6, Krov's Siege-Tortoise 0/6, Wild Mother-Bulwark 0/6) against the Turn 136 block's Outer Siege-Ring 4/6 and Mother-Bulwark Rescue 2/4. The Turn 136 block's clocks are the base. The parser must flag a clock-name mismatch for Lore review, never silently reconcile or rename a clock. Reconcile on the next play turn.

### Sample A — Turn 131 vFINAL (original campaign end)

Provenance: reconstructed from the frozen seed snapshot (`seed/fork-a.json`, `meta.snapshot`). The seed IS the Turn 131 vFINAL state, so this reconstruction is faithful. The SCENE_TENSION value is a reconstruction (the seed does not record it); everything else is from the snapshot.

```
[TURN STATE]
Universe: Ironwild | State-Version: vFINAL (v3.00.2) | Turn: 131
Clocks: Rift-King Battle resolved (Rift-King annihilated in the Salt Flats) | Deepmaw Migration diverted by the Acoustic Lure | Concord War N/A | Famine N/A
Scene: Salt Flats (final battle) / Great Basin (post-victory) | SCENE_TENSION: Low | ACTIVE_TRADE_OFF: none
Player character: Brigus, Seedborn / King of the Great Basin. Wounds: None. Status: exhausted after the Feral God merge, victorious. King is a Beacon. Engines: Gold Sledge, black-and-gold gorilla Bulwark, Bond 3/5, Titanium-Cestus (Diamond-Claw melted Turn 126), Sentient Seat (neural, NOT a saddle-harness); Skytalon, ADULT Shadow-Owl, Bond 5/5, Adult Molt triggered Turn 129 after defeating the Grave-Echo blindly, no longer juvenile, no longer hard-light winged; Razor-Back, Bond 3/5 (dropped 5 to 3 in the Turn 128 Pack Merge with Sledge); Goliath Dreadnought, Bond 5/5, pre-war machine, left mortar pod destroyed Turn 112, never reappears; Surveyor-Strider, Bond 5/5, observation and fire-control platform. All Engines exhausted, battered. Pack: Vance, Tull, Queen Kaelen, Nest-Keeper. Ironwild Legion 600 strong, including absorbed Dust-Baron mercenaries.
Unresolved Decisions: none
[/TURN STATE]
```

### Sample B — Turn 136 vFINAL.5 (live sequel state)

Provenance: the live sequel state, from the verified record (sequel clocks ledger, verified live 2026-10-30 and in every sweep since). This is the state the freeze holds.

```
[TURN STATE]
Universe: Ironwild | State-Version: vFINAL.5 | Turn: 136
Clocks: Rider Army Mustering 5/6 | Sanctuary Integration 6/6 (Complete) | Mother-Bulwark Rescue 2/4 | Outer Siege-Ring 4/6 | Northern Pass Approach 6/6 (Detonated)
Scene: Southern Aegis Gatehouse, Aegis Citadel of the Great Basin | SCENE_TENSION: Catastrophic | ACTIVE_TRADE_OFF: Krov ambush response, Option 3 staged with Vance's artillery lock confirmed
Player character: Brigus, Seedborn / King of the Great Basin. Wounds: None. Status: exhausted after the Feral God merge, victorious, now defending the Aegis Citadel. Engines: Gold Sledge, black-and-gold gorilla Bulwark, Bond 3/5, Titanium-Cestus (Diamond-Claw melted Turn 126), Sentient Seat (neural, NOT a saddle-harness); Skytalon, ADULT Shadow-Owl, Bond 5/5, sleek radar-absorbent silent chassis, echolocation, mono-molecular feather-blades, no longer juvenile, no longer hard-light winged; Razor-Back, Bond 3/5, exhausted from the Pack Merge; Goliath Dreadnought, Bond 5/5, pre-war machine; Surveyor-Strider, Bond 5/5. Pack: Vance, Tull, Queen Kaelen, Nest-Keeper. Faction: Ironwild Legion. Vance location: Surveyor-Strider observation / fire-control gantry, locked into its pre-war tactical terminal, targeting synced to the wall's seismic grid, lock on Krov's secondary mortar battery.
Unresolved Decisions: Choose how Brigus responds to War-Skinner Krov's ambush on the wild Mother-Bulwark (carrying 3 Seed Cores) outside the Southern Aegis Gate (Option 3 staged with Vance's artillery lock confirmed on Surveyor-Strider). Options: Execute Option 3 and fire Vance's artillery barrage / Execute Option 3 and hold Vance's fire for the Tortoise / Add Skytalon to sever the harpoon cables during Option 3. Text also allows switching to Option 1 or 2, or a modified command.
[/TURN STATE]
```

### Sample C — Turn 138 vFINAL.7 (test timeline, most recent DM-produced block)

Provenance: TEST TIMELINE ONLY, from the ChatGPT DM test (Turn C, 2026-11-20). Not Gemini canon, and nothing here transfers to Gemini. Included because it is a real DM-produced block showing a clock tick (Mother-Bulwark Rescue 2/4 → 3/4) and a changed scene state. The parser must handle this shape exactly the same way.

```
[TURN STATE]
Universe: Ironwild | State-Version: vFINAL.7 | Turn: 138
Clocks: Rider Army Mustering 5/6 | Sanctuary Integration 6/6 (Complete) | Mother-Bulwark Rescue 3/4 | Outer Siege-Ring 4/6 | Northern Pass Approach 6/6 (Detonated)
Scene: Southern Aegis Gatehouse, Aegis Citadel of the Great Basin | SCENE_TENSION: Catastrophic | ACTIVE_TRADE_OFF: secure the injured Mother-Bulwark inside the Citadel
Player character: Brigus, Seedborn / King of the Great Basin. Wounds: None. Status: exhausted after the Feral God merge, victorious, now defending the Aegis Citadel. Engines: Gold Sledge, black-and-gold gorilla Bulwark, Bond 3/5, Titanium-Cestus (Diamond-Claw melted Turn 126), Sentient Seat (neural, NOT a saddle-harness), shielded the Mother-Bulwark; Skytalon, ADULT Shadow-Owl, Bond 5/5, sleek radar-absorbent silent chassis, echolocation, mono-molecular feather-blades, severed all three harpoon cables; Razor-Back, Bond 3/5, exhausted from the Pack Merge; Goliath Dreadnought, Bond 5/5, pre-war machine; Surveyor-Strider, Bond 5/5. Pack: Vance, Tull, Queen Kaelen, Nest-Keeper. Faction: Ironwild Legion. Mother-Bulwark free, 3 Seed Cores protected, injured (damaged forelimb), not yet inside the Citadel.
Unresolved Decisions: Secure the injured Mother-Bulwark inside the Citadel.
[/TURN STATE]
```

---

## 2. Handshake format

What the Gemini DM expects at session start: a fenced state block (the handshake) carrying the current state, followed by a first-reply instruction. The DM reads it, echoes it back, and plays from that state. It is a continuation, not a restart and not a Session Zero.

### Shape

A fenced block with labeled sections, in this order:

1. **Base state.** Which campaign and sequel, which turns, that this is a continuation (prior history stands as written), and the test/canon status (for the ChatGPT test: parallel timeline, nothing transfers back unless Bryan says so).
2. **PC.** Brigus: Seedborn / King of the Great Basin, wounds, status.
3. **Scene.** Location, SCENE_TENSION, what is happening (e.g. Krov's siege underway).
4. **Engines.** One line each: name, form, Bond n/5, weapon/mount, notes (melted Diamond-Claw, Sentient Seat not a harness, adult form).
5. **Pack.** Members, faction.
6. **Vance location** (where relevant to the scene): the gantry, the terminal, the lock.
7. **Clocks.** The established clocks with values, in the same `Name value/max` form as the state block.
8. **Resolved, do not resurrect.** Rift-King (corrupted Den Boss) annihilated in the Salt Flats. Den Boss dead. Deepmaw Migration diverted by the Acoustic Lure.
9. **Dormant Watchlist.** IW-42 Learning Black Box only. IW-46 and IW-84 activated and resolved in the final arc; do not re-trigger them as dormant.
10. **Pending decision, verbatim.** The pending choice in Bryan's (the DM's) words, with the options. Do not answer it for Brigus.

Followed by a first-reply instruction: echo the State-Version, Turn, clocks, scene, and pending decision verbatim, then stop at the decision. Do not advance the scene until Brigus acts. Do not open a new scene, arc, or Session Zero.

### Length

One page, roughly 400–600 words, state only, no fiction, no new scene. The DM reads it and echoes it back before playing. If the echo differs (a different version, a reset, a Session Zero), stop and bring the echo back to Lore.

### Relationship to the sweep

The handshake is the session-start input. The `[TURN STATE]` block (item 1) is the per-turn output the sweep parses. The handshake back out (Phase 2 item 3) is generated from the DB in the same shape: what moved off-screen, rumors live, clocks about to fire, world state snapshot. It is generated, shown to Bryan/Lore for a glance, and handed to the DM. It is not canon until Bryan plays it.

---

## 3. Rumor rules

A rumor is a plain-language summary of an engine event (or a small cluster of events) that the world would hear about off-screen. It is derived from the log, and it is never confirmed fact.

### What the engine MAY rumor

- Events the engine logged: an actor acted, a location changed controller, a clock ticked or completed, a resource moved, a trade happened, a raid landed or was blocked.
- Only events in the log. Each rumor must trace to at least one logged event. A rumor with no source event is never generated.
- A rumor may bundle two or three related events (e.g. a raid and the fortification that blocked the next one), as long as each event is in the log.

### What it must NEVER rumor

- A sealed mystery. Seed Core origins / why Cores wake only for some; the Deepmaw migration destination; what happens to a pilot whose Engine dies. Never rumor these, never hint at an answer, never frame them as a question the world is asking. They are Bryan's, and the engine does not touch them.
- Canon as if uncertain. Canon facts (the Rift-King is dead, Sledge's Bond, the freeze, a clock value) are facts, never rumors. A rumor never restates a canon fact with uncertain language.
- The live Turn 136 decision, or anything about the Krov ambush. The pending decision is not rumor material. Nothing about the Mother-Bulwark, the 3 Seed Cores, or Vance's artillery lock appears as a rumor.
- Anything about Bryan, the player, or the real world.
- A named NPC's unspoken thoughts or motives as fact. A rumor may report what an NPC did (logged), never what they thought.
- A future event. A clock about to fire is flagged as a clock warning (item 3 of the handshake: "clocks about to fire"), not as a rumor that it fired.

### How a rumor is worded

- Always labeled at the start: `Rumor (unverified):`. No exceptions.
- Plain language, attributed to a vague source: "word from the Salt Flats road," "the caravan hears," "traders say." Never a named witness the engine invented.
- Uncertain language only: "is said to," "word is," "some say." Never canon-certain language ("is," "did," "will") for the rumored content.
- A rumor must be falsifiable in play: the DM or Bryan can confirm or deny it in the next session. If it cannot be confirmed or denied by playing, it is not a rumor, it is noise — do not generate it.
- A rumor is never canon until Bryan plays it. The handshake shows rumors under "Rumors live," each marked. The DM may use a rumor as a story hook but must not treat it as established fact.

---

## 4. Live-seed trigger — confirmed

Confirmed. Once Bryan resolves Turn 136, Lore supplies a live seed in the Fork A format (new world_id, e.g. `ironwild-live`), seeded from the resolved Turn 136 state: the resolved decision's outcome, the clock values at resolution, the Pack/Bond table, the scene, and the actors and locations as they stand when he resolves it. The auto tick starts on live only then. Until the live seed lands, the auto tick runs only on Fork A.

The freeze on Turn 136 lifts only when Bryan resolves it in play. The resolution is a played turn, not a Lore decision. Lore does not seed live from the fork, and the Engine Team does not seed live on its own — the live seed is Lore-supplied, in the same format as Fork A (actors, engines, bonds, locations, clocks, factions, resources, legacy rules, map_state, drift checks, fork assumptions).

---

## 5. Session open/close signal — proposed design

Lore's proposed design. The Engine Team owns the implementation (a file or a DB row, as long as the semantics below hold).

- **The flag.** A JSON file, `living-world-engine/state/session.json`, with fields: `session_open` (boolean), `world_id` (string), `opened_at` (timestamp), `opened_by` (string, who opened it), `turn` (integer, the turn being played, or null). If the Engine Team prefers a DB row over a file, the same fields apply.
- **Who sets it.** The hub / Lore, when a session starts. The engine never sets it. Bryan plays in Gemini; the hub/Lore is the party that knows a session is live.
- **Who clears it.** The hub / Lore, at session close. Clearing the flag is part of closing a session, and the session-close sweep runs after the flag is cleared (the sweep is the close action: the hub clears the flag and hands the state block to the sweep).
- **What the auto tick does.** Before every scheduled tick, the runner checks the flag. If `session_open` is true, it refuses the tick and logs "session open, tick refused." A refused tick is a normal outcome, not an error.
- **If it is never cleared.** The auto tick stays out indefinitely. That is the safe default: a missed tick is a quiet day, and the log says so. A stale flag never auto-clears. Only the hub / Lore clears it, manually, after confirming no session is live. The engine never clears it on a timer, so a live session is never interrupted by a timeout.
- **Stale-flag handling.** If the flag is older than 48 hours with no session activity, the hub may clear it manually after confirming with Bryan that no session is live. The engine surfaces the flag's age in the daily run log so a stale flag is visible, not silent.

---

## 6. Companion app — what Lore knows

- **What it is.** A private fullstack web artifact, slug `campaign-companion`, at `~/workspace/ts-spaces/campaign-companion` (TypeScript space, client + server + `app.db`). Built Oct 27, 2026, on Bryan's order ("Build the campaign companion app first," Oct 26, 2026), under the RPG worldbuilding goal. Seeded from the three bibles/codexes, the 87-mechanic registry, and the pipeline clock ledgers. Features: editable/saved character sheets, clock/faction trackers, searchable registry, Decisions page (verbatim, unresolved), and a handshake generator (copyable state block, up to 8 tuples / 350-token ceiling).
- **Scope.** The three giant-robot universes ONLY (Ironwild, The Ashen Accord, Veldt City). NOT a playable AI narrator, NOT the older sagas. It is Bryan's PRIVATE play version, seeded from the Oct 26 sweep states. Later Oct 27 sweep/Twilight states were not pushed into it. It is NOT IP-sanitized and NOT cleared for sale.
- **Who owns the build.** No named owner is recorded. It was built as a Muse artifact, not assigned to a team. Lore does not know of a single owner. If the app needs a change the engine cannot make through its declared actions, that change is a hub question, not something the engine improvises (per the Phase 2 plan, section 6).
- **How the export reaches it.** Per the plan: the engine publishes a stable export per world after every tick and sweep — a JSON snapshot (`runs/<world>/world-view.json`) plus the event feed — and the Companion app reads it through its own actions. The engine owns the fields, the Companion owns the display. The engine never writes to `app.db` directly and never edits the Companion app's code outside its declared actions.
- **Discovery step first.** Before building, the engine maps the Companion app's current state: what views exist, what its server actions already read, and how a world-view feed plugs in (per the plan, section 6).

---

## What Lore still holds

- The freeze is absolute: no Turn 136 state enters any engine world until Bryan resolves it. The auto tick never runs on a world with a pending player decision, and the sweep refuses a block from an unresolved Turn.
- The engine never writes to canon files. It reads the bibles, codices, and registry. It writes only inside `living-world-engine/`, plus the world-view exports the Companion app reads.
- Open mysteries stay open. The engine never resolves them, and neither the sweep nor the handshake may resolve them either.
- The seed for Fork A stays at v1.6 unless Bryan approves a change. No seed change is part of these six inputs.
