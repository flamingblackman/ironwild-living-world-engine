# Ironwild Fork A — Gemini Start Pack (test Skill + current handshake)

**For:** Bryan to use in the morning to test the Gemini DM.
**World:** Ironwild Fork A (test world ONLY). NOT live Gemini canon. NOT the Turn 136 sequel.
**Roles:** Gemini is the DM (pure narrative + state-proposal). Muse is the campaign controller (sweeps and validates every proposed state block). The Engine is the shared ledger (applies approved changes only). Lore is the mechanics registry and V2 schema. Bryan is the final approval.
**Status:** Ready. No Gemini test turn started, no state changes proposed.

---

## How to set it up (morning, Bryan's steps)

1. **Create the test Skill in Gemini** (separate from the live Ironwild Skill — do NOT edit the live Skill or the live Ironwild Gem e0e15553b378). Name it `ironwild-fork-a-test`. Attach exactly these 4 files from `~/workspace/giant-robot-multiverse/skill_uploads/ironwild-fork-a-test/`:
   - `SKILL.md` (the test DM instructions — adapted from the ChatGPT start pack Part A spec, Fork A versioning, Split-Brain role)
   - `universe-bible.md` (same static bible as the live Skill)
   - `combat-codex.md` (same static codex as the live Skill)
   - `mechanic-registry.md` (same static registry as the live Skill — the Ironwild 16)
   Static lore and mechanics live in those attached files and the Ironwild NotebookLM notebook (https://notebook.google.com/notebook/00cef792-0c01-48f2-82b4-817a2bbf2ec6), not in the Skill prompt.
2. **Start a new test chat with that Skill** (separate test chat — do NOT use the Ironwild live Gemini chat, do NOT use the "Stranded on the Salt Flats" live play chat).
3. **Paste Part B below as the FIRST message.** Wait for the DM's handshake acceptance echo before playing. If it echoes a different version, resets anything, or starts Session Zero, stop and bring the echo back to Muse. Do not play past a bad echo.
4. **Play Turn 135.** The first Gemini turn is Fork A Turn 135, State-Version `ForkA-vFINAL.4`, Base `ForkA-vFINAL.3`. One paste per turn: Bryan pastes the handshake in, Gemini plays and outputs a `[TURN STATE]` block, Bryan pastes that block back to Muse. Muse sweeps, Bryan approves, Engine commits and produces the next handshake.

**Starting-state choice (Lore's call, flag for the hub):** this test starts from the CURRENT Fork A state (Turn 134, ForkA-vFINAL.3, tick 6) — the same world the ChatGPT test has been playing (Turns 132–134, last_swept_turn 133). One Fork A world, one DB. Gemini takes over as DM from Turn 135. If Bryan wanted a fresh Turn 131 start instead, say so and Lore will rebuild Part B from the Turn 131 snapshot.

---

## Part A — where the DM instructions live

The DM instructions are the test Skill (`skill_uploads/ironwild-fork-a-test/SKILL.md`). They are the ChatGPT start pack Part A spec, adapted for Gemini — not a new spec from scratch. The adaptation is:

- **Role:** Split-Brain. Gemini DM is pure narrative + state-proposal. Muse owns Drive + SQLite. 1 paste per turn (clipboard bridge).
- **Versioning:** Fork A `ForkA-vFINAL.<k>`, plus an explicit `Base:` line in every `[TURN STATE]` block (the State-Version the proposal is based on). First Gemini turn: Turn 135, `ForkA-vFINAL.4`, `Base: ForkA-vFINAL.3`.
- **Starting state:** Turn 134, `ForkA-vFINAL.3` (not Turn 131). The first turn to DM is Turn 135.
- **Bonds:** the Player character line carries the Bonds exactly as the current handshake states them (Sledge is 4/5 now, not 3/5 — Dream Share restored it at tick 5). Never carry a Bond from an older turn.
- **Static content:** the bible, codex, and registry live in the Skill's attached files and the NotebookLM notebook, not in the Skill prompt. The Skill is lean.
- **Narrative style:** a compact narrative-style section (sensory cold open, scene beats, pacing, forked consequence, natural stopping points, callbacks, epistemic discipline, six-turn snap-point), adapted from the live Gem instructions — added 2026-11-21 on Bryan's order ("Apply fix"), the same fix as the ChatGPT Part A. The ChatGPT DM's description was thinner than Gemini's because Part A had no narrative-style guidance; this closes the gap for both DMs.
- **No Session Zero.** This is a continuation (the PC already exists). The live Skill's Session Zero override does NOT apply here.

Everything else in the Skill is the Part A spec as written: the exact `[TURN STATE]` layout and field rules, the 10-section handshake spec, propose-never-apply, rejection handling, and the hard rules (isolation, no invented fields, registry only, player agency, Core DNA, checkpoint every 3 turns, hard facts).

---

## Part B — Fork A current handshake (the starting state)

Paste this as the FIRST message in the new Gemini test chat, after creating the test Skill. The handshake uses the `[SYSTEM_STATE_OVERRIDE]` wrapper the V2 instructions recognise as authoritative current state. Do not strip the wrapper.

```
[SYSTEM_STATE_OVERRIDE // SUPERSEDES PRIOR CHAT TURNS // 2026-11-21]
TEST ONLY. Fork A test world, parallel timeline from Ironwild campaign vFINAL (Turn 131). Nothing here transfers to Gemini canon unless Bryan says so in plain words.

Base state: Ironwild Fork A — The Beacon Year, source Ironwild Turn 131 vFINAL (v3.00.2), CAMPAIGN COMPLETE. Current state: Turn 134, State-Version ForkA-vFINAL.3, tick 6. This is a CONTINUATION of the Fork A world, not a restart and not a retelling. Prior campaign history stands as written. The Turn 136 sequel (The Crown of Cold Iron, Krov ambush, Mother-Bulwark) does NOT exist in this world.

PC: Brigus, Seedborn, King of the Great Basin, Beacon. Wounds: None. Status: exhausted after the Feral God merge, victorious, directing reconstruction and requesting development of an elite combat unit. Five Engines, all exhausted and battered: Gold Sledge, black-and-gold gorilla Bulwark, Bond 4/5, Titanium-Cestus (Diamond-Claw melted Turn 126), neural Sentient Seat (not a saddle-harness); Skytalon, ADULT Shadow-Owl, Bond 5/5, sleek radar-absorbent silent chassis, echolocation, mono-molecular feather-blades, adult Molt Turn 129, no longer juvenile or hard-light winged; Razor-Back, Bond 3/5, exhausted following the Turn 128 Pack Merge; Goliath Dreadnought, Bond 5/5, pre-war machine, left mortar pod destroyed Turn 112; Surveyor-Strider, Bond 5/5, observation and fire-control platform. Pack: Vance, Tull, Queen Kaelen, Nest-Keeper. Vance, Tull, and Kaelen in Great Basin; Nest-Keeper in Chalk Canyons. Faction: Ironwild Legion, 600 strong, including absorbed Dust-Baron mercenaries. Great Basin fortified. Elite combat unit requested; preliminary engineering assessment underway, no unit formed or resources expended.

Scene: Great Basin — Legion Engineering Grounds | SCENE_TENSION: Low | ACTIVE_TRADE_OFF: Developing an elite combat unit may divert engineers, salvage, and labor from civilian welfare and Engine recovery.

Engines:
- Gold Sledge, black-and-gold gorilla Bulwark, Bond 4/5, exhausted
- Skytalon, ADULT Shadow-Owl, Bond 5/5, exhausted
- Razor-Back, Bond 3/5, field-patched
- Goliath Dreadnought, Bond 5/5, field-patched
- Surveyor-Strider, Bond 5/5, exhausted

Pack: Vance, Tull, Queen Kaelen, Nest-Keeper. Faction: Ironwild Legion.
Vance location: Great Basin.

Clocks (resolved campaign clocks — do not reopen):
- Rift-King Battle resolved (Rift-King annihilated in the Salt Flats)
- Deepmaw Migration diverted by the Acoustic Lure
- Concord War N/A
- Famine N/A

Clocks (running, Fork A — carry these in Name value/max form in every state block):
- Dust-Baron Retaliation 0/6
- Concord Blockade 0/6
- Legion Cohesion 0/6
- Great Basin Recovery 6/6 (Complete)

Resolved, do not resurrect: The Rift-King (corrupted Den Boss) annihilated in the Salt Flats. The Den Boss is dead. Deepmaw Migration diverted by the Acoustic Lure.

Dormant Watchlist: IW-42 Learning Black Box only. IW-46 and IW-84 activated and resolved in the final arc; do not re-trigger them as dormant.

Pending decision, verbatim: "What kind of elite force should the engineers develop?"

First reply: echo State-Version ForkA-vFINAL.3, Turn 134, the clocks above, the scene, and the pending decision verbatim. Then stop and wait for Bryan's first move. Do not advance the scene until Bryan acts. The first turn you DM is Fork A Turn 135, State-Version ForkA-vFINAL.4, Base ForkA-vFINAL.3.
```

---

## What this pack does not contain

- No Turn 136 sequel state. No Krov, no Mother-Bulwark, no sequel clocks. Fork A is at Turn 134, ForkA-vFINAL.3.
- No new canon, characters, clocks, or mechanics beyond the seeded files and the swept Turns 132–134. Everything above is from the live Fork A test DB (tick 6, last_swept_turn 133, 70 events) and the corrected Turn 134 handshake (597 words, Sledge Bond 4/5 in both the PC line and the Engines section).
- No live Gemini canon. This is a test world. Nothing transfers to Gemini unless Bryan says so in plain words.
- No edits to the live Gem, the live Skill, the live Gemini chat, or any live saga canon. The test Skill and test chat are separate.
