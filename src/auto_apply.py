"""0-change auto-apply (Bryan's standing approval, 2026-11-21 09:30 EST),
narrowed by Lore's canon guard (lore-auto-apply-guard.md).

A proposal auto-applies ONLY when the sweep is clean AND the block is
a pure carry-over of the last approved block (every field identical
except the State-Version/Turn increment). A 0-change block that
carries a narrative change the sweep cannot validate — a resolved or
new pending decision, a scene change, a new PC fact — does NOT
auto-apply; it goes to Lore for a call (APPROVE or ESCALATE to
Bryan). Anything with a mechanical change or a finding comes to
Bryan, as before.

The Turn 134 class does NOT auto-apply: Turn 134 was 0 mechanical
changes but resolved a pending decision narratively (Unresolved
Decisions went from the elite-force question to none). The sweep's
diff does not track the pending decision (it lives in meta, not in
clocks/Bonds/resources), so "0 changes" alone would let it through —
but resolving a decision clears the auto-tick guard and is a state
transition with consequences. Auto-apply requires the pending
decision to be UNCHANGED (the block's decision == the DB's decision,
including both empty).

Coverage limit, stated plainly: the guard's (d) (new rumor or
callback in the DM's reply narrative) and (e) (any other narrative
addition) cannot be checked from the block file — the Drive inbox
carries only the V2 block, not the reply narrative. They are covered
two other ways: the handshake generator emits rumors only from
logged events (an invented narrative rumor never enters the next
handshake), and Lore's post-apply audit of the first auto-applied
turn plus the formal 3-turn checkpoint cover the narrative. If a
reply narrative is ever carried with a proposal, (d)/(e) become
checkable and belong in flag_narrative_changes.
"""

import re

from src import db, forks, handshake as handshake_mod, session as session_mod

STANDING_APPROVAL = ("Bryan standing 0-change auto-apply approval, "
                     "2026-11-21 09:30 EST")

# Reason codes from check_eligible. A proposal whose codes are a
# subset of {"PENDING_DECISION"} and that carries narrative flags is
# a Lore call, not a Bryan hold (see attempt_auto_apply in run.py).
REASON_CHANGES = "CHANGES"
REASON_FINDINGS = "FINDINGS"
REASON_TURN = "TURN"
REASON_VERSION = "VERSION"
REASON_BASE = "BASE"
REASON_PENDING_DECISION = "PENDING_DECISION"
REASON_SESSION_OPEN = "SESSION_OPEN"


class LoreCall(Exception):
    """A 0-change proposal that needs Lore's call, not an auto-apply
    and not (yet) Bryan's. Carries the narrative flags so the caller
    can send the field diff to Lore."""

    def __init__(self, pid, flags):
        self.pid = pid
        self.flags = flags
        super().__init__(
            "proposal %s needs a Lore call: %s"
            % (pid, "; ".join("%s: %s" % (f["code"], f["detail"])
                              for f in flags)))


def _reason(code, message):
    return {"code": code, "message": message}


def check_eligible(parsed, findings, changes, conn, flag_path=None):
    """Return (eligible, reasons).

    `parsed` is a sweep_mod.parse_state_block result; `findings` and
    `changes` are fresh validate/diff results against the live DB.
    `reasons` is a list of {code, message}; the codes route a held
    proposal to Lore or to Bryan.
    """
    reasons = []
    if changes:
        kinds = ", ".join(
            "%s %s: %s -> %s"
            % (c["kind"], c.get("id") or c.get("holder", ""),
               c["old"], c["new"])
            for c in changes)
        reasons.append(_reason(
            REASON_CHANGES,
            "has %d change(s): %s" % (len(changes), kinds)))
    if findings:
        reasons.append(_reason(
            REASON_FINDINGS,
            "has %d finding(s): %s"
            % (len(findings),
               ", ".join(f["code"] for f in findings))))
    last_swept = db.get_meta(conn, "last_swept_turn")
    world_id = db.get_meta(conn, "world_id", "ironwild-fork-a")
    expected_turn = ((int(last_swept) + 1) if last_swept is not None
                     else forks.fork_first_turn(world_id))
    if parsed["turn"] != expected_turn:
        reasons.append(_reason(
            REASON_TURN,
            "turn %d is not the next turn (%d)"
            % (parsed["turn"], expected_turn)))
    expected_version = forks.fork_version(world_id, expected_turn)
    if parsed["state_version"] != expected_version:
        reasons.append(_reason(
            REASON_VERSION,
            "State-Version %s is not the expected next version %s"
            % (parsed["state_version"], expected_version)))
    last_swept_version = db.get_meta(conn, "last_swept_version")
    if (parsed.get("base_version") and last_swept_version
            and parsed["base_version"] != last_swept_version):
        reasons.append(_reason(
            REASON_BASE,
            "Base %s does not match the last approved version %s"
            % (parsed["base_version"], last_swept_version)))
    db_pending = db.get_meta(conn, "pending_decision") or ""
    block_pending = parsed["unresolved_decisions"] or ""
    if block_pending != db_pending:
        if db_pending and not block_pending:
            reasons.append(_reason(
                REASON_PENDING_DECISION,
                "resolves the pending decision %r — a state change "
                "that clears the auto-tick guard; comes to Bryan"
                % db_pending))
        elif block_pending and not db_pending:
            reasons.append(_reason(
                REASON_PENDING_DECISION,
                "creates a new pending decision %r; comes to Bryan"
                % block_pending))
        else:
            reasons.append(_reason(
                REASON_PENDING_DECISION,
                "pending decision text changed; comes to Bryan"))
    if session_mod.is_open(flag_path or session_mod.FLAG_PATH):
        reasons.append(_reason(
            REASON_SESSION_OPEN,
            "session flag is open; a live session is running"))
    return (not reasons, reasons)


_BOND_NORM_RE = re.compile(r"Bond\s+\d+/5")
_STATUS_NORM_RE = re.compile(r",\s*(exhausted|field-patched)")


def _normalize_pc(pc_text):
    """The PC line with its DB-driven values masked: Bond numbers and
    engine statuses move through ticks (Dream Share restores a Bond,
    a repair field-patches an engine), so they are not narrative
    facts. What remains is the narrative content; a difference there
    is a new PC fact."""
    text = _BOND_NORM_RE.sub("Bond #/5", pc_text or "")
    text = _STATUS_NORM_RE.sub(", <status>", text)
    return text


def flag_narrative_changes(parsed, last_carried, conn):
    """Compare a parsed block against the last approved block's
    carried record and flag the guard's (a)–(c). Returns a list of
    {code, detail}. Empty means a pure carry-over (for the fields
    the pipeline can see).

    `last_carried` is the carried dict from the last sweep
    (runs/sweeps/turn-<n>/carried.json), or None when no prior
    carried record exists. (d) and (e) are not checkable from the
    block file — see the module docstring.
    """
    flags = []
    if last_carried is None:
        flags.append({
            "code": "NO_BASELINE",
            "detail": "no prior carried record to compare against; "
                      "pure carry-over cannot be proven"})
        return flags
    block_pending = parsed["unresolved_decisions"] or ""
    last_pending = last_carried.get("pending_decision") or ""
    if block_pending != last_pending:
        if last_pending and not block_pending:
            detail = ("resolves the pending decision %r"
                      % last_pending)
        elif block_pending and not last_pending:
            detail = ("introduces a new pending decision %r"
                      % block_pending)
        else:
            detail = "pending decision text changed"
        flags.append({"code": "PENDING_DECISION", "detail": detail})
    scene_diffs = []
    if (parsed.get("scene") or "") != (last_carried.get("scene") or ""):
        scene_diffs.append("location")
    if ((parsed.get("scene_tension") or "")
            != (last_carried.get("scene_tension") or "")):
        scene_diffs.append("tension")
    if ((parsed.get("active_trade_off") or "")
            != (last_carried.get("active_trade_off") or "")):
        scene_diffs.append("trade-off")
    if scene_diffs:
        flags.append({
            "code": "SCENE_CHANGE",
            "detail": "scene differs from the last approved block: %s"
                      % ", ".join(scene_diffs)})
    if (_normalize_pc(parsed.get("pc_raw"))
            != _normalize_pc(last_carried.get("pc_raw"))):
        flags.append({
            "code": "NEW_PC_FACT",
            "detail": "Player character line adds text beyond the "
                      "carried facts (normalized comparison differs)"})
    # Statuses are masked by the normalization (they move through
    # ticks), so verify them separately against the DB: a block
    # status that contradicts the DB is a mechanical drift the sweep
    # does not check, and it must not hide behind the mask.
    engines = {}
    for row in conn.execute(
            "SELECT id, name, status FROM engines").fetchall():
        engines[_norm(row["id"])] = row
        engines[_norm(row["name"])] = row
    for bond in parsed.get("bonds", []):
        # This engine's Bond, then the status word right after it
        # (", exhausted" / ", field-patched" within a few chars).
        # The window is tight so a later engine's status word can
        # never be read as this engine's.
        pc = parsed.get("pc_raw") or ""
        name_at = pc.find(bond["engine"])
        if name_at < 0:
            continue
        bond_at = re.search(r"Bond\s+%d/5" % bond["bond"],
                            pc[name_at:])
        if bond_at is None:
            continue
        after = pc[name_at + bond_at.end():
                   name_at + bond_at.end() + 40]
        match = handshake_mod._STATUS_RE.search(after)
        if match is None:
            continue
        row = engines.get(_norm(bond["engine"]))
        if row is not None and match.group(1) != row["status"]:
            flags.append({
                "code": "STATUS_MISMATCH",
                "detail": "engine %s is %r in the block but %r in "
                          "the DB" % (bond["engine"], match.group(1),
                                     row["status"])})
            break
    return flags


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())
