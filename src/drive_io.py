"""Google Drive I/O for the Stage 1 proposal pipeline.

Thin wrapper over the Drive CLI (`hatch_gws_cli drive ...`) — the
only Drive surface available. No webhook or push exists there, so
the 1A intake polls the inbox folder (see stage-1-plan.md section 4).

Every function raises DriveError on failure; callers record the
failure and halt safely without advancing state.
"""

import json
import os
import subprocess

CLI = "/opt/hatch/bin/hatch_gws_cli"


class DriveError(Exception):
    """A Drive operation failed (auth, network, missing file, ...)."""


def _run(argv, check=True):
    try:
        out = subprocess.run(argv, capture_output=True, text=True,
                             timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise DriveError("Drive CLI failed to run: %s" % exc)
    if check and out.returncode != 0:
        raise DriveError("Drive CLI %s failed (%d): %s"
                         % (" ".join(argv[2:4]), out.returncode,
                            (out.stderr or out.stdout).strip()[:300]))
    return out


def _parse(out):
    try:
        return json.loads(out.stdout)
    except ValueError:
        raise DriveError("Drive CLI returned non-JSON output: %r"
                         % out.stdout[:300])


def list_folder(folder_id, page_size=50):
    """Files directly in a folder (not trashed): [{id, name, mimeType,
    modifiedTime}]."""
    params = json.dumps({
        "q": "'%s' in parents and trashed=false" % folder_id,
        "pageSize": page_size,
        "fields": "files(id,name,mimeType,modifiedTime)",
    })
    out = _run([CLI, "drive", "files", "list", "--params", params])
    return _parse(out).get("files", [])


def download_text(file_id, dest_path):
    """Download a stored (non-Google-native) file's bytes as text.

    The CLI writes to a path; the caller chooses a durable path under
    the workspace (never /tmp — restarts wipe it). Returns the text.
    """
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    _run([CLI, "drive", "files", "get",
          "--params", json.dumps({"fileId": file_id, "alt": "media"}),
          "--output", dest_path])
    with open(dest_path, encoding="utf-8") as f:
        return f.read()


def upload_text(folder_id, name, content, local_path):
    """Upload text content as a new file in a folder. Returns the
    Drive file id."""
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, "w", encoding="utf-8") as f:
        f.write(content)
    out = _run([CLI, "drive", "+upload", local_path,
                "--parent", folder_id, "--name", name])
    data = _parse(out)
    return data.get("id")


def create_folder(name, parent_id):
    """Create a folder under a parent. Returns the folder id."""
    out = _run([CLI, "drive", "files", "create",
                "--params", json.dumps({"ignoreDefaultVisibility": True}),
                "--json", json.dumps({
                    "name": name,
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": [parent_id]})])
    return _parse(out).get("id")
