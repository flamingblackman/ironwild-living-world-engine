"""Session-close sweep (Phase 2 harness, items 2–3).

ChatGPT DMs a turn and proposes a Turn state block in Lore's V2
`[TURN STATE]` format. This module parses that block, validates it
against the engine DB (clocks, Bonds, actors), and shows old-to-new
for review. Nothing lands without Bryan's approval in the hub: the
parse/validate/diff path is read-only, and `apply_sweep` only runs
when the caller passes an approver.

Rules, from Lore's Phase 2 inputs (lore-phase-2-inputs.md):
- Parse the literal heading `[TURN STATE]` and the literal field
  labels. Do not accept paraphrased labels.
- A block missing the heading, missing the Player character line, or
  with a Bond outside 0–5 fails validation.
- A clock value never decreases silently — a lower value in a later
  block is a data error, not a tick.
- A clock-name mismatch is flagged for Lore review, never silently
  reconciled or renamed.
- Unresolved Decisions are carried verbatim. The parser records them
  as pending. It never resolves them.
- The frozen live state (Turn 136 vFINAL.5) never enters Fork A.
- A sweep from a block whose clocks are not in `Name value/max` form
  carries the clocks as text and changes no clock.

What the sweep changes: clock values (up only, never down) and Bond
values, each as one append-only event with old and new values, in a
single transaction. If a clock reaches its max, the next tick fires
its completion effects (see src/clocks.py check_completions) — the
sweep itself never fires completion effects.
"""

import json
import re

from src import db, events, resources, session as session_mod

FROZEN_TURN = 136
FROZEN_VERSION = "vFINAL.5"
SCENE_TENSIONS = {"Low", "Rising", "Snap-Point", "Catastrophic"}

FIELD_LABELS = [
    "Universe", "State-Version", "Base", "Turn", "Clocks", "Scene",
    "SCENE_TENSION", "ACTIVE_TRADE_OFF", "Player character",
    "Unresolved Decisions",
]

_CLOCK_RE = re.compile(
    r"^(.+?)\s+(\d+)/(\d+)(?:\s*\(([^)]*)\))?\s*$")
_BOND_RE = re.compile(r"Bond\s+(\d+)/5")


class SweepError(ValueError):
    """The block fails parsing, or apply is refused."""


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _parse_fields(text):
    """Split the block body into {label: value} on literal labels.

    A line starting with a known label opens a field; any other line
    appends to the current field. Raises SweepError on a missing
    heading or closing marker.
    """
    start = text.find("[TURN STATE]")
    end = text.find("[/TURN STATE]")
    if start < 0:
        raise SweepError("missing literal heading [TURN STATE]")
    if end < 0 or end <= start:
        raise SweepError("missing closing marker [/TURN STATE]")
    body = text[start + len("[TURN STATE]"):end]
    fields = {}
    current = None
    label_re = re.compile(
        r"^(" + "|".join(re.escape(l) for l in FIELD_LABELS) + r"):\s*(.*)$")
    for raw in body.strip().splitlines():
        line = raw.strip()
        if not line:
            continue
        # Fields may share a line, pipe-joined ("Universe: Ironwild |
        # State-Version: vFINAL | Turn: 131"), so split on "|" first.
        # A segment that opens with a known label starts that field;
        # any other segment appends to the current field, keeping the
        # "|" so the Clocks and Scene parsers can split on it again.
        for segment in line.split("|"):
            seg = segment.strip()
            if not seg:
                continue
            m = label_re.match(seg)
            if m:
                current = m.group(1)
                fields[current] = m.group(2).strip()
            elif current is not None:
                fields[current] += " | " + seg
            else:
                raise SweepError("text before the first field label: %r"
                                 % seg)
    return fields


def _parse_clocks(raw):
    """Parse the Clocks field. Returns (clocks, text_segments).

    Clocks may be `|`- or `;`-separated. A segment that matches
    `Name value/max` (with an optional parenthetical — only
    (Complete) / (Detonated) count as a status, any other
    parenthetical such as "(proposed, pending approval)" is ignored)
    is a clock. A segment that does not match — prose, e.g. a resolved
    campaign clock the start pack lists for context — is carried as
    text, never silently reconciled, and never fails the field.
    `clocks` is None only when NO segment matches (fully prose
    clocks, carried as text, no clock changes).
    """
    clocks = []
    text = []
    for segment in re.split(r"[|;]", raw):
        seg = segment.strip()
        if not seg:
            continue
        m = _CLOCK_RE.match(seg)
        if not m:
            text.append(seg)
            continue
        status = m.group(4)
        clocks.append({
            "name": m.group(1).strip(),
            "value": int(m.group(2)),
            "max": int(m.group(3)),
            # Only Complete / Detonated count as a status; any other
            # parenthetical is a note, not a state.
            "status": status if status in ("Complete", "Detonated")
            else None,
        })
    return (clocks if clocks else None), text


def _parse_bonds(pc_line):
    """Extract Engine Bonds from the Player character line.

    Each `Bond n/5` takes its engine name from the first comma segment
    of the text since the previous ';', ':' or sentence end — e.g.
    "Gold Sledge, black-and-gold gorilla Bulwark, Bond 3/5" gives Gold
    Sledge, and "Five Engines, all exhausted and battered: Gold
    Sledge, ..., Bond 3/5" gives Gold Sledge too (the ':' after the
    preamble is a boundary). A leading "Engines:" marker is stripped.
    Raises SweepError on a Bond outside 0–5.
    """
    bonds = []
    for m in _BOND_RE.finditer(pc_line):
        value = int(m.group(1))
        if value < 0 or value > 5:
            raise SweepError("Bond %d/5 is outside 0-5" % value)
        before = pc_line[:m.start()]
        chunk = re.split(r"[;.:]", before)[-1].strip()
        if chunk.lower().startswith("engines:"):
            chunk = chunk[len("engines:"):].strip()
        name = chunk.split(",")[0].strip()
        if not name:
            raise SweepError("Bond %d/5 has no engine name before it" % value)
        bonds.append({"engine": name, "bond": value})
    return bonds


def _parse_pack(pc_line):
    """Pack membership from `Pack: A, B, C.` in the PC line."""
    m = re.search(r"Pack:\s*([^.;]+)", pc_line)
    if not m:
        return []
    return [p.strip() for p in m.group(1).split(",") if p.strip()]


def _parse_wounds(pc_line):
    m = re.search(r"Wounds:\s*([^.;]+)", pc_line)
    return m.group(1).strip() if m else None


def _split_scene(fields):
    """Scene, SCENE_TENSION, and ACTIVE_TRADE_OFF may arrive as
    separate labeled lines or as `|` segments of one Scene line."""
    scene = fields.get("Scene", "")
    tension = fields.get("SCENE_TENSION", "")
    trade_off = fields.get("ACTIVE_TRADE_OFF", "")
    if scene and ("|" in scene) and (not tension or not trade_off):
        parts = [p.strip() for p in scene.split("|")]
        scene = parts[0]
        for part in parts[1:]:
            if part.startswith("SCENE_TENSION:"):
                tension = part.split(":", 1)[1].strip()
            elif part.startswith("ACTIVE_TRADE_OFF:"):
                trade_off = part.split(":", 1)[1].strip()
    return scene, tension, trade_off


def parse_state_block(text):
    """Parse a V2 [TURN STATE] block into a structured dict.

    Raises SweepError on a missing heading, a missing Player character
    line, a non-integer Turn, an invalid SCENE_TENSION, or a Bond
    outside 0–5.
    """
    fields = _parse_fields(text)
    if "Player character" not in fields:
        raise SweepError("missing Player character line")
    try:
        turn = int(fields.get("Turn", "").strip())
    except ValueError:
        raise SweepError("Turn is not an integer: %r"
                         % fields.get("Turn", ""))
    scene, tension, trade_off = _split_scene(fields)
    if tension and tension not in SCENE_TENSIONS:
        raise SweepError("SCENE_TENSION %r is not one of %s"
                         % (tension, sorted(SCENE_TENSIONS)))
    unresolved = fields.get("Unresolved Decisions", "").strip()
    clocks, clocks_text = _parse_clocks(fields.get("Clocks", ""))
    return {
        "universe": fields.get("Universe", "").strip(),
        "state_version": fields.get("State-Version", "").strip(),
        # Base: the state version the proposal was built on (the
        # Gemini Skill adds this line). Absent in older blocks
        # (ChatGPT Turns 132/133) — those keep working, Base is
        # simply None. Before this field existed, a Base line
        # polluted State-Version ("ForkA-vFINAL.4 | Base:
        # ForkA-vFINAL.3") and the intake rejected the block.
        "base_version": fields.get("Base", "").strip() or None,
        "turn": turn,
        "clocks_raw": fields.get("Clocks", "").strip(),
        "clocks": clocks,
        "clocks_text": clocks_text,
        "scene": scene,
        "scene_tension": tension,
        "active_trade_off": trade_off,
        "pc_raw": fields["Player character"],
        "bonds": _parse_bonds(fields["Player character"]),
        "pack": _parse_pack(fields["Player character"]),
        "wounds": _parse_wounds(fields["Player character"]),
        "unresolved_decisions":
            None if unresolved.lower() == "none" else unresolved,
    }


def _clock_rows(conn):
    return {r["id"]: dict(r) for r in
            conn.execute("SELECT * FROM clocks").fetchall()}


def _engine_rows(conn):
    return {r["id"]: dict(r) for r in
            conn.execute("SELECT * FROM engines").fetchall()}


def _find_clock(parsed_name, rows):
    want = _norm(parsed_name)
    for row_id, row in rows.items():
        if _norm(row.get("name")) == want or _norm(row_id) == want:
            return row
    return None


def _find_engine(parsed_name, rows):
    want = _norm(parsed_name)
    for row_id, row in rows.items():
        if _norm(row.get("name")) == want or _norm(row_id) == want:
            return row
    return None


def validate(parsed, conn):
    """Check a parsed block against the DB.

    Returns a list of findings, each {level, code, message}.
    level "error" blocks apply; level "flag" goes to review.
    """
    findings = []
    if not parsed["state_version"]:
        findings.append({
            "level": "error", "code": "NO_VERSION",
            "message": "the block does not identify its base version "
                       "(State-Version missing); every proposal must name "
                       "the state version it was based on."})
    if (parsed["turn"] == FROZEN_TURN
            and parsed["state_version"] == FROZEN_VERSION):
        findings.append({
            "level": "error", "code": "FROZEN_LIVE",
            "message": "Turn 136 vFINAL.5 is the frozen live state; "
                       "it never enters Fork A."})
    # Base: the version the proposal was built on. A mismatch with
    # the last approved (swept) version is a FLAG, not an error —
    # whether Base must equal last_swept_version or the last
    # generated handshake's version is still an open design question
    # (Fork A continuation vs Fork G), and a flag keeps the review
    # honest without blocking a good proposal. Absent Base (older
    # blocks) is not flagged: the ChatGPT blocks never carried it.
    last_swept_version = db.get_meta(conn, "last_swept_version")
    if (parsed.get("base_version") and last_swept_version
            and parsed["base_version"] != last_swept_version):
        findings.append({
            "level": "flag", "code": "BASE_MISMATCH",
            "message": "block says it is based on %s, but the last "
                       "approved version is %s; the DM may be working "
                       "from a newer handshake than the last sweep — "
                       "Bryan decides whether that is the right base."
                       % (parsed["base_version"], last_swept_version)})
    if parsed["clocks"] is None:
        findings.append({
            "level": "flag", "code": "NO_CLOCKS_PARSED",
            "message": "Clocks field is not in Name value/max form; "
                       "carried as text, no clock changes applied."})
    else:
        rows = _clock_rows(conn)
        for clock in parsed["clocks"]:
            row = _find_clock(clock["name"], rows)
            if row is None:
                findings.append({
                    "level": "flag", "code": "CLOCK_UNKNOWN",
                    "message": "clock %r is not in this world; "
                               "clock-name mismatch, Lore review, never "
                               "silently reconciled." % clock["name"]})
                continue
            if clock["value"] < row["value"]:
                findings.append({
                    "level": "error", "code": "CLOCK_DECREASE",
                    "message": "clock %s would fall %d -> %d; a lower "
                               "value is a data error, not a tick."
                               % (row["id"], row["value"], clock["value"])})
            if clock["value"] > clock["max"]:
                findings.append({
                    "level": "error", "code": "CLOCK_OVER_MAX",
                    "message": "clock %s value %d exceeds its max %d."
                               % (row["id"], clock["value"], clock["max"])})
            if clock["status"] == "Complete" and row["status"] != "complete":
                if clock["value"] < clock["max"]:
                    findings.append({
                        "level": "flag", "code": "CLOCK_STATUS",
                        "message": "block says clock %s is Complete but "
                                   "its value %d/%d is below max."
                                   % (row["id"], clock["value"],
                                      clock["max"])})
    engines = _engine_rows(conn)
    for bond in parsed["bonds"]:
        if _find_engine(bond["engine"], engines) is None:
            findings.append({
                "level": "error", "code": "ENGINE_UNKNOWN",
                "message": "Bond names engine %r, which is not in this "
                           "world." % bond["engine"]})
    if parsed["unresolved_decisions"]:
        findings.append({
            "level": "flag", "code": "PENDING_DECISION",
            "message": "Unresolved Decisions present; carried verbatim, "
                       "never resolved by the sweep."})
    last_swept = db.get_meta(conn, "last_swept_turn")
    if last_swept is not None and parsed["turn"] < int(last_swept):
        findings.append({
            "level": "error", "code": "STALE_PROPOSAL",
            "message": "Turn %d is older than the last approved turn "
                       "(%s); an old proposal cannot overwrite newer "
                       "approved state. Revise from the current state."
                       % (parsed["turn"], last_swept)})
    # Staleness is judged by Turn: a Turn-N proposal is based on the
    # last approved version before it, and versions increment once per
    # played turn. The version string itself is recorded and shown in
    # the review; the Turn is what refuses a stale base.
    elif last_swept is not None and parsed["turn"] == int(last_swept):
        findings.append({
            "level": "flag", "code": "TURN_ORDER",
            "message": "Turn %d is the last swept turn (%s); re-sweep, "
                       "review before applying."
                       % (parsed["turn"], last_swept)})
    return findings


def diff(parsed, conn, resource_changes=None):
    """Old-to-new changes the block would make. Empty when the block
    matches the DB (a clean re-sweep). Only known clocks and engines,
    plus any explicitly approved resource changes (the V2 block has no
    Resources field, so a resource change the hub approved by name —
    e.g. Legion Salvage 12 -> 11 — arrives as a resource change, never
    inferred from the block)."""
    changes = []
    if parsed["clocks"]:
        rows = _clock_rows(conn)
        for clock in parsed["clocks"]:
            row = _find_clock(clock["name"], rows)
            if row is None or row["value"] == clock["value"]:
                continue
            changes.append({"kind": "clock", "id": row["id"],
                            "name": row["name"],
                            "old": row["value"], "new": clock["value"],
                            "max": clock["max"]})
    engines = _engine_rows(conn)
    bonds = {r["engine_id"]: r["bond"] for r in
             conn.execute("SELECT engine_id, bond FROM bonds").fetchall()}
    for bond in parsed["bonds"]:
        row = _find_engine(bond["engine"], engines)
        if row is None:
            continue
        old = bonds.get(row["id"])
        if old is not None and old != bond["bond"]:
            changes.append({"kind": "bond", "id": row["id"],
                            "name": row["name"],
                            "old": old, "new": bond["bond"]})
    for rc in resource_changes or []:
        current = resources.get_qty(conn, rc["holder"],
                                    rc["holder_kind"], rc["resource"])
        if current != rc["old"]:
            raise SweepError(
                "resource %s/%s %s is %d in the DB, not the approved "
                "old value %d; refusing to apply a change from a stale "
                "base." % (rc["holder"], rc["holder_kind"],
                           rc["resource"], current, rc["old"]))
        if current != rc["new"]:
            changes.append({"kind": "resource",
                            "holder": rc["holder"],
                            "holder_kind": rc["holder_kind"],
                            "resource": rc["resource"],
                            "old": rc["old"], "new": rc["new"]})
    return changes


def summarize(parsed, findings, changes, conn=None):
    """The old-to-new review text shown to Bryan before applying.

    When `conn` is given, the review also shows the base version the
    proposal was built on against the last approved version — so a
    stale proposal is visible before anyone approves it.
    """
    lines = ["Sweep review — Turn %d %s"
             % (parsed["turn"], parsed["state_version"])]
    if conn is not None:
        lines.append(
            "Based on: Turn %d %s | Last approved: Turn %s %s"
            % (parsed["turn"], parsed["state_version"],
               db.get_meta(conn, "last_swept_turn") or "-",
               db.get_meta(conn, "last_swept_version") or "-"))
    if parsed.get("base_version"):
        lines.append("Base (carried): %s — the version this proposal "
                     "was built on." % parsed["base_version"])
    lines.append("Scene: %s | tension %s"
                 % (parsed["scene"], parsed["scene_tension"] or "-"))
    if parsed.get("active_trade_off"):
        lines.append("Trade-off (carried): %s"
                     % parsed["active_trade_off"])
    if parsed.get("clocks_text"):
        lines.append("Clocks carried as text (context, not running "
                     "clocks): %s" % "; ".join(parsed["clocks_text"]))
    if changes:
        lines.append("Changes (%d):" % len(changes))
        for c in changes:
            if c["kind"] == "clock":
                lines.append("  clock %s: %d -> %d (max %d)"
                             % (c["id"], c["old"], c["new"], c["max"]))
            elif c["kind"] == "resource":
                lines.append("  resource %s %s: %d -> %d"
                             % (c["holder"], c["resource"],
                                c["old"], c["new"]))
            else:
                lines.append("  Bond %s: %d -> %d"
                             % (c["id"], c["old"], c["new"]))
    else:
        lines.append("Changes: none — the block matches the DB.")
    if findings:
        lines.append("Findings:")
        for f in findings:
            lines.append("  [%s] %s: %s"
                         % (f["level"].upper(), f["code"], f["message"]))
    else:
        lines.append("Findings: none.")
    if parsed["unresolved_decisions"]:
        lines.append("Pending decision (verbatim): "
                     + parsed["unresolved_decisions"][:200])
    return "\n".join(lines)


def apply_sweep(parsed, conn, approved_by, flag_path=None,
                resource_changes=None, lore_approval=None):
    """Apply a validated block in one transaction.

    Raises SweepError when validation has errors, when the session
    flag is open, or when no approver is named. `resource_changes`
    are explicitly approved resource moves (the V2 block has no
    Resources field); each is validated against the DB's current
    value and applied in the same transaction, one append-only event
    per change. `lore_approval` is the Lore submission id when the
    apply rests on Lore's verdict (a Lore-call proposal): the audit
    trail then records the approver as Lore, not Bryan, so a
    Lore-approved apply is distinguishable from a Bryan-approved
    one. Returns the applied changes plus the carried state
    for the next handshake.
    """
    if not approved_by:
        raise SweepError("apply needs an approver (Bryan's tap in the hub)")
    reason = session_mod.refuse_reason(flag_path) if flag_path else None
    if reason:
        raise SweepError(reason)
    findings = validate(parsed, conn)
    errors = [f for f in findings if f["level"] == "error"]
    if errors:
        raise SweepError("validation errors block apply: "
                         + "; ".join(e["message"] for e in errors))
    for rc in resource_changes or []:
        if rc["new"] < 0:
            raise SweepError("resource %s/%s %s cannot go below 0"
                             % (rc["holder"], rc["holder_kind"],
                                rc["resource"]))
    changes = diff(parsed, conn, resource_changes)
    tick = db.get_tick(conn)
    with conn:
        for c in changes:
            if c["kind"] == "clock":
                conn.execute("UPDATE clocks SET value = ? WHERE id = ?",
                             (c["new"], c["id"]))
                events.append_event(
                    conn, tick, "sweep", "sweep_clock", None, None,
                    [{"op": "sweep_clock", "clock": c["id"],
                      "old": c["old"], "new": c["new"],
                      "source_turn": parsed["turn"]}])
            elif c["kind"] == "resource":
                delta = c["new"] - c["old"]
                applied = resources.add_qty(
                    conn, c["holder"], c["holder_kind"], c["resource"],
                    delta)
                events.append_event(
                    conn, tick, "sweep", "sweep_resource", None, None,
                    [{"op": "resource_add", "holder": c["holder"],
                      "holder_kind": c["holder_kind"],
                      "resource": c["resource"], "qty": delta,
                      "applied_qty": applied,
                      "source_turn": parsed["turn"]}])
            else:
                conn.execute("UPDATE bonds SET bond = ? WHERE engine_id = ?",
                             (c["new"], c["id"]))
                events.append_event(
                    conn, tick, "sweep", "sweep_bond", None, None,
                    [{"op": "sweep_bond", "engine": c["id"],
                      "old": c["old"], "new": c["new"],
                      "source_turn": parsed["turn"]}])
        events.append_event(
            conn, tick, "sweep", "sweep", None, None,
            [{"op": "note",
              "text": ("sweep Turn %d %s: %d change(s), Lore-approved "
                       "(submission %s)"
                       % (parsed["turn"], parsed["state_version"],
                          len(changes), lore_approval))
                      if lore_approval else
                      "sweep Turn %d %s: %d change(s), approved by %s"
                      % (parsed["turn"], parsed["state_version"],
                         len(changes), approved_by)}])
        db.set_meta(conn, "last_swept_turn", parsed["turn"])
        db.set_meta(conn, "last_swept_version", parsed["state_version"])
        # The auto tick's pending-decision guard reads this: the
        # block's decision, or empty when the block resolves it. The
        # runner refuses while a decision is recorded here.
        db.set_meta(conn, "pending_decision",
                    parsed["unresolved_decisions"] or "")
    carried = {
        "turn": parsed["turn"],
        "state_version": parsed["state_version"],
        "base_version": parsed.get("base_version"),
        "scene": parsed["scene"],
        "scene_tension": parsed["scene_tension"],
        "active_trade_off": parsed["active_trade_off"],
        "pending_decision": parsed["unresolved_decisions"],
        "pc_raw": parsed["pc_raw"],
        "pack": parsed["pack"],
        "wounds": parsed["wounds"],
        "clocks_raw": parsed["clocks_raw"],
        # The checkpoint audit reads these directly: the block's Bonds
        # and clocks, so it can compare block value vs DB value now.
        "bonds": parsed["bonds"],
        "clocks": parsed["clocks"],
        # Explicitly approved resource changes, so the next handshake
        # and the checkpoint can see them (the V2 block has no
        # Resources field).
        "resources": [c for c in changes if c["kind"] == "resource"],
    }
    result = {"applied": changes, "carried": carried,
              "turn": parsed["turn"],
              "approved_by": "Lore" if lore_approval else approved_by}
    if lore_approval:
        result["lore_approval"] = lore_approval
    return result
