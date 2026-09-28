"""Bounded subprocess host for repository-defined Rules."""

from __future__ import annotations

import contextlib
import io
import json
import os
import pickle
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.rule_engine._helpers.engine.catalogue import build_catalogue
from sqlbuild.rule_engine._helpers.host.custom_evaluation import evaluate_custom_rules
from sqlbuild.rule_engine.classes.runtime_guard import RuntimeGuard
from sqlbuild.rule_engine.constants import (
    CUSTOM_HOST_HASH_SEED,
    CUSTOM_HOST_INPUT_TUPLE_SIZE,
    CUSTOM_HOST_LAUNCH_MODULE,
    CUSTOM_HOST_PROTOCOL_VERSION,
    CUSTOM_HOST_RUNTIME_VERSION,
)
from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.rule_engine.models import Finding, Rule, RulesConfig


def main() -> int:
    """Read one Fensu host request and write exactly one response."""

    if sys.flags.hash_randomization:
        return _write_error(
            f"custom host must be started by {CUSTOM_HOST_LAUNCH_MODULE} "
            f"with PYTHONHASHSEED={CUSTOM_HOST_HASH_SEED}"
        )
    request: object = json.load(sys.stdin)
    if not isinstance(request, dict):
        return _write_error("custom host request must be an object")
    protocol: object = request.get("protocol")
    runtime_version: object = request.get("runtime_version")
    if protocol != CUSTOM_HOST_PROTOCOL_VERSION or runtime_version != CUSTOM_HOST_RUNTIME_VERSION:
        return _write_error("unsupported custom host protocol or runtime")
    guard: RuntimeGuard | None = None
    try:
        payload: object = request["payload"]
        if not isinstance(payload, dict):
            raise RulesError("custom host payload must be an object")
        project, config = _decode_inputs(payload)
        project_dir: Path = Path(str(payload["project_dir"])).resolve()
        dialect: str = str(payload.get("dialect", "generic"))
        verify_determinism: bool = payload.get("verify_determinism") is True
        selected_codes: tuple[str, ...] = tuple(str(code) for code in payload["selected_codes"])
        raw_model_paths: object = payload.get("selected_model_paths")
        selected_model_paths: frozenset[str] | None = (
            frozenset(str(path) for path in raw_model_paths)
            if isinstance(raw_model_paths, list)
            else None
        )
        os.environ.clear()
        os.chdir(project_dir)
        guard = RuntimeGuard(project_dir=project_dir)
        sys.addaudithook(guard)
        guard.guard_filesystem_metadata()
        messages: io.StringIO = io.StringIO()
        with contextlib.redirect_stdout(messages):
            catalogue: tuple[Rule, ...] = build_catalogue(config=config, project_dir=project_dir)
            guard.raise_violation()
            by_code: dict[str, Rule] = {rule.code: rule for rule in catalogue}
            selected: tuple[Rule, ...] = tuple(by_code[code] for code in selected_codes)
            findings: list[Finding] = evaluate_custom_rules(
                project=project,
                config=config,
                project_dir=project_dir,
                selected_rules=selected,
                dialect=dialect,
                selected_model_paths=selected_model_paths,
                verify_determinism=verify_determinism,
                guard=guard,
            )
    except Exception as error:
        violation: Exception | None = None if guard is None else guard.violation
        return _write_error(str(violation or error))
    response: dict[str, object] = {
        "protocol": CUSTOM_HOST_PROTOCOL_VERSION,
        "runtime_version": CUSTOM_HOST_RUNTIME_VERSION,
        "error": None,
        "payload": [_finding_payload(finding) for finding in findings],
        "messages": messages.getvalue().splitlines(),
    }
    sys.stdout.write(json.dumps(response, sort_keys=True))
    return 0


def _decode_inputs(payload: dict[str, Any]) -> tuple[CompiledProject, RulesConfig]:
    project_dir: Path = Path(str(payload["project_dir"])).resolve()
    input_root: Path = (project_dir / "target" / "rules-cache" / "host-inputs").resolve()
    input_path: Path = Path(str(payload["project_pickle_path"]))
    if (
        not input_path.is_absolute()
        or input_path.is_symlink()
        or not input_path.resolve().is_relative_to(input_root)
    ):
        raise RulesError("custom host project payload path is invalid")
    with input_path.open("rb") as handle:
        decoded: object = pickle.load(handle)
    if (
        not isinstance(decoded, tuple)
        or len(decoded) != CUSTOM_HOST_INPUT_TUPLE_SIZE
        or not isinstance(decoded[0], CompiledProject)
        or not isinstance(decoded[1], RulesConfig)
    ):
        raise RulesError("custom host project payload has invalid types")
    return decoded


def _finding_payload(finding: Finding) -> dict[str, object]:
    payload: dict[str, object] = asdict(finding)
    payload.pop("affected_rules", None)
    payload["path"] = finding.path.as_posix()
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
