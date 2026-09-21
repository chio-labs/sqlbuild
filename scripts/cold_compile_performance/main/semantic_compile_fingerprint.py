"""Fingerprint fresh-process semantic compile output."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import orjson


def semantic_compile_fingerprint(*, payload: dict[str, object], compiled_dir: Path) -> str:
    """Hash deterministic semantic output and every compiled artifact."""

    semantic_payload: dict[str, object] = dict(payload)
    semantic_payload.pop("compile_timings", None)
    semantic_payload.pop("version", None)
    fingerprint: Any = hashlib.sha256(orjson.dumps(semantic_payload, option=orjson.OPT_SORT_KEYS))
    for artifact_path in sorted(path for path in compiled_dir.rglob("*") if path.is_file()):
        fingerprint.update(str(artifact_path.relative_to(compiled_dir)).encode("utf-8"))
        fingerprint.update(b"\0")
        fingerprint.update(artifact_path.read_bytes())
        fingerprint.update(b"\0")
    return str(fingerprint.hexdigest())
