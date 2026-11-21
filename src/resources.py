"""Resource helpers. Quantities never go below zero."""

def get_qty(conn, holder_id, holder_kind, resource):
    row = conn.execute(
        "SELECT qty FROM resources WHERE holder_id = ? AND holder_kind = ? "
        "AND resource = ?",
        (holder_id, holder_kind, resource),
    ).fetchone()
    return row["qty"] if row else 0


def add_qty(conn, holder_id, holder_kind, resource, qty):
    """Add qty (may be negative). Clamps at zero. Returns the qty actually applied."""
    current = get_qty(conn, holder_id, holder_kind, resource)
    new = current + qty
    if new < 0:
        applied = -current
        new = 0
    else:
        applied = qty
    conn.execute(
        "INSERT INTO resources (holder_id, holder_kind, resource, qty) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(holder_id, holder_kind, resource) "
        "DO UPDATE SET qty = excluded.qty",
        (holder_id, holder_kind, resource, new),
    )
    return applied


def move_qty(conn, from_id, from_kind, to_id, to_kind, resource, qty):
    """Move up to qty from one holder to another. Returns qty actually moved."""
    available = get_qty(conn, from_id, from_kind, resource)
    moved = min(qty, available)
    if moved > 0:
        add_qty(conn, from_id, from_kind, resource, -moved)
        add_qty(conn, to_id, to_kind, resource, moved)
    return moved
