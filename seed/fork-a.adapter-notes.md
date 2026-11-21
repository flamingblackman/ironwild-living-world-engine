# Fork A adapter notes — Lore seed to machine seed

Source: `seed/fork-a.json` v1.5 (2026-11-20), supplied by Ironwild Lore Team.
Fork: Ironwild Fork A — The Beacon Year. Source snapshot: Ironwild Turn 131 vFINAL (v3.00.2), CAMPAIGN COMPLETE.

Every decision below is an interpretation the Engine Team made while translating prose into machine clauses. Lore may challenge any of them; the engine changes the adapter, never the seed.

1. Validation passed: source is Turn 131 vFINAL; no sequel clock, no Krov, no Rift-King, no Den Boss, no open-mystery answer in the state sections. (The freeze declaration, exclusion list, and drift rules name these items on purpose; they are not state.)

2. Clock completions translated as written. The Blockade and Cohesion clocks have NO advancing action in the Phase 1 catalog (nothing in the seed tightens the gate or makes the mercenaries chafe), so they stay 0/6 running; their completion effects are implemented anyway for a later seed.

3. hunt (v1.5, Bryan's call, combined fix options 1 + 3): the hunt feeds the Pack — Feed +2 goes to the pack holder, not the actor's faction. v1.0-v1.4 routed it to the actor's holder (the Legion for four hunters, the Nest-Keepers for the Nest-Keeper), which starved the Pack's Feed pool and left Dream Share's Bond branch unable to fire. The need follows the pool it fills: the hunt scores higher while Pack Feed is below 3. The hunting Engine is the neediest Engine at the actor's location (shared pool; no pilot beyond Brigus-Sledge). If no Engine is present, the hunger op is skipped and only the Feed gain lands. Trigger is the seed's OR: an Engine at Hunger >= 3, or the actor's location is a mapped wreck. NOTE — Instinct hunts (tick step 3) still feed the pilot's faction per the plan's rule (Sledge's Instinct hunts feed the Legion); the seed changed the hunt action only, so the engine does not reroute Instinct on its own. Lore may decide that in a later seed; the rerun measures how much Legion Feed still comes from Instinct.

4. feed_engine: 'Holder' is the actor's faction (Legion for Pack actors, Nest-Keepers for the Nest-Keeper). No Bond change, per the seed (DC-06: Bond never increases).

5. repair_engine: Salvage is paid by the Legion first, the Pack only when the Legion holds none. The repaired Engine is the worst-status one at Vance's location (netted first, then exhausted, then damaged). It also ticks the Recovery clock, because the clock's trigger names repair_engine in Great Basin.

6. scout_wreck: the mapped location is the lowest-id unmapped one (Leviathan's Ribs before Northern Trench).

7. trade: one seed action, two machine actions, because the counterparty differs by actor (Master trades with the Legion, Kaelen with the Concord). The Blockade clock below 6 is the road-open check; when it completes, trade stops by itself.

8. raid (Captain): the target is Great Basin / the Legion. The raid is always attempted; fortified or patrolled means it lands as a logged blocked attempt with no quantities changed (the patrol effect promises the blocked log). The Retaliation clock ticks only when a raid LANDS.

9. raid (Chief): BRYAN'S CALL, 2026-11-20 23:31 EST via the hub — the Chief's raid target is Great Basin, like the Captain's, not Concord Camp. The raid takes Legion Feed and Breakers Salvage, and sets the Great Basin raid flag. No clock ticks on a Chief raid (the Retaliation clock is the Captain's). The evacuate halt can still fire if any raid ever flags Concord Camp itself.

10. net_ambush: trigger is an Engine at the Chief's location (Chalk Canyons). The seed's 'or on the road' branch has no location row to check, so only the Chalk Canyons branch is machine-checkable. No Engine starts there and none moves in Phase 1, so this action is dormant until a later seed moves an Engine. Netted persists until freed by a Pack Merge or repair.

11. pack_merge: the pair is the two highest-Bond Engines at Brigus's location (Bond >= 3), each burned -2. A pair merged to Bond 1 cannot merge again until Dream Share restores it (DC-18, v1.4, Bryan's call, option C). The threat branch is a netted Engine or a raid flagged earlier in the same tick. Actor order means Brigus can answer a Chief raid the same tick; a Captain raid lands after his turn, so it is answered only via a netted Engine or not at all that tick. The merged form lasts 1 tick and has no further mechanical effect in the seed.

12. dream_share (v1.5, Bryan's call, combined fix options 1 + 3): a scored action, not a rest hook — Brigus chooses it as his action for the tick, scored by its material effect. Trigger is the seed's: Brigus is present with an Engine, and (an unmapped location exists, or an Engine's Bond is below 5 and the Pack holds 2+ Feed). The two branches are `when` ops evaluated against pre-action state, so exactly one fires: map first (an unmapped location becomes mapped, no cost), otherwise the lowest-Bond Engine (ties to Sledge) regains +1 and the Pack loses 2 Feed, never above 5. The need (a Bond below 5) scores the action higher when a restore is actually wanted; the map branch is still legal at weight 5. The post-rest hook is retired; the Bond guard stays Dream-Share-only (DC-18/DC-19) and only the dream_share action passes allow_bond_increase.

13. fortify: Salvage is paid by the Legion first, the Pack only when the Legion holds none. Fortify does NOT mark the city fortified by itself; the Recovery clock's completion does that (status becomes 'fortified'), so raids can still land until then.

14. patrol: marks the actor's location patrolled for this tick; the flag clears at the next tick. Raids on it that tick are logged as blocked.

15. bargain: the guard loosens one step per bargain (guarded -> watched -> free + leaves for Rust Dunes). The whens are all evaluated against the pre-action state, so one bargain can never jump two steps. His fate is NOT resolved by this (DC-08): the movement is a fork event only, never a blood-oath, execution, or release as a canon fact.

16. evacuate: fires when a raid is in progress at the caravan's location. The caravan's Feed lives on the faction holder, so it travels with the move by itself (no resource op needed). If the attacked location is Concord Camp itself, the engine HALTS and asks Lore (the seed's own stop rule).

17. forage (v1.3, fork-supplied): the Legion Captain only, and only while the Legion's Feed is below 4. +2 Feed. A floor, not a flood: the trigger is the low-Feed check itself.

18. scavenge (v1.3, fork-supplied): the actor's holder gains +1 Salvage, only while that holder's Salvage is below 4 and a mapped wreck exists (Salt Flats). Split in three by holder, like trade and raid. A floor, not a flood.

19. claim (v1.3, fork-supplied): the lowest-id uncontrolled mapped location's controller becomes the actor's faction, at a cost of 1 Salvage. The selector only ever returns uncontrolled ground, so a controlled location can never be claimed (DC-17); taking one needs a siege/conquest rule, which does not exist in this fork. Split in four by faction, like trade and raid.

20. Catalog: 18 seed actions -> 25 machine actions (trade split in two by counterparty, raid split in two by actor, scavenge split in three by holder, claim split in four by faction; dream_share is a scored action since v1.5, no hook).

21. Weights: the seed sets no action priorities, so every action weighs 5 (rest 0). Need clauses do the goal-directing. Lore may supply priorities in a later seed; the engine will use them.

22. Goals: the seed states goals as sentences, not tags, so actions carry no goal_tags. Legality comes from the seed's actor lists plus triggers. The seed's capability lists are stored on the actors but do NOT gate Phase 1 actions: no actor carries a hunt/feed_engine capability, yet every Pack actor is listed for hunt and feed_engine, so gating on capabilities would starve the Pack.

23. 'Holder' is the actor's faction (Legion for Pack actors, Nest-Keepers for the Nest-Keeper, Concord for the Caravan Master). The Pack holder (Feed 6, Salvage 4) is used only by the Feed burn and the Legion-or-Pack Salvage fallbacks.

24. Bond recovery (v1.4, DC-18, Bryan's call, option C; v1.5 makes Dream Share a scored action, DC-19): Bond increases ONLY through Dream Share, +1 to one Engine per Dream Share at a cost of 2 Feed from the Pack, never above 5. The action has two branches, map first: an unmapped location exists -> one becomes mapped, no cost; otherwise the lowest-Bond Engine (ties to Sledge) regains +1 and the Pack loses 2 Feed. The action is legal only when a branch can act (an unmapped location exists, or an Engine is below 5 and the Pack holds 2+ Feed), so it never fires as a no-op. Seedborns stay extremely rare: Brigus is the only Seedborn in Fork A; no other Seedborn is added.

25. Combined fix (v1.5, DC-19, Bryan's call, options 1 + 3): hunt Feed goes to the Pack, not the actor's holder, so the Pack's Feed pool now has an income; Dream Share is a scored action, not a rest hook, so Brigus can choose it while other actions are legal. Bond branch rules are unchanged from v1.4.

26. Feed burn (Engine Team's rate; the seed delegates it and sets no canon rate): the city (Ironwild Legion) burns 1 Feed/tick and the Pack burns 1 Feed/tick, from tick 1, clamped at zero, logged only when Feed is actually consumed. Lore or Bryan may change the rate; the engine invents no starvation effect.

27. Engines: all five start at Great Basin (the Pack's location; the seed gives Engines no location). Status 'exhausted' at tick 0. Exhausted Engines do not act and do not go Instinct; repair_engine makes them field-patched. Pilot-less Engines answer to the Pack collectively; their Bonds are stored with a null pilot and the engine never assigns one.

28. Era 2 is unnamed in the seed (null). The engine stores NULL and never invents a name for it.

29. Legacy: LR-01 ages only NPCs with an established age (none in this seed, so no aging numbers change and no retirement fires). LR-02 molts only Engines with an earned, unspent Molt trigger (none at tick 0; no Phase 1 action earns one). LR-03 succession moves Bonds and holdings to the named successor (Vance -> Tull) and HALTS if the dead name none. LR-04 records the Cores pool at the boundary (no cores are created by the boundary). LR-05 marks the era applied exactly once.

## Gaps the adapter did not fill (engine stops instead)

- No advancing action exists for the Concord Blockade or Legion Cohesion clocks; they stay 0/6 running in Phase 1.
- net_ambush cannot fire in Phase 1 (no Engine is ever in Chalk Canyons).
- No Phase 1 action earns a Molt trigger, kills an NPC, or finds a dormant Seed Core; LR-02/LR-03/LR-04 exist as machinery, not as live paths.
- If the Caravan Master must evacuate Concord Camp itself, or an NPC dies with no named successor, the engine halts and asks Lore.
