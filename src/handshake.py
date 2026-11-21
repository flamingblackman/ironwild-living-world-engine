"""Handshake back out (Phase 2 harness, item 3).

Before the next ChatGPT turn, the engine generates a handshake from
the DB alone, in Lore's 10-section shape (lore-phase-2-inputs.md
section 2): base state, PC, scene, Engines, Pack, Vance location,
clocks, resolved do-not-resurrect, Dormant Watchlist, pending decision
verbatim — plus what moved off-screen, rumors live, and clocks about
to fire. One page, roughly 400–600 words, state only.

Rules:
- Every line traces to the DB or to the carried state from the last
  swept block. The generator invents nothing.
- Rumors trace to logged events only, are always labeled
  "Rumor (unverified):", use uncertain language, and name no witness
  the engine invented. Never a sealed mystery, canon as uncertain,
  the Turn 136 decision, Bryan/the real world, NPC thoughts, or a
  future event. A clock about to fire is a clock warning, not a rumor.
- The handshake is not canon until Bryan plays it.
"""

import json
import re

from src import db, forks, render

_BOND_RE = re.compile(r"Bond\s+(\d+)/5")

# The status word right after an engine's Bond in the PC line:
# "exhausted" or "field-patched", the only engine statuses so far.
_STATUS_RE = re.compile(r",\s*(exhausted|field-patched)")

MAX_WORDS = 600
MAX_RUMORS = 3

# Harness framing, from Lore's handshake spec (inputs doc section 2):
# each test fork is a parallel timeline and nothing transfers back
# unless Bryan says so. This is about the harness, not the world.
# The fork name follows the DB's world_id (Fork A is the default;
# Fork G is the Gemini test).
def _test_framing(world_id):
    fork = forks.fork_display(world_id)
    return ("Parallel test timeline (%s). Nothing here transfers "
            "back to live canon unless Bryan says so." % fork)


# Fork version prefixes, from the fork registry: the handshake's
# State-Version follows the DB's world_id.
def _fork_prefix(world_id):
    return forks.fork_prefix(world_id)

# Fork A constants from Lore's Phase 2 inputs (section 2) and the
# start pack Part B. The V2 block has no resolved-list or watchlist
# fields, so the sweep's carried state never includes them; the
# handshake carries them as defaults until a turn resolves something
# new. These are Lore's stated facts, not invented values. (Fork B,
# a new story, has empty defaults; see src/forks.py.)
RESOLVED_DEFAULT = forks.fork_resolved_default("ironwild-fork-a")
WATCHLIST_DEFAULT = forks.fork_watchlist_default("ironwild-fork-a")

# Rumor templates by event kind. {place} and {clock} come from the
# event's own effect ops; a rumor with no place or clock is skipped,
# never filled in with an invented one.
_RUMOR_TEMPLATES = {
    "claim": "Rumor (unverified): traders say {place} has changed hands.",
    "raid": ("Rumor (unverified): word from the road says raiders "
             "struck near {place}."),
    "clock_complete": ("Rumor (unverified): word is the {clock} has run "
                       "its course."),
    "trade": ("Rumor (unverified): the caravan hears trade is moving "
              "again on the road."),
}

# Event actions the rumor pass never uses.
_RUMOR_EXCLUDED = {"sweep", "sweep_clock", "sweep_bond", "rest", "note"}


def _place_names(conn):
    rows = conn.execute("SELECT id, name FROM locations").fetchall()
    return {r["id"]: r["name"] for r in rows}


def _clock_names(conn):
    rows = conn.execute("SELECT id, name FROM clocks").fetchall()
    return {r["id"]: r["name"] for r in rows}


def _event_place(effect, places):
    """First location id or name found in the effect ops, or None.

    A location may appear as a bare id ("great_basin") or embedded in
    a flag name ("raid_in_progress:great_basin"). Either counts — the
    flag names the place. A rumor with no place is skipped, never
    filled in with an invented one.
    """
    for op in effect:
        for value in op.values():
            if isinstance(value, str):
                if value in places:
                    return places[value]
                for part in re.split(r"[^a-z0-9_]+", value):
                    if part in places:
                        return places[part]
                for loc_id, loc_name in places.items():
                    if value == loc_name:
                        return loc_name
    return None


def _rumor_for_event(row, places, clocks):
    """One rumor string for a logged event, or None when the event is
    not rumor-eligible or carries no place/clock to name."""
    action = row["action"]
    if action in _RUMOR_EXCLUDED or row["actor_id"] == "sweep":
        return None
    try:
        effect = json.loads(row["effect"])
    except (ValueError, TypeError):
        return None
    if action == "complete":
        clock_id = row["actor_id"].split(":", 1)[-1]
        name = clocks.get(clock_id, clock_id)
        return _RUMOR_TEMPLATES["clock_complete"].format(clock=name)
    if action.startswith("claim"):
        place = _event_place(effect, places)
        return (_RUMOR_TEMPLATES["claim"].format(place=place)
                if place else None)
    if action.startswith("raid"):
        place = _event_place(effect, places)
        return (_RUMOR_TEMPLATES["raid"].format(place=place)
                if place else None)
    if action.startswith("trade"):
        return _RUMOR_TEMPLATES["trade"]
    return None


def rumors_from_events(conn, since_tick=0, limit=MAX_RUMORS):
    """Rumors the next handshake would carry, with their source event
    ids. Every rumor traces to a logged event; a rumor with no place
    or clock is skipped, never invented. The checkpoint reuses this so
    its rumor section and the handshake can never disagree."""
    places = _place_names(conn)
    clocks = _clock_names(conn)
    rows = conn.execute(
        "SELECT id, tick, actor_id, action, effect FROM events "
        "WHERE tick > ? ORDER BY id DESC", (since_tick,)).fetchall()
    rumors = []
    seen = set()
    for row in rows:
        if len(rumors) >= limit:
            break
        text = _rumor_for_event(row, places, clocks)
        if text and text not in seen:
            rumors.append((row["id"], text))
            seen.add(text)
    return rumors


def _off_screen_lines(conn, since_tick, places, clocks):
    """Recent events as plain-language lines, newest first.

    Sweep-actor events are ledger bookkeeping, not off-screen world
    movement — the DM proposed the change, and the Clocks/Engines
    sections already show the result — so they never appear here.
    (A Turn 132 correction event at tick 3 leaked in otherwise.)"""
    rows = conn.execute(
        "SELECT id, tick, actor_id, action, effect FROM events "
        "WHERE tick > ? AND actor_id != 'sweep' "
        "ORDER BY id DESC LIMIT 20",
        (since_tick,)).fetchall()
    lines = []
    for row in rows:
        try:
            effect = json.loads(row["effect"])
        except (ValueError, TypeError):
            continue
        text = "; ".join(
            t for t in (render._effect_text(op) for op in effect)
            if t) or "-"
        lines.append("Tick %d — %s %s: %s"
                     % (row["tick"], row["actor_id"], row["action"], text))
    return lines, [r["id"] for r in rows]


def _refresh_engine_state_in_pc(pc_text, conn):
    """Rewrite the PC line's Bond numbers and engine statuses from the DB.

    Bond values are single digits (0–5), so replacing one never
    changes the text length. Statuses can differ in length
    ("exhausted" vs "field-patched"), so engines are processed last
    to first: a replacement never shifts a span that is still to be
    searched. Each engine's "Bond N/5" is the first one after its
    name and before the next engine's name, and its status is the
    first "exhausted" or "field-patched" after that Bond; an engine
    whose name is absent, or with no Bond in its span, is left
    alone. If any Bond changed, the carried claim "All Engine Bonds
    unchanged." is dropped, since it is now false. A status change
    does not touch that claim — it speaks about Bonds only.
    """
    rows = conn.execute(
        "SELECT e.name AS name, b.bond AS bond, e.status AS status "
        "FROM engines e JOIN bonds b ON b.engine_id = e.id").fetchall()
    positions = []
    for name, bond, status in rows:
        at = pc_text.find(name)
        if at >= 0:
            positions.append((at, name, bond, status))
    positions.sort()
    changed = False
    text = pc_text
    for i in range(len(positions) - 1, -1, -1):
        at, name, bond, status = positions[i]
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        m = _BOND_RE.search(text, at + len(name), end)
        if not m:
            continue
        if int(m.group(1)) != bond:
            text = text[:m.start(1)] + str(bond) + text[m.end(1):]
            changed = True
        s = _STATUS_RE.search(text, m.end(), end)
        if s and s.group(1) != status:
            text = text[:s.start(1)] + status + text[s.end(1):]
    if changed:
        text = text.replace("All Engine Bonds unchanged. ", "")
        text = text.replace("All Engine Bonds unchanged.", "")
    return text


def generate_handshake(conn, carried, since_tick=0):
    """Build the handshake text plus audit metadata.

    `carried` is the state from the last swept block (see
    sweep.apply_sweep): scene, pending decision, PC line, resolved
    list, watchlist, Vance location. The PC line's Bonds and engine
    statuses are refreshed from the DB (see
    _refresh_engine_state_in_pc) — the carried text is historical
    and a tick can move a Bond or field-patch an Engine. Missing carried
    fields fall back
    to the DB where the DB knows the answer, to Lore's stated
    constants for the resolved list and watchlist (the V2 block has
    no such fields), and to an explicit "not recorded" where neither
    knows — never an invented value.
    The Base state line names the next State-Version and Turn (one
    past the last swept turn in the DB), because the first-reply
    instruction asks the DM to echo them.
    Returns {"text": str, "meta": {...}}.
    """
    tick = db.get_tick(conn)
    places = _place_names(conn)
    clocks = _clock_names(conn)
    world_id = db.get_meta(conn, "world_id", "unknown")
    fork_label = db.get_meta(conn, "fork_label", "")
    source = db.get_meta(conn, "source_snapshot", "")

    # The handshake names its own next State-Version and Turn: the
    # first-reply instruction asks the DM to echo them, and a
    # handshake that never states them makes the DM fall back to the
    # last accepted version in chat history (Turn 134 echoed .2/133).
    # The next turn is one past the last swept turn; a DB with no
    # sweeps yet opens at its fork's first turn (132 for Fork A,
    # 1 for Fork B).
    last_swept = db.get_meta(conn, "last_swept_turn")
    next_turn = ((int(last_swept) + 1) if last_swept is not None
                 else forks.fork_first_turn(world_id))
    state_version = forks.fork_version(world_id, next_turn)

    engines = conn.execute(
        "SELECT e.id, e.name, e.shape, e.status, b.bond "
        "FROM engines e JOIN bonds b ON b.engine_id = e.id "
        "ORDER BY e.id").fetchall()
    clock_rows = conn.execute(
        "SELECT * FROM clocks ORDER BY id").fetchall()
    pack = carried.get("pack") or []
    pack_names = ", ".join(pack) if pack else "not recorded"
    # The PC's faction: the faction of the pilot of any Engine (the
    # PC is the pilot). Generic across forks; Fork A reads Brigus /
    # Ironwild Legion, Fork B reads Rook / Great Basin.
    faction = conn.execute(
        "SELECT f.name FROM engines e JOIN npcs n "
        "ON n.id = e.pilot_id JOIN factions f "
        "ON f.id = n.faction_id WHERE e.pilot_id IS NOT NULL "
        "LIMIT 1").fetchone()
    faction_name = faction["name"] if faction else "not recorded"
    companion_id, companion_label = forks.fork_companion(world_id)
    companion = conn.execute(
        "SELECT l.name FROM npcs n JOIN locations l "
        "ON l.id = n.location_id WHERE n.id = ?",
        (companion_id,)).fetchone()
    # Actor locations come from the DB (Lore, 2026-11-21). The carried
    # state is only a fallback when the DB has no location for the
    # actor — never the other way round.
    companion_loc = ((companion["name"] if companion else None)
                     or carried.get("vance_location")
                     or "not recorded")
    pc_short = carried.get("pc_short")
    if not pc_short:
        # The PC line is carried in full, never truncated: the start
        # pack requires the Player character line in full, all five
        # Engines with Bonds and details. A 200-char cap cut it
        # mid-list ("...battered: Gold").
        pc_short = carried.get("pc_raw", "") or "not recorded"
    # The PC line's Bonds and engine statuses come from the DB, never
    # the carried block: a tick after the sweep can restore a Bond
    # (Dream Share), burn one (Pack Merge), or field-patch an Engine
    # (repair), and the handshake must never carry two values for the
    # same Bond or status (the PC line from carried, the Engines
    # section from the DB). Turn 134 shipped Sledge 3/5 in the PC
    # line and 4/5 in the Engines section, and Razor-Back "exhausted"
    # against "field-patched"; the DM would have echoed the stale
    # values.
    if pc_short and pc_short != "not recorded":
        pc_short = _refresh_engine_state_in_pc(pc_short, conn)

    sections = []
    sections.append(
        "Base state: %s (%s), source %s. State-Version %s, Turn %d. "
        "Current tick %d. %s"
        % (world_id, fork_label, source, state_version, next_turn,
           tick, _test_framing(world_id)))
    sections.append(
        "PC: %s" % pc_short)
    sections.append(
        "Scene: %s | SCENE_TENSION: %s | ACTIVE_TRADE_OFF: %s"
        % (carried.get("scene") or "not recorded",
           carried.get("scene_tension") or "not recorded",
           carried.get("active_trade_off") or "none"))
    sections.append(
        "Engines:\n" + "\n".join(
            "  %s (%s), Bond %d/5, %s"
            % (e["name"], e["shape"], e["bond"], e["status"])
            for e in engines))
    sections.append("Pack: %s. Faction: %s." % (pack_names, faction_name))
    sections.append("%s location: %s." % (companion_label, companion_loc))
    sections.append(
        "Clocks:\n" + "\n".join(
            "  %s %d/%d%s" % (c["name"], c["value"], c["max"],
                             " (Complete)" if c["status"] == "complete"
                             else "")
            for c in clock_rows))
    resolved = (carried.get("resolved_do_not_resurrect")
                or forks.fork_resolved_default(world_id))
    sections.append(
        "Resolved, do not resurrect:\n" + "\n".join(
            "  %s" % r for r in resolved) if resolved
        else "Resolved, do not resurrect: not recorded.")
    watchlist = (carried.get("dormant_watchlist")
                 or forks.fork_watchlist_default(world_id))
    sections.append(
        "Dormant Watchlist:\n" + "\n".join(
            "  %s" % w for w in watchlist) if watchlist
        else "Dormant Watchlist: not recorded.")

    # What moved off-screen since the last session.
    off_lines, event_ids = _off_screen_lines(conn, since_tick, places,
                                             clocks)
    sections.append("What moved off-screen:\n" + (
        "\n".join("  " + line for line in off_lines)
        if off_lines else "  Nothing since the last session."))

    # Rumors live: from the same events, newest first, at most 3.
    rumors = rumors_from_events(conn, since_tick)
    sections.append("Rumors live:\n" + (
        "\n".join("  " + text for _, text in rumors)
        if rumors else "  None."))
    rumor_sources = [event_id for event_id, _ in rumors]

    # Clocks about to fire: within 1 of max, still running.
    warnings = [c for c in clock_rows
                if c["status"] == "running"
                and c["max"] - c["value"] <= 1]
    sections.append("Clocks about to fire:\n" + (
        "\n".join("  %s is at %d/%d." % (c["name"], c["value"], c["max"])
                  for c in warnings)
        if warnings else "  None."))

    pending = carried.get("pending_decision") or "none"
    sections.append("Pending decision, verbatim: %s" % pending)

    body = "\n\n".join(sections)
    # The first-reply instruction names the PC (the pilot of any
    # Engine). Generic across forks; Fork A reads Brigus, Fork B
    # reads Rook.
    pc_name_row = conn.execute(
        "SELECT n.name FROM engines e JOIN npcs n "
        "ON n.id = e.pilot_id WHERE e.pilot_id IS NOT NULL "
        "LIMIT 1").fetchone()
    pc_name = pc_name_row["name"] if pc_name_row else "the player"
    echo = ("First reply: echo the State-Version, Turn, clocks, scene, "
            "and pending decision verbatim, then stop at the decision. "
            "Do not advance the scene until %s acts. Do not open a "
            "new scene, arc, or Session Zero." % pc_name)
    text = ("```\n[HANDSHAKE]\n" + body + "\n[/HANDSHAKE]\n```\n\n" + echo)

    # Word budget: trim the off-screen list, oldest first, until the
    # text fits ~600 words. Canon sections are never trimmed.
    words = len(text.split())
    while words > MAX_WORDS and len(off_lines) > 3:
        off_lines = off_lines[:-1]
        sections[9] = "What moved off-screen:\n" + "\n".join(
            "  " + line for line in off_lines)
        body = "\n\n".join(sections)
        text = ("```\n[HANDSHAKE]\n" + body + "\n[/HANDSHAKE]\n```\n\n"
                + echo)
        words = len(text.split())

    return {"text": text, "meta": {
        "world_id": world_id, "tick": tick, "words": words,
        "state_version": state_version, "turn": next_turn,
        "events_covered": event_ids, "rumors": len(rumors),
        "rumor_sources": rumor_sources,
        "clocks_about_to_fire": [c["id"] for c in warnings],
    }}
