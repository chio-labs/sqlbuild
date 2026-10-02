"""Reuse the complete built-in rules response for a byte-identical native request."""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path
from typing import Any

import orjson

from sqlbuild.compiler.fact_cache.main.code_identity import compiled_code_identity
from sqlbuild.rule_engine.constants import NATIVE_RULES_MEMO_FILE, NATIVE_RULES_MEMO_VERSION


def native_request_identity(request_json: bytes) -> str:
    """Digest one serialized native request together with the installed code identity."""

    digest: Any = hashlib.sha256()
    digest.update(NATIVE_RULES_MEMO_VERSION.encode())
    digest.update(b"\0")
    digest.update(compiled_code_identity().encode())
    digest.update(b"\0")
    digest.update(request_json)
    return digest.hexdigest()


def read_native_response(*, project_dir: Path, identity: str) -> str | None:
    """Return the stored response for this exact request identity, if any."""

    try:
        payload: object = orjson.loads((project_dir / NATIVE_RULES_MEMO_FILE).read_bytes())
    except (OSError, orjson.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("identity") != identity:
        return None
    response: object = payload.get("response")
    return response if isinstance(response, str) else None


def write_native_response(*, project_dir: Path, identity: str, response: str) -> None:
    """Atomically replace the stored response with the latest evaluated request."""

    path: Path = project_dir / NATIVE_RULES_MEMO_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path = path.with_suffix(f".tmp-{os.getpid()}-{threading.get_ident()}")
    temporary.write_bytes(orjson.dumps({"identity": identity, "response": response}))
    temporary.replace(path)
