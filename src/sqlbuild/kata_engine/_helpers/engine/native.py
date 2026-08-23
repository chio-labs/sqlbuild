"""Typed Python adapter for the private native kata engine."""

from __future__ import annotations

import base64
import hashlib
import inspect
import json
import pickle
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import sqlbuild._kata_native as _kata_native
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import ConstantDeclaration, EnumDeclaration
from sqlbuild.kata_engine.constants import (
    CUSTOM_HOST_RUNTIME_VERSION,
    EVALUATE_RULE_CALL,
    KATA_NATIVE_API_VERSION,
)
from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.kata_engine.models import (
    KataConfig,
    KataFault,
    KataResult,
    KataRule,
)


def evaluate_native(
    *,
    project: CompiledProject,
    config: KataConfig,
    project_dir: Path,
    catalogue: tuple[KataRule, ...],
) -> KataResult:
    """Evaluate one compiled model batch through the native engine."""

    request: dict[str, object] = {
        "version": KATA_NATIVE_API_VERSION,
        "project_dir": str(project_dir.resolve()),
        "config": _config_payload(config),
        "models": _model_payloads(project),
        "public_enums": [
            _enum_payload(declaration) for declaration in project.public_enums.values()
        ],
        "public_constants": [
            _constant_payload(declaration) for declaration in project.public_constants.values()
        ],
        "custom_rules": [
            _custom_rule_payload(rule=rule, project_dir=project_dir)
            for rule in catalogue
            if rule.custom
        ],
        "custom_host": _custom_host_payload(
            project=project,
            config=config,
            project_dir=project_dir,
            catalogue=catalogue,
        ),
    }
    try:
        response: object = json.loads(
            _kata_native.evaluate_json(json.dumps(request, sort_keys=True, default=str))
        )
    except (ValueError, TypeError) as error:
        raise KataError(str(error)) from error
    if not isinstance(response, dict):
        raise KataError("native kata engine returned an invalid response")
    payload: dict[str, Any] = response
    if payload.get("version") != KATA_NATIVE_API_VERSION:
        raise KataError("native kata engine returned an unsupported response version")
    raw_faults: object = payload.get("faults")
    if not isinstance(raw_faults, list):
        raise KataError("native kata engine returned invalid faults")
    return KataResult(
        faults=tuple(_decode_fault(value) for value in raw_faults),
        evaluated_models=int(payload.get("evaluated_models", 0)),
        cache_hits=int(payload.get("cache_hits", 0)),
        cache_misses=int(payload.get("cache_misses", 0)),
    )


def load_native_config(project_dir: Path) -> dict[str, object]:
    """Load strict kata TOML through the native configuration owner."""

    try:
        payload: object = json.loads(_kata_native.load_config_json(str(project_dir.resolve())))
    except (ValueError, TypeError) as error:
        raise KataError(str(error)) from error
    if not isinstance(payload, dict):
        raise KataError("native kata engine returned invalid configuration")
    return {str(key): value for key, value in payload.items()}


def native_catalogue() -> tuple[dict[str, object], ...]:
    """Return native-owned built-in rule metadata."""

    try:
        payload: object = json.loads(_kata_native.catalogue_json())
    except (ValueError, TypeError) as error:
        raise KataError(str(error)) from error
    if not isinstance(payload, dict) or not isinstance(payload.get("rules"), list):
        raise KataError("native kata engine returned an invalid catalogue")
    rules: list[object] = payload["rules"]
    if any(not isinstance(value, dict) for value in rules):
        raise KataError("native kata engine returned invalid rule metadata")
    normalized: list[dict[str, object]] = []
    for value in rules:
        normalized.append({str(key): item for key, item in value.items()})
    return tuple(normalized)


def native_selected_codes(
    *, config: KataConfig, catalogue: tuple[KataRule, ...]
) -> tuple[str, ...]:
    """Resolve the active policy through the native Fensu adapter."""

    request: dict[str, object] = {
        "version": KATA_NATIVE_API_VERSION,
        "config": _config_payload(config),
        "custom_rules": [
            {
                "code": rule.code,
                "family": rule.family,
                "slug": rule.slug,
                "message": rule.message,
                "remediation": rule.remediation,
                "enabled_by_default": rule.enabled_by_default,
                "implementation_fingerprint": _rule_implementation_fingerprint(rule),
                "source": rule.source,
                "project_wide": rule.project_wide,
                "check_name": getattr(rule.check, "__name__", ""),
                "test_case_count": 0,
            }
            for rule in catalogue
            if rule.custom
        ],
    }
    try:
        payload: object = json.loads(
            _kata_native.selected_codes_json(json.dumps(request, sort_keys=True, default=str))
        )
    except (ValueError, TypeError) as error:
        raise KataError(str(error)) from error
    if not isinstance(payload, list) or any(not isinstance(code, str) for code in payload):
        raise KataError("native kata engine returned invalid selected rule codes")
    return tuple(payload)


def render_native_owned_skill(*, content: str, input_fingerprint: str) -> str:
    """Attach Fensu schema-v2 ownership to generated guidance."""

    try:
        return _kata_native.render_owned_skill(content, input_fingerprint)
    except (ValueError, TypeError) as error:
        raise KataError(str(error)) from error


def native_skill_freshness(*, content: str | None, input_fingerprint: str) -> str:
    """Classify generated guidance through the Fensu ownership contract."""

    return _kata_native.skill_freshness(content, input_fingerprint)


def _config_payload(config: KataConfig) -> dict[str, object]:
    return asdict(config)


def _model_payloads(project: CompiledProject) -> list[dict[str, object]]:
    audit_counts: dict[str, int] = {}
    for audit in project.audits:
        if audit.attached_target_name is not None:
            audit_counts[audit.attached_target_name] = (
                audit_counts.get(audit.attached_target_name, 0) + 1
            )
    test_counts: dict[str, int] = {}
    for test in project.sql_tests:
        names: frozenset[str] = frozenset(
            dependency.name
            for dependency in test.scope_deps
            if dependency.resource_type == CompiledResourceType.MODEL
        )
        for name in names:
            test_counts[name] = test_counts.get(name, 0) + 1
    return [
        _model_payload(
            model=model,
            compiled_audit_count=audit_counts.get(model.name, 0),
            targeting_test_count=test_counts.get(model.name, 0),
        )
        for model in project.models
    ]


def _model_payload(
    *, model: CompiledModel, compiled_audit_count: int, targeting_test_count: int
) -> dict[str, object]:
    schema_audit_count: int = 0
    columns: list[dict[str, object]] = []
    if model.schema_entry is not None:
        schema_audit_count = len(model.schema_entry.audits) + sum(
            len(column.audits) for column in model.schema_entry.columns
        )
        columns = [
            {
                "name": column.name,
                "type": column.type or "",
                "nullable": column.nullable,
                "audit_count": len(column.audits),
            }
            for column in model.schema_entry.columns
        ]
    return {
        "name": model.name,
        "relative_path": model.relative_path.as_posix(),
        "query_sql": model.query_sql,
        "authored_sql": model.authored_sql,
        "config": model.config.values,
        "references": [
            {
                "ref_kind": str(reference.ref_kind),
                "ref_name": reference.ref_name,
                "ref_package": reference.ref_package,
            }
            for reference in model.references
        ],
        "columns": columns,
        "enum_columns": list(model.enum_columns),
        "enum_declarations": [
            _enum_payload(declaration) for declaration in model.enum_declarations
        ],
        "constant_declarations": [
            _constant_payload(declaration) for declaration in model.constant_declarations
        ],
        "declared_audit_count": max(schema_audit_count, compiled_audit_count),
        "targeting_test_count": targeting_test_count,
    }


def _enum_payload(declaration: EnumDeclaration) -> dict[str, object]:
    return {
        "name": declaration.name,
        "relative_path": declaration.relative_path.as_posix(),
        "members": [{"name": member.name, "value": member.value} for member in declaration.members],
    }


def _constant_payload(declaration: ConstantDeclaration) -> dict[str, object]:
    return {
        "name": declaration.name,
        "relative_path": declaration.relative_path.as_posix(),
        "members": [],
    }


def _custom_rule_payload(*, rule: KataRule, project_dir: Path) -> dict[str, object]:
    source: str | None = rule.source
    if source is not None:
        source_path: Path = Path(source).resolve()
        root: Path = project_dir.resolve()
        if source_path.is_relative_to(root):
            source = source_path.relative_to(root).as_posix()
    check_name: str = getattr(rule.check, "__name__", "")
    return {
        "code": rule.code,
        "family": rule.family,
        "slug": rule.slug,
        "message": rule.message,
        "remediation": rule.remediation,
        "enabled_by_default": rule.enabled_by_default,
        "implementation_fingerprint": _rule_implementation_fingerprint(rule),
        "source": source,
        "project_wide": rule.project_wide,
        "check_name": check_name,
        "test_case_count": _custom_rule_test_case_count(
            project_dir=project_dir, check_name=check_name
        ),
    }


def _rule_implementation_fingerprint(rule: KataRule) -> str:
    digest: Any = hashlib.sha256(inspect.getsource(rule.check).encode())
    if rule.source is not None:
        digest.update(Path(rule.source).read_bytes())
    return digest.hexdigest()


def _custom_rule_test_case_count(*, project_dir: Path, check_name: str) -> int:
    count: int = 0
    for path in project_dir.glob("tests/**/*.py"):
        source: str = path.read_text(encoding="utf-8")
        if check_name in source and EVALUATE_RULE_CALL in source:
            count += source.count("RuleCase(")
    return count


def _custom_host_payload(
    *,
    project: CompiledProject,
    config: KataConfig,
    project_dir: Path,
    catalogue: tuple[KataRule, ...],
) -> dict[str, object] | None:
    if not any(rule.custom for rule in catalogue):
        return None
    encoded: str = base64.b64encode(pickle.dumps((project, config))).decode("ascii")
    return {
        "program": sys.executable,
        "arguments": ["-m", "sqlbuild.kata_engine._helpers.engine.custom_host"],
        "timeout_millis": 30_000,
        "runtime_version": CUSTOM_HOST_RUNTIME_VERSION,
        "payload": {
            "project_pickle": encoded,
            "project_dir": str(project_dir.resolve()),
        },
    }


def _decode_fault(value: object) -> KataFault:
    if not isinstance(value, dict):
        raise KataError("native kata engine returned an invalid fault")
    payload: dict[str, object] = {str(key): item for key, item in value.items()}
    code: object = payload.get("code")
    path: object = payload.get("path")
    line: object = payload.get("line")
    column: object = payload.get("column")
    message: object = payload.get("message")
    remediation: object = payload.get("remediation")
    if (
        not isinstance(code, str)
        or not isinstance(path, str)
        or not isinstance(line, int)
        or not isinstance(column, int)
        or not isinstance(message, str)
        or not isinstance(remediation, str)
    ):
        raise KataError("native kata engine returned an invalid fault")
    return KataFault(
        code=code,
        path=Path(path),
        line=line,
        column=column,
        message=message,
        remediation=remediation,
    )
