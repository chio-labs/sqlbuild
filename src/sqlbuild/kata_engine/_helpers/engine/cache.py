"""Persistent per-model kata result cache."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.kata_engine.constants import TARGET_DIRECTORY_NAME
from sqlbuild.kata_engine.models import KataFault, ResolvedRuleset

_CACHE_SCHEMA: int = 1
_CACHE_PATH: Path = Path("target") / "kata-cache.json"


def load_cache(*, project_dir: Path) -> dict[str, dict[str, object]]:
    """Load valid cached model entries, treating malformed state as a cold cache."""

    path: Path = project_dir / _CACHE_PATH
    if not path.is_file():
        return {}
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("schema") != _CACHE_SCHEMA:
        return {}
    entries: object = payload.get("entries")
    if not isinstance(entries, dict):
        return {}
    return {
        str(key): value
        for key, value in entries.items()
        if isinstance(key, str) and isinstance(value, dict)
    }


def save_cache(*, project_dir: Path, entries: dict[str, dict[str, object]]) -> None:
    """Atomically persist cache entries."""

    path: Path = project_dir / _CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"schema": _CACHE_SCHEMA, "entries": entries}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def model_fingerprint(
    *,
    model: CompiledModel,
    project: CompiledProject,
    ruleset: ResolvedRuleset,
    project_dir: Path,
) -> str:
    """Fingerprint model-local inputs plus global inputs required by active rules."""

    payload: dict[str, object] = {
        "ruleset": ruleset.fingerprint,
        "path": model.relative_path.as_posix(),
        "query": model.query_sql,
        "authored_sql": model.authored_sql,
        "config": model.config.values,
        "references": [
            (str(reference.ref_kind), reference.ref_name, reference.ref_package)
            for reference in model.references
        ],
        "columns": [
            (column.name, column.type, column.nullable)
            for column in (() if model.schema_entry is None else model.schema_entry.columns)
        ],
        "schema_entry": model.schema_entry,
        "enum_declarations": model.enum_declarations,
        "constant_declarations": model.constant_declarations,
        "enum_columns": model.enum_columns,
    }
    needs_project: bool = any(
        rule.project_wide or rule.code.startswith("KTX") for rule in ruleset.rules
    ) or any(rule.custom for rule in ruleset.rules)
    if needs_project:
        payload["project"] = _project_fingerprint(project=project, project_dir=project_dir)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def decode_faults(*, entry: dict[str, object], expected_fingerprint: str) -> list[KataFault] | None:
    """Decode one matching cache entry."""

    if entry.get("fingerprint") != expected_fingerprint:
        return None
    raw_faults: object = entry.get("faults")
    if not isinstance(raw_faults, list):
        return None
    faults: list[KataFault] = []
    for raw_fault in raw_faults:
        if not isinstance(raw_fault, dict):
            return None
        fault_mapping: dict[str, object] = cast(dict[str, object], raw_fault)
        try:
            faults.append(
                KataFault(
                    code=str(fault_mapping["code"]),
                    path=Path(str(fault_mapping["path"])),
                    line=int(str(fault_mapping["line"])),
                    column=int(str(fault_mapping["column"])),
                    message=str(fault_mapping["message"]),
                    remediation=str(fault_mapping["remediation"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            return None
    return faults


def encode_entry(*, fingerprint: str, faults: list[KataFault]) -> dict[str, object]:
    """Encode one model's unsuppressed rule results."""

    return {
        "fingerprint": fingerprint,
        "faults": [
            {
                "code": fault.code,
                "path": fault.path.as_posix(),
                "line": fault.line,
                "column": fault.column,
                "message": fault.message,
                "remediation": fault.remediation,
            }
            for fault in faults
        ],
    }


def _project_fingerprint(*, project: CompiledProject, project_dir: Path) -> str:
    digest: Any = hashlib.sha256()
    suffixes: frozenset[str] = frozenset({".py", ".sql", ".toml", ".yaml", ".yml"})
    for path in sorted(project_dir.rglob("*")):
        if not path.is_file() or path.suffix not in suffixes or TARGET_DIRECTORY_NAME in path.parts:
            continue
        digest.update(path.relative_to(project_dir).as_posix().encode())
        digest.update(path.read_bytes())
    digest.update(str(tuple(project.public_enums)).encode())
    digest.update(str(tuple(project.public_constants)).encode())
    return digest.hexdigest()
