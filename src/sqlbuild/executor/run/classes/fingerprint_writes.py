"""The fingerprint tables and recorded identities one build writes through."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild._native import AUDIT_GATE_METADATA_KEY, Fingerprint
from sqlbuild.executor.run.types import FingerprintTableLocation

_AUDIT_GATE_RUN_KEY: str = "run_id"


class FingerprintWrites:
    """Set up each fingerprint table once per build and skip rows identical to the latest one."""

    def __init__(self, *, skips_identical: bool = True) -> None:
        """Skip identical rows unless the build applies migrations, which rename matching needs."""

        self._skips_identical: bool = skips_identical
        self._lock: threading.Lock = threading.Lock()
        self._ready: set[FingerprintTableLocation] = set()
        self._recreated: set[FingerprintTableLocation] = set()
        self._setup_locks: dict[FingerprintTableLocation, threading.Lock] = {}

    def records(
        self,
        *,
        location: FingerprintTableLocation,
        previous: Fingerprint | None,
        current: Fingerprint,
    ) -> bool:
        """Whether ``current`` must be appended: the latest row differs, or the table was lost."""

        with self._lock:
            if location in self._recreated:
                return True
        return (
            not self._skips_identical
            or previous is None
            or _identity(previous) != _identity(current)
        )

    @contextmanager
    def setting_up(self, *, location: FingerprintTableLocation) -> Iterator[bool]:
        """Yield whether to set up the table; writers wait while another sets it up."""

        with self._lock:
            ready: bool = location in self._ready
            setup_lock: threading.Lock = self._setup_locks.setdefault(location, threading.Lock())
        if ready:
            yield False
            return
        with setup_lock:
            with self._lock:
                requested: bool = location not in self._ready
            yield requested

    def written(
        self, *, location: FingerprintTableLocation, requested_setup: bool, set_up: bool
    ) -> None:
        """Note a write; a table set up only because its insert failed was lost mid-run."""

        with self._lock:
            if set_up and not requested_setup:
                self._recreated.add(location)
            self._ready.add(location)


def _identity(fingerprint: Fingerprint) -> tuple[object, ...]:
    """Everything a fingerprint row records except when and by which run it was written."""

    return (
        fingerprint.node_type,
        fingerprint.node_name,
        fingerprint.target_database,
        fingerprint.target_schema,
        fingerprint.target_name,
        fingerprint.definition_hash,
        fingerprint.version_hash,
        fingerprint.schema_fingerprint,
        fingerprint.definition,
        _metadata_identity(fingerprint.metadata_json),
    )


def _metadata_identity(metadata_json: str) -> object:
    """Metadata without the audit gate's run reference; unparseable metadata compares as text."""

    try:
        metadata: object = json.loads(metadata_json)
    except json.JSONDecodeError:
        return metadata_json
    if isinstance(metadata, dict):
        gate: object = metadata.get(AUDIT_GATE_METADATA_KEY)
        if isinstance(gate, dict):
            metadata = {
                **metadata,
                AUDIT_GATE_METADATA_KEY: {
                    key: value for key, value in gate.items() if key != _AUDIT_GATE_RUN_KEY
                },
            }
    return json.dumps(metadata, sort_keys=True)
