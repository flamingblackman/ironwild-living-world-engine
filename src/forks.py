"""Fork registry: per-world configuration for the living-world engine.

Each fork (a test timeline) has its own world_id, display name, version
prefix, first turn, and version scheme. The engine reads the DB's
world_id and looks the fork up here, so Fork A, Fork B, and Fork G
each get the right versioning, first turn, and display name without
any file hardcoding one fork's values. An unknown world_id falls back
to Fork A (the default pipeline; the fixture DBs carry it).

Version schemes (Bryan-approved):
- Fork A: Turn 132 opens at ForkA-vFINAL.1; version is ForkA-vFINAL.<turn-131>.
- Fork B: Turn 1 opens at ForkB-v1.0; version is ForkB-v1.<turn-1>.
- Fork G: like Fork A (Turn 132 opens at ForkG-vFINAL.1).
"""

_FORK_A_RESOLVED = [
    "Rift-King (corrupted Den Boss) annihilated in the Salt Flats.",
    "Den Boss dead.",
    "Deepmaw Migration diverted by the Acoustic Lure.",
]
_FORK_A_WATCHLIST = [
    "IW-42 Learning Black Box only.",
    "IW-46 and IW-84 activated and resolved in the final arc; "
    "do not re-trigger them as dormant.",
]

FORK_CONFIG = {
    "ironwild-fork-a": {
        "display": "Fork A",
        "prefix": "ForkA",
        "first_turn": 132,
        "version": lambda turn: "ForkA-vFINAL.%d" % (turn - 131),
        "version_re": r"^ForkA-vFINAL(\.\d+)?$",
        "version_example": "ForkA-vFINAL or ForkA-vFINAL.<k>",
        # The Pack member whose location the handshake tracks.
        "companion_id": "vance",
        "companion_label": "Vance",
        "resolved_default": list(_FORK_A_RESOLVED),
        "watchlist_default": list(_FORK_A_WATCHLIST),
    },
    "ironwild-fork-b": {
        "display": "Fork B",
        "prefix": "ForkB",
        "first_turn": 1,
        "version": lambda turn: "ForkB-v1.%d" % (turn - 1),
        "version_re": r"^ForkB-v1\.\d+$",
        "version_example": "ForkB-v1.<k>",
        "companion_id": "pip",
        "companion_label": "Pip",
        # New story: nothing resolved yet, nothing dormant.
        "resolved_default": [],
        "watchlist_default": [],
    },
    "ironwild-fork-g": {
        "display": "Fork G",
        "prefix": "ForkG",
        "first_turn": 132,
        "version": lambda turn: "ForkG-vFINAL.%d" % (turn - 131),
        "version_re": r"^ForkG-vFINAL(\.\d+)?$",
        "version_example": "ForkG-vFINAL or ForkG-vFINAL.<k>",
        "companion_id": "vance",
        "companion_label": "Vance",
        "resolved_default": list(_FORK_A_RESOLVED),
        "watchlist_default": list(_FORK_A_WATCHLIST),
    },
}

_DEFAULT = "ironwild-fork-a"


def fork_config(world_id):
    """The fork config for a world_id (Fork A when unknown)."""
    return FORK_CONFIG.get(world_id or _DEFAULT, FORK_CONFIG[_DEFAULT])


def fork_display(world_id):
    return fork_config(world_id)["display"]


def fork_prefix(world_id):
    return fork_config(world_id)["prefix"]


def fork_first_turn(world_id):
    return fork_config(world_id)["first_turn"]


def fork_version(world_id, turn):
    """The State-Version a turn carries in this fork."""
    return fork_config(world_id)["version"](turn)


def fork_version_re(world_id):
    return fork_config(world_id)["version_re"]


def fork_version_example(world_id):
    return fork_config(world_id)["version_example"]


def fork_companion(world_id):
    """(npc id, label) of the Pack member whose location the handshake tracks."""
    cfg = fork_config(world_id)
    return cfg["companion_id"], cfg["companion_label"]


def fork_resolved_default(world_id):
    return list(fork_config(world_id)["resolved_default"])


def fork_watchlist_default(world_id):
    return list(fork_config(world_id)["watchlist_default"])
