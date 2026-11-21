"""Stage 1A proposal pipeline: Drive inbox intake + approval binding.

A proposal is a V2 [TURN STATE] block placed as a plain-text file in
the Drive inbox. Intake (poll) registers it, validates it, and
writes the review — it never touches the DB. Apply happens only by
proposal ID, only for Bryan, only when the Drive file's current
content still hashes to the reviewed content, and only in the one
transaction `sweep.apply_sweep` already guarantees.

Safeguards (stage-1-plan.md section 3):
- Unique proposal ID: prop-<turn>-<sha256(content)[:8]>, plus the
  Drive file ID recorded. A revised file is a new proposal.
- Base state version: the existing STALE_PROPOSAL / NO_VERSION /
  TURN_ORDER findings in sweep.validate.
- Strict Fork A identifier: validate_fork_a — Universe must be
  Ironwild and State-Version must be ForkA-vFINAL.<k>. This check
  lives HERE, not in sweep.validate, because the manual sweep path
  must keep accepting the historical samples (Turn 131 vFINAL, Turn
  136 vFINAL.5, Turn 138 vFINAL.7) for its own checks.
- Atomic approval-and-commit: the apply verifies the binding, then
  runs apply_sweep in one transaction, and records the approval
  (approver, timestamp, proposal ID, content hash) in applied.json.
"""

import hashlib
import json
import os
import re

from src import db, drive_io, events, sweep as sweep_mod

# The proposals tree is scopable for tests: IRONWILD_PROPOSALS_DIR
# points the registry + proposal records at a scratch dir, so the 1A
# acceptance test never touches the live registry.
PROPOSALS_DIR = os.environ.get(
    "IRONWILD_PROPOSALS_DIR", os.path.join("runs", "proposals"))
REGISTRY_PATH = os.path.join(PROPOSALS_DIR, "registry.json")

FORK_VERSION_RE = re.compile(r"^ForkA-vFINAL(\.\d+)?$")


def content_hash(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def proposal_id(turn, content):
    return "prop-%d-%s" % (turn, content_hash(content)[:8])


def validate_fork_a(parsed):
    """Fork A identifier check (intake only). Returns findings; an
    error finding blocks intake, a proposal with one is rejected."""
    findings = []
    if parsed.get("universe") != "Ironwild":
        findings.append({
            "level": "error", "code": "NOT_FORK_A",
            "message": "Universe is %r, not Ironwild; only Fork A "
                       "proposals enter this pipeline."
                       % (parsed.get("universe") or "",)})
    version = parsed.get("state_version") or ""
    if not FORK_VERSION_RE.match(version):
        findings.append({
            "level": "error", "code": "NOT_FORK_A",
            "message": "State-Version %r is not a Fork A version "
                       "(ForkA-vFINAL or ForkA-vFINAL.<k>); a live-canon "
                       "or other-fork block never enters Fork A."
                       % version})
    return findings


def load_registry():
    if not os.path.exists(REGISTRY_PATH):
        return {}
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_registry(registry):
    os.makedirs(PROPOSALS_DIR, exist_ok=True)
    tmp = REGISTRY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, sort_keys=True)
    os.replace(tmp, REGISTRY_PATH)


def _proposal_dir(pid):
    return os.path.join(PROPOSALS_DIR, pid)


def intake_file(drive_file_id, name, content, conn):
    """Register + validate one inbox file. Returns the registry entry.

    Writes runs/proposals/<id>/proposal.txt + review.json and updates
    the registry. Never writes the DB. A file already in the registry
    with the same hash is returned unchanged (idempotent poll); a
    changed file is a new proposal revision with a new ID.
    """
    try:
        parsed = sweep_mod.parse_state_block(content)
    except sweep_mod.SweepError as exc:
        entry = {
            "proposal_id": "prop-unknown-%s"
                           % content_hash(content)[:8],
            "drive_file_id": drive_file_id, "drive_file_name": name,
            "content_hash": content_hash(content),
            "turn": None, "state_version": None,
            "status": "rejected", "error": str(exc),
        }
        _record(entry, content, review=None)
        return entry
    pid = proposal_id(parsed["turn"], content)
    registry = load_registry()
    existing = registry.get(pid)
    if existing and existing.get("content_hash") == content_hash(content):
        return existing
    findings = sweep_mod.validate(parsed, conn) + validate_fork_a(parsed)
    try:
        changes = sweep_mod.diff(parsed, conn)
    except sweep_mod.SweepError as exc:
        findings.append({"level": "error", "code": "DIFF_REFUSED",
                         "message": str(exc)})
        changes = []
    review = sweep_mod.summarize(parsed, findings, changes, conn=conn)
    errors = [f for f in findings if f["level"] == "error"]
    entry = {
        "proposal_id": pid,
        "drive_file_id": drive_file_id, "drive_file_name": name,
        "content_hash": content_hash(content),
        "turn": parsed["turn"], "state_version": parsed["state_version"],
        "status": "rejected" if errors else "reviewed",
        "findings": findings, "changes": changes,
        "review": review,
    }
    _record(entry, content, review=review)
    return entry


def _record(entry, content, review):
    out_dir = _proposal_dir(entry["proposal_id"])
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "proposal.txt"), "w",
              encoding="utf-8") as f:
        f.write(content)
    if review is not None:
        with open(os.path.join(out_dir, "review.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"proposal_id": entry["proposal_id"],
                       "turn": entry["turn"],
                       "state_version": entry["state_version"],
                       "findings": entry["findings"],
                       "changes": entry["changes"],
                       "review": review},
                      f, indent=2, sort_keys=True)
    registry = load_registry()
    registry[entry["proposal_id"]] = entry
    save_registry(registry)


def intake_folder(folder_id, conn, downloads_dir=None):
    """Poll the inbox: intake every file not yet registered with its
    current hash. Returns (new_entries, skipped_count)."""
    downloads_dir = downloads_dir or os.path.join(
        PROPOSALS_DIR, ".downloads")
    registry = load_registry()
    new_entries, skipped = [], 0
    for f in drive_io.list_folder(folder_id):
        if f["mimeType"] == "application/vnd.google-apps.folder":
            continue
        dest = os.path.join(downloads_dir, f["id"])
        content = drive_io.download_text(f["id"], dest)
        h = content_hash(content)
        known = [e for e in registry.values()
                 if e.get("drive_file_id") == f["id"]
                 and e.get("content_hash") == h]
        if known:
            entry = known[0]
            if entry.get("status") == "held":
                # The file was restored to the reviewed content after
                # a tamper hold: the hash IS the binding, and it
                # matches again, so the proposal is reviewable again.
                # The hold stays on the record as history.
                entry["status"] = "reviewed"
                entry["restored_after_hold"] = True
                save_registry(registry)
                new_entries.append(entry)
                continue
            skipped += 1
            continue
        new_entries.append(intake_file(f["id"], f["name"], content, conn))
    return new_entries, skipped


def apply_proposal(pid, conn, approved_by, flag_path=None,
                   resource_changes=None, downloads_dir=None):
    """Apply a reviewed proposal by ID, with approval binding.

    Verifies, before touching the DB: the registry entry exists and
    is `reviewed`; the approver is Bryan; the Drive file's current
    content still hashes to the reviewed content (re-downloaded).
    Then runs apply_sweep in one transaction on the STORED (reviewed)
    content, and records the approval binding in the applied record.
    Raises sweep_mod.SweepError on any refusal — nothing is applied.
    Returns the apply_sweep result plus the binding.
    """
    registry = load_registry()
    entry = registry.get(pid)
    if entry is None:
        raise sweep_mod.SweepError(
            "unknown proposal %s: no such proposal in the registry" % pid)
    if entry["status"] != "reviewed":
        raise sweep_mod.SweepError(
            "proposal %s is %s, not reviewed; only a reviewed proposal "
            "can be applied" % (pid, entry["status"]))
    if approved_by != "Bryan":
        raise sweep_mod.SweepError(
            "proposal applies need Bryan's approval; got %r"
            % (approved_by or "",))
    downloads_dir = downloads_dir or os.path.join(
        PROPOSALS_DIR, ".downloads")
    dest = os.path.join(downloads_dir, entry["drive_file_id"])
    current = drive_io.download_text(entry["drive_file_id"], dest)
    if content_hash(current) != entry["content_hash"]:
        entry["status"] = "held"
        entry["error"] = ("Drive file changed since review (hash "
                          "mismatch); approval binds to the reviewed "
                          "revision only.")
        save_registry(registry)
        raise sweep_mod.SweepError(entry["error"])
    with open(os.path.join(_proposal_dir(pid), "proposal.txt"),
              encoding="utf-8") as f:
        stored = f.read()
    if content_hash(stored) != entry["content_hash"]:
        raise sweep_mod.SweepError(
            "stored proposal %s does not match its recorded hash; "
            "refusing to apply" % pid)
    parsed = sweep_mod.parse_state_block(stored)
    result = sweep_mod.apply_sweep(
        parsed, conn, approved_by, flag_path=flag_path,
        resource_changes=resource_changes)
    import datetime
    result["proposal_binding"] = {
        "proposal_id": pid,
        "drive_file_id": entry["drive_file_id"],
        "content_hash": entry["content_hash"],
        "approved_by": approved_by,
        "applied_at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
    }
    entry["status"] = "applied"
    entry["applied_at"] = result["proposal_binding"]["applied_at"]
    save_registry(registry)
    out_dir = _proposal_dir(pid)
    with open(os.path.join(out_dir, "applied.json"), "w",
              encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
    return result
