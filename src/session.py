"""Session open/close flag (Phase 2 harness).

The flag says whether a play session is live. The auto tick (Phase 2
item 1) refuses to tick while it is open, and the session-close sweep
refuses to apply while it is open — the sweep runs AFTER the flag is
cleared, at session close.

Who sets it: the hub / Lore, when a session starts. Who clears it: the
hub / Lore, at session close. The engine NEVER sets or clears it, and
never auto-clears a stale flag — a missed tick is a quiet day, and the
log says so. If the flag is older than 48 hours with no session
activity, the hub may clear it manually after confirming with Bryan
that no session is live. (Design from Lore's Phase 2 inputs,
living-world-engine/lore-phase-2-inputs.md section 5.)
"""

import json
import os

FLAG_PATH = os.path.join(os.path.dirname(__file__), "..", "state",
                         "session.json")


def default_flag(world_id):
    return {
        "session_open": False,
        "world_id": world_id,
        "opened_at": None,
        "opened_by": None,
        "turn": None,
    }


def load_flag(path=FLAG_PATH):
    """Read the flag. A missing file means closed (safe default)."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default_flag("unknown")


def save_flag(flag, path=FLAG_PATH):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(flag, f, indent=2, sort_keys=True)


def is_open(path=FLAG_PATH):
    return bool(load_flag(path).get("session_open", False))


def refuse_reason(path=FLAG_PATH):
    """None when the flag is closed, else the reason a tick/sweep must stop."""
    flag = load_flag(path)
    if not flag.get("session_open", False):
        return None
    return ("session is open (world %s, turn %s, opened %s by %s); "
            "tick/sweep refused until the hub clears it"
            % (flag.get("world_id"), flag.get("turn"),
               flag.get("opened_at"), flag.get("opened_by")))
