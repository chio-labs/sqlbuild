"""Bounded subprocess host for repository-defined Kata rules."""

from __future__ import annotations

import base64
import contextlib
import io
import json
import pickle
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.kata_engine._helpers.engine.catalogue import build_catalogue
from sqlbuild.kata_engine._helpers.engine.custom_evaluation import evaluate_custom_rules
from sqlbuild.kata_engine.constants import (
    CUSTOM_HOST_INPUT_TUPLE_SIZE,
    CUSTOM_HOST_PROTOCOL_VERSION,
    CUSTOM_HOST_RUNTIME_VERSION,
)
from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.kata_engine.models import KataConfig, KataFault, KataRule


def main() -> int:
    """Read one Fensu host request and write exactly one response."""

    request: object = json.load(sys.stdin)
    if not isinstance(request, dict):
        return _write_error("custom host request must be an object")
    protocol: object = request.get("protocol")
    runtime_version: object = request.get("runtime_version")
    if protocol != CUSTOM_HOST_PROTOCOL_VERSION or runtime_version != CUSTOM_HOST_RUNTIME_VERSION:
        return _write_error("unsupported custom host protocol or runtime")
    try:
        payload: object = request["payload"]
        if not isinstance(payload, dict):
            raise KataError("custom host payload must be an object")
        project, config = _decode_inputs(payload)
        project_dir: Path = Path(str(payload["project_dir"])).resolve()
        selected_codes: tuple[str, ...] = tuple(str(code) for code in payload["selected_codes"])
        messages: io.StringIO = io.StringIO()
        with contextlib.redirect_stdout(messages):
            catalogue: tuple[KataRule, ...] = build_catalogue(
                config=config, project_dir=project_dir
            )
            by_code: dict[str, KataRule] = {rule.code: rule for rule in catalogue}
            selected: tuple[KataRule, ...] = tuple(by_code[code] for code in selected_codes)
            faults: list[KataFault] = evaluate_custom_rules(
                project=project,
                config=config,
                project_dir=project_dir,
                selected_rules=selected,
            )
    except Exception as error:
        return _write_error(str(error))
    response: dict[str, object] = {
        "protocol": CUSTOM_HOST_PROTOCOL_VERSION,
        "runtime_version": CUSTOM_HOST_RUNTIME_VERSION,
        "error": None,
        "payload": [_fault_payload(fault) for fault in faults],
        "messages": messages.getvalue().splitlines(),
    }
    sys.stdout.write(json.dumps(response, sort_keys=True))
    return 0


def _decode_inputs(payload: dict[str, Any]) -> tuple[CompiledProject, KataConfig]:
    encoded: str = str(payload["project_pickle"])
    decoded: object = pickle.loads(base64.b64decode(encoded, validate=True))
    if (
        not isinstance(decoded, tuple)
        or len(decoded) != CUSTOM_HOST_INPUT_TUPLE_SIZE
        or not isinstance(decoded[0], CompiledProject)
        or not isinstance(decoded[1], KataConfig)
    ):
        raise KataError("custom host project payload has invalid types")
    return decoded


def _fault_payload(fault: KataFault) -> dict[str, object]:
    payload: dict[str, object] = asdict(fault)
    payload["path"] = fault.path.as_posix()
    return payload


def _write_error(message: str) -> int:
    response: dict[str, object] = {
        "protocol": CUSTOM_HOST_PROTOCOL_VERSION,
        "runtime_version": CUSTOM_HOST_RUNTIME_VERSION,
        "error": message or "custom host failed",
        "payload": None,
        "messages": [],
    }
    sys.stdout.write(json.dumps(response, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
