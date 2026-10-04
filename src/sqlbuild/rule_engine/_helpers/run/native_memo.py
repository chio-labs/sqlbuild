"""Reuse the complete built-in rules response for an identical native request."""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path
from typing import Any

import orjson

from sqlbuild.compiler.fact_cache.main.code_identity import compiled_code_identity
from sqlbuild.rule_engine.constants import NATIVE_RULES_MEMO_FILE, NATIVE_RULES_MEMO_VERSION


def native_payload_digests(payloads: list[bytes]) -> list[str]:
    """Digest each exact encoded model payload; the digest keys that model's cached findings."""

    return [hashlib.blake2b(payload, digest_size=32).hexdigest() for payload in payloads]


def native_request_identity(*, request_json: bytes, model_digests: list[str]) -> str:
    """Digest the model-free request plus ordered digests of each exact model payload."""

    digest: Any = hashlib.blake2b(digest_size=32)
    digest.update(NATIVE_RULES_MEMO_VERSION.encode())
    digest.update(b"\0")
    digest.update(compiled_code_identity().encode())
    digest.update(b"\0")
    digest.update(request_json)
    digest.update(b"\0")
    digest.update(len(model_digests).to_bytes(8, "little"))
    digest.update("\0".join(model_digests).encode())
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
