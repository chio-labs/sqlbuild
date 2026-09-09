"""Typed Python adapter for the private native rules engine."""

from __future__ import annotations

import hashlib
import inspect
import json
import pickle
import sys
import tempfile
from dataclasses import asdict, replace
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import orjson

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompiledSqlScenario,
    CompiledSqlTest,
)
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.discovery.models import ConstantDeclaration, EnumDeclaration
from sqlbuild.compiler.scopes.main.scope_metadata import scope_metadata_projection
from sqlbuild.rule_engine._helpers.engine.custom_rule_evidence import (
    custom_rule_implementation_fingerprint,
    custom_rule_import_closure,
    custom_rule_project_fact_attributes,
    custom_rule_test_evidence,
)
from sqlbuild.rule_engine.constants import (
    CUSTOM_HOST_RUNTIME_VERSION,
    RULE_CONTEXT_AUDITS_FACT,
    RULE_CONTEXT_DECLARATIONS_FACT,
    RULE_CONTEXT_GRAPH_FACT,
    RULE_CONTEXT_PROJECT_FACT,
    RULE_CONTEXT_TESTS_FACT,
    RULES_NATIVE_API_VERSION,
)
from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.rule_engine.models import (
    Finding,
    Rule,
    RulesConfig,
    RulesResult,
)
from sqlbuild.sql_values.models import SqlValue
from sqlbuild.sql_values.types import SqlValueKind

_CUSTOM_HOST_REQUIRED: str = "selected custom rules require a custom host"


def evaluate_native(
    *,
    project: CompiledProject,
    config: RulesConfig,
    project_dir: Path,
    catalogue: tuple[Rule, ...],
    dialect: str = "generic",
    initial_findings: tuple[Finding, ...] = (),
) -> RulesResult:
    """Evaluate one compiled model batch through the native engine."""

    selected_catalogue: list[Rule] = []
    for rule in catalogue:
        selected_by_config: bool = any(rule.code.startswith(selector) for selector in config.select)
        if rule.custom and selected_by_config:
            selected_catalogue.append(rule)
    request: dict[str, object] = {
        "version": RULES_NATIVE_API_VERSION,
        "project_dir": str(project_dir.resolve()),
        "dialect": dialect,
        "config": _config_payload(config),
        "models": _model_payloads(project),
        "sql_tests": _sql_test_payloads(project),
        "sql_scenarios": _sql_scenario_payloads(project),
        "public_enums": [
            _enum_payload(declaration) for declaration in project.public_enums.values()
        ],
        "public_constants": [
            _constant_payload(declaration) for declaration in project.public_constants.values()
        ],
        "scope_index": scope_metadata_projection(index=project.scope_index),
        "initial_findings": [_finding_payload(finding) for finding in initial_findings],
        "custom_rules": _custom_rule_payloads(
            catalogue=catalogue, project=project, project_dir=project_dir
        ),
    }
    custom_host_input: Path | None = None
    request["custom_host"] = None
    try:
        try:
            response_json: str = _evaluate_request(request)
        except ValueError as error:
            if _CUSTOM_HOST_REQUIRED not in str(error):
                raise
            custom_host, custom_host_input = _custom_host_payload(
                project=project,
                config=config,
                project_dir=project_dir,
                catalogue=tuple(selected_catalogue),
                dialect=dialect,
            )
            request["custom_host"] = custom_host
            response_json = _evaluate_request(request)
        response: object = orjson.loads(response_json)
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error
    finally:
        if custom_host_input is not None:
            custom_host_input.unlink(missing_ok=True)
    if not isinstance(response, dict):
        raise RulesError("native rules engine returned an invalid response")
    payload: dict[str, Any] = response
    if payload.get("version") != RULES_NATIVE_API_VERSION:
        raise RulesError("native rules engine returned an unsupported response version")
    raw_findings: object = payload.get("faults")
    if not isinstance(raw_findings, list):
        raise RulesError("native rules engine returned invalid findings")
    return RulesResult(
        findings=tuple(_decode_finding(value) for value in raw_findings),
        evaluated_models=int(payload.get("evaluated_models", 0)),
        cache_hits=int(payload.get("cache_hits", 0)),
        cache_misses=int(payload.get("cache_misses", 0)),
        built_in_ms=int(payload.get("built_in_ms", 0)),
        custom_ms=int(payload.get("custom_ms", 0)),
    )


def _evaluate_request(request: dict[str, object]) -> str:
    return _native.evaluate_json(
        orjson.dumps(request, option=orjson.OPT_SORT_KEYS, default=str).decode()
    )


def load_native_config(project_dir: Path) -> dict[str, object]:
    """Load strict rules TOML through the native configuration owner."""

    try:
        payload: object = json.loads(_native.load_config_json(str(project_dir.resolve())))
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error
    if not isinstance(payload, dict):
        raise RulesError("native rules engine returned invalid configuration")
    return {str(key): value for key, value in payload.items()}


def native_catalogue() -> tuple[dict[str, object], ...]:
    """Return native-owned built-in rule metadata."""

    try:
        payload: object = json.loads(_native.catalogue_json())
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error
    if not isinstance(payload, dict) or not isinstance(payload.get("rules"), list):
        raise RulesError("native rules engine returned an invalid catalogue")
    rules: list[object] = payload["rules"]
    if any(not isinstance(value, dict) for value in rules):
        raise RulesError("native rules engine returned invalid rule metadata")
    normalized: list[dict[str, object]] = []
    for value in rules:
        normalized.append({str(key): item for key, item in value.items()})
    return tuple(normalized)


def native_selected_codes(
    *, config: RulesConfig, catalogue: tuple[Rule, ...], project_dir: Path
) -> tuple[str, ...]:
    """Resolve the active ruleset through the native Fensu adapter."""

    closures: dict[str, tuple[Path, ...]] = {}
    request: dict[str, object] = {
        "version": RULES_NATIVE_API_VERSION,
        "config": _config_payload(config),
        "custom_rules": [
            {
                "code": rule.code,
                "family": rule.family,
                "slug": rule.slug,
                "message": rule.message,
                "remediation": rule.remediation,
                "enabled_by_default": rule.enabled_by_default,
                "implementation_fingerprint": custom_rule_implementation_fingerprint(
                    rule=rule,
                    project_dir=project_dir,
                    import_closure=_shared_import_closure(
                        rule=rule, project_dir=project_dir, cache=closures
                    ),
                ),
                **_custom_rule_source_payload(rule=rule, project_dir=project_dir),
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
            _native.selected_codes_json(json.dumps(request, sort_keys=True, default=str))
        )
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error
    if not isinstance(payload, list) or any(not isinstance(code, str) for code in payload):
        raise RulesError("native rules engine returned invalid selected rule codes")
    return tuple(payload)


def render_native_owned_skill(*, content: str, input_fingerprint: str) -> str:
    """Attach Fensu schema-v2 ownership to generated guidance."""

    try:
        return _native.render_owned_skill(content, input_fingerprint)
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error


def native_skill_freshness(*, content: str | None, input_fingerprint: str) -> str:
    """Classify generated guidance through the Fensu ownership contract."""

    return _native.skill_freshness(content, input_fingerprint)


def _config_payload(config: RulesConfig) -> dict[str, object]:
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
        if test.mode is not SqlTestMode.MODEL:
            continue
        for name in test.target_model_names:
            test_counts[name] = test_counts.get(name, 0) + 1
    return [
        _model_payload(
            model=model,
            compiled_audit_count=audit_counts.get(model.name, 0),
            targeting_test_count=test_counts.get(model.name, 0),
        )
        for model in project.models
    ]


def _sql_test_payloads(project: CompiledProject) -> list[dict[str, object]]:
    return [_sql_test_payload(test) for test in project.sql_tests]


def _sql_test_payload(test: CompiledSqlTest) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_path": (test.source_path or test.test_file.relative_path).as_posix(),
        "ownership_root": (test.ownership_root or test.test_file.ownership_root).as_posix(),
        "block_index": test.block_index or test.test_block.test_index,
        "name": test.name,
        "explicit_name": test.explicit_name,
        "mode": test.mode.value,
        "expected_model_names": list(test.expected_model_names),
        "assertion_names": list(test.assertion_names),
        "assertion_target_model_names": list(test.assertion_target_model_names),
        "target_model_names": list(test.target_model_names),
        "tested_resources": [
            {"kind": resource.kind.value, "name": resource.name}
            for resource in test.tested_resources
        ],
    }
    if test.case_name is not None:
        parameter_types: dict[str, str] = {
            parameter.name: parameter.value_type.value for parameter in test.parameter_schema
        }
        payload.update(
            {
                "parent_name": test.parent_name,
                "case_name": test.case_name,
                "case_index": test.case_index,
                "case_fingerprint": test.case_fingerprint,
                "parameter_schema": [
                    {
                        "name": parameter.name,
                        "type": parameter.value_type.value,
                        "nullable": parameter.nullable,
                    }
                    for parameter in test.parameter_schema
                ],
                "parameters": [
                    {
                        "name": name,
                        "type": parameter_types[name],
                        "value": _typed_value_payload(value),
                    }
                    for name, value in test.parameter_values
                ],
            }
        )
    return payload


def _sql_scenario_payloads(project: CompiledProject) -> list[dict[str, object]]:
    return [_sql_scenario_payload(scenario) for scenario in project.sql_scenarios]


def _sql_scenario_payload(scenario: CompiledSqlScenario) -> dict[str, object]:
    description: object | None = scenario.scenario_file.header_values.get("description")
    return {
        "source_path": (scenario.source_path or scenario.scenario_file.relative_path).as_posix(),
        "ownership_root": (
            scenario.ownership_root or scenario.scenario_file.ownership_root
        ).as_posix(),
        "name": scenario.name,
        "description": description if isinstance(description, str) else None,
        "expected_model_names": list(scenario.expected_model_names),
        "assertion_names": list(scenario.assertion_names),
        "assertion_target_model_names": list(scenario.assertion_target_model_names),
        "target_model_names": list(scenario.target_model_names),
    }


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
        "value": _typed_value_payload(declaration.value),
        "value_type": declaration.logical_type.display_name,
        "render_as": declaration.render_as.value if declaration.render_as is not None else None,
    }


def _typed_value_payload(value: SqlValue) -> object:
    if value.kind == SqlValueKind.DECIMAL:
        return str(cast(Decimal, value.value))
    if value.kind in {
        SqlValueKind.STRING,
        SqlValueKind.INTEGER,
        SqlValueKind.BOOLEAN,
        SqlValueKind.FLOAT,
        SqlValueKind.NULL,
    }:
        return value.value
    if value.kind in {SqlValueKind.LIST, SqlValueKind.SET}:
        return [_typed_value_payload(item) for item in cast(tuple[SqlValue, ...], value.value)]
    return {
        key: _typed_value_payload(item)
        for key, item in cast(tuple[tuple[str, SqlValue], ...], value.value)
    }


def _custom_rule_payloads(
    *, catalogue: tuple[Rule, ...], project: CompiledProject, project_dir: Path
) -> list[dict[str, object]]:
    fingerprints: dict[frozenset[str], str] = {}
    closures: dict[str, tuple[Path, ...]] = {}
    payloads: list[dict[str, object]] = []
    for rule in catalogue:
        if not rule.custom:
            continue
        closure: tuple[Path, ...] = _shared_import_closure(
            rule=rule, project_dir=project_dir, cache=closures
        )
        attributes: frozenset[str] = custom_rule_project_fact_attributes(
            rule=rule, project_dir=project_dir, import_closure=closure
        )
        if attributes not in fingerprints:
            fingerprints[attributes] = _custom_fact_fingerprint(
                project=project, attributes=attributes
            )
        fact_fingerprint: str = fingerprints[attributes]
        payloads.append(
            _custom_rule_payload(
                rule=rule,
                project_dir=project_dir,
                project_attributes=attributes,
                fact_fingerprint=fact_fingerprint,
                import_closure=closure,
            )
        )
    return payloads


def _custom_rule_payload(
    *,
    rule: Rule,
    project_dir: Path,
    project_attributes: frozenset[str],
    fact_fingerprint: str,
    import_closure: tuple[Path, ...],
) -> dict[str, object]:
    check_name: str = getattr(rule.check, "__name__", "")
    return {
        "code": rule.code,
        "family": rule.family,
        "slug": rule.slug,
        "message": rule.message,
        "remediation": rule.remediation,
        "enabled_by_default": rule.enabled_by_default,
        "implementation_fingerprint": custom_rule_implementation_fingerprint(
            rule=rule, project_dir=project_dir, import_closure=import_closure
        ),
        **_custom_rule_source_payload(rule=rule, project_dir=project_dir),
        "project_wide": rule.project_wide,
        "project_dependent": RULE_CONTEXT_PROJECT_FACT in project_attributes,
        "fact_fingerprint": fact_fingerprint,
        "check_name": check_name,
        "test_case_count": len(custom_rule_test_evidence(rule=rule, project_dir=project_dir)),
    }


def _shared_import_closure(
    *, rule: Rule, project_dir: Path, cache: dict[str, tuple[Path, ...]]
) -> tuple[Path, ...]:
    if rule.source is None:
        return ()
    source: str = str(Path(rule.source).resolve())
    if source not in cache:
        cache[source] = custom_rule_import_closure(rule=rule, project_dir=project_dir)
    return cache[source]


def _custom_fact_fingerprint(*, project: CompiledProject, attributes: frozenset[str]) -> str:
    facts: dict[str, object] = {}
    if RULE_CONTEXT_GRAPH_FACT in attributes:
        facts[RULE_CONTEXT_GRAPH_FACT] = [
            (model.name, model.relative_path, model.deps) for model in project.models
        ]
    if RULE_CONTEXT_TESTS_FACT in attributes:
        facts[RULE_CONTEXT_TESTS_FACT] = project.sql_tests
    if RULE_CONTEXT_AUDITS_FACT in attributes:
        facts[RULE_CONTEXT_AUDITS_FACT] = project.audits
    if RULE_CONTEXT_DECLARATIONS_FACT in attributes:
        facts[RULE_CONTEXT_DECLARATIONS_FACT] = (
            project.public_enums,
            project.public_constants,
            tuple(model.enum_declarations for model in project.models),
            tuple(model.constant_declarations for model in project.models),
        )
    encoded: bytes = orjson.dumps(facts, option=orjson.OPT_SORT_KEYS, default=str)
    return hashlib.sha256(encoded).hexdigest()


def _custom_rule_source_payload(*, rule: Rule, project_dir: Path) -> dict[str, object]:
    source: str | None = rule.source
    if source is not None:
        source_path: Path = Path(source).resolve()
        root: Path = project_dir.resolve()
        if source_path.is_relative_to(root):
            source = source_path.relative_to(root).as_posix()
    try:
        source_line: int = inspect.getsourcelines(rule.check)[1]
    except (OSError, TypeError):
        source_line = 1
    check_owner: str = getattr(rule.check, "__qualname__", getattr(rule.check, "__name__", ""))
    return {
        "source": source,
        "source_line": source_line,
        "source_column": 1,
        "owner": f"{source or 'rules'}:{check_owner}",
    }


def _custom_host_payload(
    *,
    project: CompiledProject,
    config: RulesConfig,
    project_dir: Path,
    catalogue: tuple[Rule, ...],
    dialect: str,
) -> tuple[dict[str, object] | None, Path | None]:
    if not any(rule.custom for rule in catalogue):
        return None, None
    serializable_project: CompiledProject = replace(
        project,
        loaded_macros={},
        loader_functions=(),
        hook_functions=(),
        materialization_files=(),
        external_sql_reference_resolver=None,
    )
    input_dir: Path = project_dir / "target" / "rules-cache" / "host-inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    input_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=input_dir,
            prefix="project-",
            suffix=".pickle",
            delete=False,
        ) as handle:
            input_path = Path(handle.name)
            pickle.dump((serializable_project, config), handle)
    except Exception:
        if input_path is not None:
            input_path.unlink(missing_ok=True)
        raise
    assert input_path is not None
    return (
        {
            "program": sys.executable,
            "arguments": ["-m", "sqlbuild.rule_engine._helpers.engine.custom_host"],
            "timeout_millis": 120_000,
            "runtime_version": CUSTOM_HOST_RUNTIME_VERSION,
            "payload": {
                "project_pickle_path": str(input_path.resolve()),
                "project_dir": str(project_dir.resolve()),
                "dialect": dialect,
            },
        },
        input_path,
    )


def _decode_finding(value: object) -> Finding:
    if not isinstance(value, dict):
        raise RulesError("native rules engine returned an invalid finding")
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
        raise RulesError("native rules engine returned an invalid finding")
    return Finding(
        code=code,
        path=Path(path),
        line=line,
        column=column,
        message=message,
        remediation=remediation,
    )


def _finding_payload(finding: Finding) -> dict[str, object]:
    return {
        "code": finding.code,
        "path": finding.path.as_posix(),
        "line": finding.line,
        "column": finding.column,
        "message": finding.message,
        "remediation": finding.remediation,
    }
