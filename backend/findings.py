from sqlite3 import Connection
from uuid import UUID

from .contracts import Finding, Resolution


def update_resolution(db: Connection, finding_id: UUID, resolution: Resolution) -> Finding | None:
    # Setting the state is idempotent. Only this finding changes; no source code
    # or review execution state is modified. Across clients, the last write wins.
    rows = db.execute(
        "UPDATE findings SET resolution = ? WHERE id = ? RETURNING *",
        (resolution.value, str(finding_id)),
    ).fetchall()
    return Finding.model_validate(dict(rows[0])) if rows else None
