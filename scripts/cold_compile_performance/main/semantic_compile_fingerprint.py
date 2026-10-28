"""Fingerprint fresh-process semantic compile output."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import orjson

from scripts.cold_compile_performance.constants import FAILED_COMPILED_DIRECTORY


def semantic_compile_fingerprint(*, payload: dict[str, object], compiled_dir: Path) -> str:
    """Hash deterministic semantic output and every compiled and failed-compile artifact."""

    semantic_payload: dict[str, object] = dict(payload)
    semantic_payload.pop("compile_timings", None)
    semantic_payload.pop("compiler_engine", None)
    semantic_payload.pop("version", None)
    fingerprint: Any = hashlib.sha256(orjson.dumps(semantic_payload, option=orjson.OPT_SORT_KEYS))
    fingerprint.update(_tree_bytes(root=compiled_dir, relative_to=compiled_dir))
    fingerprint.update(
        _tree_bytes(
            root=compiled_dir.with_name(FAILED_COMPILED_DIRECTORY), relative_to=compiled_dir.parent
        )
    )
    return str(fingerprint.hexdigest())


def _tree_bytes(*, root: Path, relative_to: Path) -> bytes:
    parts: list[bytes] = []
    for artifact_path in sorted(path for path in root.rglob("*") if path.is_file()):
        parts.extend(
            (
                str(artifact_path.relative_to(relative_to)).encode("utf-8"),
                b"\0",
                artifact_path.read_bytes(),
                b"\0",
            )
        )
    return b"".join(parts)
