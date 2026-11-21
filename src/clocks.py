"""Clock completion. A clock that reaches its max fires its on_complete
effect ops (defined by Lore in the seed) once and marks itself complete.
"""

import json

from . import actions
from . import events


def check_completions(conn, tick):
    """Fire completion for every clock at max that is still running.

    Returns the list of clock ids completed this tick.
    """
    completed = []
    rows = conn.execute(
        "SELECT id, on_complete FROM clocks "
        "WHERE status = 'running' AND value >= max ORDER BY id"
    ).fetchall()
    for row in rows:
        effects = actions.apply_effects(
            conn, json.loads(row["on_complete"] or "[]"))
        conn.execute(
            "UPDATE clocks SET status = 'complete' WHERE id = ?", (row["id"],))
        events.append_event(conn, tick, f"clock:{row['id']}", "complete",
                            None, None, effects)
        completed.append(row["id"])
    return completed
