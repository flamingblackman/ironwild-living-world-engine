"""NPC / engine action scoring.

An action is legal for an actor when:
  - the actor's kind matches the action's actor_kind,
  - the actor holds the action's capability (NPCs; engines need none),
  - every trigger clause holds, and
  - at least one of the action's goal_tags is one of the actor's goals
    (an action with no goal_tags matches any goal).

Score = weight (Lore-set priority, default 5)
      + 1 per need clause currently satisfied (the action's material effect
        addresses a live scarcity).

The score is transparent: the event row records the winner's score and the
runner-up, so any tick can be audited. Ties are broken by the run's seeded
RNG in tick.py, never by insertion order alone.
"""

import json

from . import conditions


def actor_capabilities(conn, actor):
    if actor["kind"] == "npc":
        row = conn.execute(
            "SELECT capabilities FROM npcs WHERE id = ?", (actor["id"],)
        ).fetchone()
        return json.loads(row["capabilities"]) if row else []
    return []


def actor_goals(conn, actor):
    if actor["kind"] == "npc":
        row = conn.execute(
            "SELECT goals FROM npcs WHERE id = ?", (actor["id"],)
        ).fetchone()
        return json.loads(row["goals"]) if row else []
    return []


def score_actions(conn, actor, catalog):
    """Return [(score, action), ...] sorted best-first for one actor."""
    caps = actor_capabilities(conn, actor)
    goals = actor_goals(conn, actor)
    scored = []
    for action in catalog:
        if action.get("actor_kind") != actor["kind"]:
            continue
        actor_ids = action.get("actor_ids")
        if actor_ids is not None and actor["id"] not in actor_ids:
            continue
        capability = action.get("capability")
        if capability and capability not in caps:
            continue
        goal_tags = action.get("goal_tags") or []
        if goal_tags and not any(tag in goals for tag in goal_tags):
            continue
        if not conditions.clauses_hold(conn, action.get("trigger") or []):
            continue
        need = sum(1 for c in (action.get("need") or [])
                   if conditions.clause_holds(conn, c))
        score = float(action.get("weight", 5)) + need
        scored.append((score, action))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored
