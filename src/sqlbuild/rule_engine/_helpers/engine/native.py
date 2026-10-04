"""Typed Python adapter for the private native rules engine."""

from __future__ import annotations

import inspect
import json
from collections.abc import Iterator
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import orjson

import sqlbuild._native as _native
from sqlbuild.adapter.type_system.main.types_equal import types_equal
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledModelSqlTestPayload,
    CompiledProject,
    CompiledSqlScenario,
    CompiledSqlTest,
    CompileSqlTestCte,
    DynamicColumnContractProof,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.discovery.models import ConstantDeclaration, EnumDeclaration
from sqlbuild.compiler.scopes.main.scope_metadata import scope_metadata_projection
from sqlbuild.rule_engine._helpers.engine.custom_rule_evidence import (
    custom_rule_implementation_fingerprint,
    custom_rule_import_closure,
    custom_rule_test_evidence,
)
from sqlbuild.rule_engine._helpers.engine.custom_rules import evaluate_custom_rules_cached
from sqlbuild.rule_engine._helpers.run.native_memo import (
    native_payload_digests,
    native_request_identity,
    read_native_response,
    write_native_response,
)
from sqlbuild.rule_engine.constants import (
    RULES_NATIVE_API_VERSION,
    TYPE_PROOF_RULE_CODES,
)
from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.rule_engine.models import (
    CustomRulesOutcome,
    Finding,
    Rule,
    RulesConfig,
    RulesResult,
)
from sqlbuild.sql_values.models import SqlValue
from sqlbuild.sql_values.types import SqlValueKind


@dataclass(frozen=True)
class _EncodedNativeRequest:
    request_json: bytes
    model_jsons: list[bytes]
    model_digests: list[str]


@dataclass(frozen=True)
class _PreparedNativeRequest:
    identity: str | None
    reused: str | None
    parsed: _native.ParsedRulesRequest | None


def evaluate_native(
    *,
    project: CompiledProject,
    config: RulesConfig,
    project_dir: Path,
    catalogue: tuple[Rule, ...],
    dialect: str = "generic",
    initial_findings: tuple[Finding, ...] = (),
    defer_suppressions: bool = False,
    verify_determinism: bool = False,
    custom_payloads: list[dict[str, object]] | None = None,
    custom_outcome: Future[CustomRulesOutcome] | None = None,
) -> RulesResult:
    """Evaluate built-in rules natively while custom rules run incrementally beside them."""

    payloads: list[dict[str, object]] = (
        custom_rule_payloads(catalogue=catalogue, project_dir=project_dir)
        if custom_payloads is None
        else custom_payloads
    )
    prepared: _PreparedNativeRequest = _prepare_native_request(
        encoded=_encode_native_request(
            project=project,
            config=config,
            project_dir=project_dir,
            dialect=dialect,
            initial_findings=initial_findings,
            custom_payloads=payloads,
        ),
        project_dir=project_dir,
        cache_enabled=config.cache.enabled,
    )
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="sqlbuild-custom-rules") as pool:
        custom_future: Future[CustomRulesOutcome] | None = (
            custom_outcome
            if custom_payloads is not None
            else start_custom_rules(
                executor=pool,
                project=project,
                config=config,
                project_dir=project_dir,
                catalogue=catalogue,
                custom_payloads=payloads,
                dialect=dialect,
                verify_determinism=verify_determinism,
            )
        )
        reused: bool = prepared.reused is not None
        try:
            response: object = orjson.loads(
                _evaluate_request(prepared=prepared, project_dir=project_dir)
            )
        except (ValueError, TypeError) as error:
            raise RulesError(str(error)) from error
        del prepared
        custom: CustomRulesOutcome = (
            CustomRulesOutcome(findings=(), cache_hits=0, cache_misses=0, custom_ms=0)
            if custom_future is None
            else custom_future.result()
        )
    if not isinstance(response, dict):
        raise RulesError("native rules engine returned an invalid response")
    payload: dict[str, Any] = response
    if payload.get("version") != RULES_NATIVE_API_VERSION:
        raise RulesError("native rules engine returned an unsupported response version")
    raw_findings: object = payload.get("faults")
    selected_codes: object = payload.get("selected_codes")
    if not isinstance(raw_findings, list) or not isinstance(selected_codes, list):
        raise RulesError("native rules engine returned invalid findings")
    findings: tuple[Finding, ...] = tuple(
        decode_rule_finding(value) for value in (*raw_findings, *custom.findings)
    )
    if not defer_suppressions:
        findings = finalize_native_findings(
            config=config,
            project_dir=project_dir,
            evaluated_codes=tuple(str(code) for code in selected_codes),
            findings=findings,
        )
    native_hits: int = int(payload.get("cache_hits", 0))
    native_misses: int = int(payload.get("cache_misses", 0))
    return RulesResult(
        findings=findings,
        evaluated_models=int(payload.get("evaluated_models", 0)),
        cache_hits=(native_hits + native_misses if reused else native_hits) + custom.cache_hits,
        cache_misses=(0 if reused else native_misses) + custom.cache_misses,
        built_in_ms=0 if reused else int(payload.get("built_in_ms", 0)),
        custom_ms=custom.custom_ms,
    )


def _encode_native_request(
    *,
    project: CompiledProject,
    config: RulesConfig,
    project_dir: Path,
    dialect: str,
    initial_findings: tuple[Finding, ...],
    custom_payloads: list[dict[str, object]],
) -> _EncodedNativeRequest:
    """Encode each model separately so its digest keys cached findings without a second pass."""

    include_type_proof: bool = any(
        _rule_selected(config=config, code=code) for code in TYPE_PROOF_RULE_CODES
    )
    model_jsons: list[bytes] = [
        _serialise_native_request(payload)
        for payload in _model_payloads(
            project=project, dialect=dialect, include_type_proof=include_type_proof
        )
    ]
    return _EncodedNativeRequest(
        request_json=_serialise_native_request(
            _native_request(
                project=project,
                config=config,
                project_dir=project_dir,
                dialect=dialect,
                initial_findings=initial_findings,
                custom_payloads=custom_payloads,
            )
        ),
        model_jsons=model_jsons,
        model_digests=native_payload_digests(model_jsons),
    )


def _native_request(
    *,
    project: CompiledProject,
    config: RulesConfig,
    project_dir: Path,
    dialect: str,
    initial_findings: tuple[Finding, ...],
    custom_payloads: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "version": RULES_NATIVE_API_VERSION,
        "project_dir": str(project_dir.resolve()),
        "dialect": dialect,
        "config": _config_payload(config),
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
        "defer_suppressions": True,
        "custom_rules": custom_payloads,
    }


def start_custom_rules(
    *,
    executor: Executor,
    project: CompiledProject,
    config: RulesConfig,
    project_dir: Path,
    catalogue: tuple[Rule, ...],
    custom_payloads: list[dict[str, object]],
    dialect: str,
    verify_determinism: bool = False,
) -> Future[CustomRulesOutcome] | None:
    """Submit selected custom rules, reusing the implementation fingerprints of their payloads."""

    custom_rules: tuple[Rule, ...] = _selected_custom_rules(
        config=config, catalogue=catalogue, custom_payloads=custom_payloads
    )
    if not custom_rules:
        return None
    return executor.submit(
        evaluate_custom_rules_cached,
        project=project,
        config=config,
        project_dir=project_dir.resolve(),
        rules=custom_rules,
        dialect=dialect,
        verify_determinism=verify_determinism,
        implementation_fingerprints={
            str(payload["code"]): str(payload["implementation_fingerprint"])
            for payload in custom_payloads
        },
    )


def _selected_custom_rules(
    *,
    config: RulesConfig,
    catalogue: tuple[Rule, ...],
    custom_payloads: list[dict[str, object]],
) -> tuple[Rule, ...]:
    if not custom_payloads:
        return ()
    selected: frozenset[str] = frozenset(
        _selected_codes(config=config, custom_payloads=custom_payloads)
    )
    return tuple(rule for rule in catalogue if rule.custom and rule.code in selected)


def _serialise_native_request(request: dict[str, object]) -> bytes:
    """Encode one native request part, reporting values the encoder rejects as rules errors."""

    try:
        return orjson.dumps(request, option=orjson.OPT_SORT_KEYS, default=str)
    except orjson.JSONEncodeError as error:
        raise RulesError(str(error)) from error


def _prepare_native_request(
    *, encoded: _EncodedNativeRequest, project_dir: Path, cache_enabled: bool
) -> _PreparedNativeRequest:
    """Resolve the memo, else decode natively so the encoded payloads die when this returns."""

    identity: str | None = (
        native_request_identity(
            request_json=encoded.request_json, model_digests=encoded.model_digests
        )
        if cache_enabled
        else None
    )
    reused: str | None = (
        read_native_response(project_dir=project_dir, identity=identity)
        if identity is not None
        else None
    )
    return _PreparedNativeRequest(
        identity=identity,
        reused=reused,
        parsed=_parse_native_request(encoded) if reused is None else None,
    )


def _parse_native_request(encoded: _EncodedNativeRequest) -> _native.ParsedRulesRequest:
    try:
        return _native.parse_rules_parts(
            encoded.request_json, encoded.model_jsons, encoded.model_digests
        )
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error


def _evaluate_request(*, prepared: _PreparedNativeRequest, project_dir: Path) -> str:
    if prepared.reused is not None:
        return prepared.reused
    response: str = _native.evaluate_parsed_rules(cast(_native.ParsedRulesRequest, prepared.parsed))
    if prepared.identity is not None:
        write_native_response(
            project_dir=project_dir, identity=prepared.identity, response=response
        )
    return response


def finalize_native_findings(
    *,
    config: RulesConfig,
    project_dir: Path,
    evaluated_codes: tuple[str, ...],
    findings: tuple[Finding, ...],
) -> tuple[Finding, ...]:
    """Apply exception policy once to completed SQL, native, and custom findings."""

    request: dict[str, object] = {
        "version": RULES_NATIVE_API_VERSION,
        "project_dir": str(project_dir.resolve()),
        "config": _config_payload(config),
        "evaluated_codes": evaluated_codes,
        "findings": [_finding_payload(finding) for finding in findings],
    }
    try:
        payload: object = orjson.loads(
            _native.finalize_rule_findings_json(orjson.dumps(request).decode())
        )
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error
    if not isinstance(payload, list):
        raise RulesError("native rules engine returned invalid finalized findings")
    fixable: frozenset[tuple[str, str, int, int, str]] = frozenset(
        _finding_identity(finding) for finding in findings if finding.fixable
    )
    finalized: tuple[Finding, ...] = tuple(decode_rule_finding(value) for value in payload)
    return tuple(
        replace(finding, fixable=True) if _finding_identity(finding) in fixable else finding
        for finding in finalized
    )


def _finding_identity(finding: Finding) -> tuple[str, str, int, int, str]:
    return (
        finding.code,
        finding.path.as_posix(),
        finding.line,
        finding.column,
        finding.message,
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
    *,
    config: RulesConfig,
    catalogue: tuple[Rule, ...],
    project_dir: Path,
    custom_payloads: list[dict[str, object]] | None = None,
) -> tuple[str, ...]:
    """Resolve the active ruleset through the native Fensu adapter."""

    return _selected_codes(
        config=config,
        custom_payloads=(
            custom_rule_payloads(catalogue=catalogue, project_dir=project_dir)
            if custom_payloads is None
            else custom_payloads
        ),
    )


def _selected_codes(
    *, config: RulesConfig, custom_payloads: list[dict[str, object]]
) -> tuple[str, ...]:
    request: dict[str, object] = {
        "version": RULES_NATIVE_API_VERSION,
        "config": _config_payload(config),
        "custom_rules": custom_payloads,
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


def _rule_selected(*, config: RulesConfig, code: str) -> bool:
    selected: bool = any(code.startswith(selector) for selector in config.select)
    ignored: bool = any(code.startswith(selector) for selector in config.ignore)
    return selected and not ignored


def _model_payloads(
    *, project: CompiledProject, dialect: str, include_type_proof: bool
) -> Iterator[dict[str, object]]:
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
    return (
        dict(
            _model_payload(
                model=model,
                compiled_audit_count=audit_counts.get(model.name, 0),
                targeting_test_count=test_counts.get(model.name, 0),
                dialect=dialect,
                include_type_proof=include_type_proof,
            ),
            sql_analysis_disabled=not project.settings.sql_analysis
            or model.config.values.get("sql_analysis") is False,
        )
        for model in project.models
    )


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
    if isinstance(test.payload, CompiledModelSqlTestPayload):
        payload.update(
            {
                "authored_ctes": _sql_test_cte_payloads(test.payload.authored_ctes),
                "expected_ctes": _sql_test_cte_payloads(test.payload.expected_ctes),
                "assertion_ctes": _sql_test_cte_payloads(test.payload.assertion_ctes),
                "has_macro_mocks": bool(test.payload.macro_mocks),
                "has_model_query_overrides": bool(test.payload.model_query_overrides),
            }
        )
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


def _sql_test_cte_payloads(ctes: tuple[CompileSqlTestCte, ...]) -> list[dict[str, str]]:
    return [{"name": cte.name, "sql": cte.sql_body} for cte in ctes]


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
    *,
    model: CompiledModel,
    compiled_audit_count: int,
    targeting_test_count: int,
    dialect: str,
    include_type_proof: bool,
) -> dict[str, object]:
    schema_audit_count: int = 0
    columns: list[dict[str, object]] = []
    if model.schema_entry is not None:
        inferred_by_name: dict[str, InferredColumn] = {
            column.name: column for column in (model.inferred_columns or ())
        }
        schema_audit_count = len(model.schema_entry.audits) + sum(
            len(column.audits) for column in model.schema_entry.columns
        )
        for column in model.schema_entry.columns:
            payload: dict[str, object] = {
                "name": column.name,
                "type": column.type or "",
                "nullable": column.nullable,
                "audit_count": len(column.audits),
            }
            if include_type_proof:
                payload["type_proven"] = bool(
                    column.type
                    and (inferred := inferred_by_name.get(column.name)) is not None
                    and inferred.type
                    and types_equal(
                        left=column.type,
                        right=inferred.type,
                        dialect=dialect,
                    )
                )
            columns.append(payload)
    dynamic_columns: list[dict[str, object]] = []
    dynamic_columns_proven: bool = False
    if model.schema_entry is not None and model.schema_entry.dynamic_columns:
        proof: DynamicColumnContractProof | None = model.dynamic_column_contract
        dynamic_columns_proven = bool(proof is not None and proof.output_proven)
        proof_types: dict[str, str | None] = (
            {family.name.casefold(): family.inferred_type for family in proof.families}
            if proof is not None
            else {}
        )
        for family in model.schema_entry.dynamic_columns:
            inferred_type: str | None = proof_types.get(family.name.casefold())
            dynamic_columns.append(
                {
                    "name": family.name,
                    "pivot_column": family.pivot_column,
                    "value_column": family.value_column,
                    "aggregate": family.aggregate,
                    "type": family.type,
                    "name_pattern": family.name_pattern,
                    "type_proven": bool(
                        include_type_proof
                        and inferred_type
                        and types_equal(
                            left=family.type,
                            right=inferred_type,
                            dialect=dialect,
                        )
                    ),
                }
            )
    return {
        "name": model.name,
        "relative_path": model.relative_path.as_posix(),
        "query_sql": model.query_sql,
        "authored_sql": model.authored_query_sql or model.authored_sql,
        "config": model.config.values,
        "authored_config_keys": list(model.config.model_header_keys),
        "logical_schema": model.config.layer_schema,
        "references": [
            {
                "ref_kind": str(reference.ref_kind),
                "ref_name": reference.ref_name,
                "ref_package": reference.ref_package,
            }
            for reference in model.references
        ],
        "columns": columns,
        "dynamic_columns": dynamic_columns,
        "dynamic_columns_proven": dynamic_columns_proven,
        "bare_dynamic_pivot": bool(
            model.dynamic_column_contract is not None
            and model.dynamic_column_contract.bare_dynamic_pivot
        ),
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


def custom_rule_payloads(
    *, catalogue: tuple[Rule, ...], project_dir: Path
) -> list[dict[str, object]]:
    """Describe every catalogued custom rule for native selection and evaluation."""

    closures: dict[str, tuple[Path, ...]] = {}
    return [
        _custom_rule_payload(
            rule=rule,
            project_dir=project_dir,
            import_closure=_shared_import_closure(
                rule=rule, project_dir=project_dir, cache=closures
            ),
        )
        for rule in catalogue
        if rule.custom
    ]


def _custom_rule_payload(
    *, rule: Rule, project_dir: Path, import_closure: tuple[Path, ...]
) -> dict[str, object]:
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
        "check_name": getattr(rule.check, "__name__", ""),
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


def decode_rule_finding(value: object) -> Finding:
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
        unevaluated=payload.get("unevaluated") is True,
        fixable=payload.get("fixable") is True,
    )


def _finding_payload(finding: Finding) -> dict[str, object]:
    return {
        "unevaluated": finding.unevaluated,
        "code": finding.code,
        "path": finding.path.as_posix(),
        "line": finding.line,
        "column": finding.column,
        "message": finding.message,
        "remediation": finding.remediation,
    }
