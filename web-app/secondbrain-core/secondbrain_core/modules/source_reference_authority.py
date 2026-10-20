"""Fail-closed adapters for exact, Core-owned Daily Brief source references.

Only project documents currently have a canonical ID-to-record mapping and a
version defined as SHA-256 of the exact authoritative JSON bytes. Other kinds
remain unsupported until their stores publish equivalent stable IDs/versions.
"""


class SourceReferenceAuthority:
    """Verify a brief reference against one bounded Projects snapshot."""

    _UNSUPPORTED = {"task", "note", "capture", "review", "journal"}

    def __init__(self, projects_store, permission_check=None):
        self.projects_store = projects_store
        self.permission_check = permission_check
        self._snapshot = None

    def verify(self, reference):
        kind = reference.get("kind") if isinstance(reference, dict) else None
        if kind in self._UNSUPPORTED:
            return "unsupported"
        if kind != "project" or self.projects_store is None:
            return "unsupported"
        if self.permission_check is not None:
            try:
                self.permission_check()
            except Exception:
                # Do not disclose whether the referenced project exists.
                return "forbidden"
        if self._snapshot is None:
            try:
                self._snapshot = self.projects_store.read_snapshot()
            except Exception:
                return "unavailable"
        snapshot = self._snapshot
        if not snapshot.configured:
            return "unavailable"
        if not snapshot.available or not snapshot.complete:
            # Incomplete enumeration cannot prove absence or uniqueness.
            return "unavailable"
        matches = [row for row in snapshot.documents if row.project_id == reference["id"]]
        if not matches:
            return "missing"
        if len(matches) != 1:
            return "unavailable"
        return "verified" if matches[0].sha256 == reference["version"] else "stale"
