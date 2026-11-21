"""Era boundaries and legacy rules (LR-01..LR-05 in the Lore seed).

An era is era_length ticks (365 = 1 year, per the approved plan). When a tick
crosses an era boundary, legacy rules fire exactly once:
  - LR-01 Aging: every NPC with an established age ages +1. NPCs with no
    age in canon (age NULL) do not age on paper. Retirement fires only when
    the seed sets a retire_age; the Lore seed sets none, so no retirement
    or death fires from aging in Phase 1.
  - LR-02 Molt on earned triggers: only Engines with an earned, unspent
    Molt trigger (molt_trigger = 1) Molt at the boundary: status becomes
    molted, Hunger resets to 0, and the trigger is spent (set to 0).
    No Molt trigger is earned at tick 0, and no Phase 1 action earns one,
    so no boundary Molt fires in Phase 1 unless a later seed earns one.
  - LR-03 Succession: if an NPC died during the era, their Bonds and
    holdings pass to their named successor. If the dead NPC names no
    successor, the engine STOPS (EngineHalt) and asks Lore instead of
    improvising. No Phase 1 action kills an NPC, so this never fires in
    Phase 1, but the machinery exists and is tested.
  - LR-04 Dormant Cores confirmed: the boundary event records the current
    Cores pool per holder (cores found during the era are confirmed in it).
    Cores enter the pool only via actions; the boundary itself creates none.
  - LR-05 Era applied once: the closing era row is marked applied exactly
    once; a second application in the same era is a failure.
The engine never names an era: the next era's name comes from the seed,
and stays NULL when Lore has not named it.
"""

from . import events


class EngineHalt(Exception):
    """The engine stops and asks Lore instead of improvising."""


def apply_legacy(conn, tick, legacy):
    """Apply legacy rules for the era ending at `tick`. Returns effects."""
    era_length = legacy.get("era_length", 365)
    retire_age = legacy.get("retire_age")  # None = no retirement (Lore seed)
    closing_number = tick // era_length  # 1 at tick 365
    closing_name = _era_name(legacy, closing_number)

    effects = [{"era_closed": closing_name}]

    # LR-02: Molts on earned triggers only.
    rows = conn.execute(
        "SELECT id FROM engines WHERE status != 'dead' "
        "AND molt_trigger = 1 ORDER BY id").fetchall()
    for row in rows:
        conn.execute(
            "UPDATE engines SET status = 'molted', hunger = 0, "
            "molt_trigger = 0 WHERE id = ?", (row["id"],))
        effects.append({"op": "status_set", "entity_kind": "engine",
                        "id": row["id"], "status": "molted",
                        "reason": "legacy molt (LR-02)"})

    # LR-01: Aging (+1 for NPCs with an established age) and retirement.
    for npc in conn.execute(
            "SELECT id, age FROM npcs WHERE status LIKE 'active%' "
            "ORDER BY id").fetchall():
        if npc["age"] is None:
            continue
        new_age = npc["age"] + 1
        conn.execute("UPDATE npcs SET age = ? WHERE id = ?",
                     (new_age, npc["id"]))
        if retire_age is not None and new_age >= retire_age:
            conn.execute(
                "UPDATE npcs SET status = 'retired' WHERE id = ?",
                (npc["id"],))
            effects.append({"op": "status_set", "entity_kind": "npc",
                            "id": npc["id"], "status": "retired",
                            "reason": "legacy retirement (LR-01)"})

    # LR-03: Succession for NPCs who died during the era.
    for npc in conn.execute(
            "SELECT id, successor FROM npcs WHERE status = 'dead' "
            "ORDER BY id").fetchall():
        successor = npc["successor"]
        if not successor:
            raise EngineHalt(
                f"LR-03: NPC {npc['id']} died with no named successor. "
                "The engine stops and asks Lore; it will not improvise "
                "an heir.")
        conn.execute(
            "UPDATE bonds SET pilot_id = ? WHERE pilot_id = ?",
            (successor, npc["id"]))
        conn.execute(
            "UPDATE resources SET holder_id = ? "
            "WHERE holder_id = ? AND holder_kind = 'npc'",
            (successor, npc["id"]))
        effects.append({"op": "succession", "from": npc["id"],
                        "to": successor, "reason": "LR-03"})

    # LR-04: Dormant Cores confirmed in their holders' pools.
    cores = {}
    for row in conn.execute(
            "SELECT holder_id, qty FROM resources WHERE resource = 'Cores' "
            "AND qty > 0 ORDER BY holder_id").fetchall():
        cores[row["holder_id"]] = row["qty"]
    effects.append({"cores_confirmed": cores})

    # LR-05: close the era that just ended, open the next one, exactly once.
    conn.execute(
        "UPDATE eras SET end_tick = ?, legacy_applied = 1 "
        "WHERE end_tick IS NULL",
        (tick,),
    )
    next_number = closing_number + 1
    conn.execute(
        "INSERT INTO eras (name, start_tick, end_tick, legacy_applied) "
        "VALUES (?, ?, NULL, 0)",
        (_era_name(legacy, next_number), tick + 1),
    )
    events.append_event(conn, tick, "era", "legacy", None, None, effects)
    return effects


def _era_name(legacy, era_number):
    names = legacy.get("era_names") or []
    if 0 < era_number <= len(names):
        return names[era_number - 1]
    return None
