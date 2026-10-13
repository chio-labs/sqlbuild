"""Hand the native rules request builder rows read from the Python compiled project."""

from __future__ import annotations

from dataclasses import asdict
from functools import partial
from pathlib import Path

import orjson

import sqlbuild._native as _native
from sqlbuild._native import compiled_project_facts, declaration_rows
from sqlbuild.adapter.type_system.main.types_equal import types_equal
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.frontier.main.compiled_code_identity import compiled_code_identity
from sqlbuild.compiler.scopes.main.scope_metadata import scope_metadata_projection
from sqlbuild.rule_engine._helpers.run.cache_paths import rules_bulk_cache_path
from sqlbuild.rule_engine.constants import (
    NATIVE_RULES_CACHE_FILE,
    NATIVE_RULES_MEMO_FILE,
    RULES_NATIVE_API_VERSION,
)
from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.rule_engine.models import Finding, NativeRulesEvaluation, RulesConfig


def build_rules_request(
    *,
    project: CompiledProjectView,
    config: RulesConfig,
    project_dir: Path,
    dialect: str,
    initial_findings: tuple[Finding, ...],
    custom_payloads: list[dict[str, object]],
    include_type_proof: bool,
) -> _native.NativeRulesRequest:
    """Build the built-in rules request natively from the compiled project's rows."""

    resolved: Path = project_dir.resolve()
    header: dict[str, object] = {
        "version": RULES_NATIVE_API_VERSION,
        "project_dir": str(resolved),
        "dialect": dialect,
        "config": asdict(config),
        "scope_index": scope_metadata_projection(index=project.scope_index),
        "defer_suppressions": True,
        "custom_rules": custom_payloads,
        "rules_cache_path": str(
            rules_bulk_cache_path(project_dir=resolved, file_name=NATIVE_RULES_CACHE_FILE)
        ),
    }
    public_enums, public_constants = declaration_rows(
        enums=tuple(project.public_enums.values()),
        constants=tuple(project.public_constants.values()),
    )
    project_rows: dict[str, object] = {
        "header_json": _encoded(header),
        "memo": (
            (
                compiled_code_identity(),
                str(
                    rules_bulk_cache_path(project_dir=project_dir, file_name=NATIVE_RULES_MEMO_FILE)
                ),
            )
            if config.cache.enabled
            else None
        ),
        "sql_analysis_enabled": project.settings.sql_analysis,
        "include_type_proof": include_type_proof,
        "attached_audit_targets": [
            audit.attached_target_name
            for audit in project.audits
            if audit.attached_target_name is not None
        ],
        "public_enums": public_enums,
        "public_constants": public_constants,
        "initial_findings": list(initial_findings),
        "types_equal": partial(types_equal, dialect=dialect),
    }
    try:
        request: _native.NativeRulesRequest
        request = _native.build_rules_request(
            project_rows,
            (compiled_project_facts(project), [model.name for model in project.models]),
            list(project.sql_tests),
            list(project.sql_scenarios),
        )
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error
    return request


def evaluate_rules_request(request: _native.NativeRulesRequest) -> NativeRulesEvaluation:
    """Answer the request from the response memo or evaluate it, decoding findings natively."""

    try:
        faults, selected_codes, evaluated, hits, misses, built_in_ms, reused = (
            _native.evaluate_rules_request(request)
        )
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error
    return NativeRulesEvaluation(
        findings=tuple(faults),
        selected_codes=tuple(selected_codes),
        evaluated_models=evaluated,
        cache_hits=hits,
        cache_misses=misses,
        built_in_ms=built_in_ms,
        reused=reused,
    )


def finalize_rules_rows(
    *,
    config: RulesConfig,
    project_dir: Path,
    evaluated_codes: tuple[str, ...],
    findings: tuple[Finding, ...],
) -> tuple[Finding, ...]:
    """Apply the exception policy natively, keeping each original finding's fixable mark."""

    try:
        finalized: list[Finding] = _native.finalize_rule_findings_rows(
            {
                "project_dir": str(project_dir.resolve()),
                "config_json": _encoded(asdict(config)),
                "evaluated_codes": list(evaluated_codes),
                "findings": list(findings),
            }
        )
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error
    return tuple(finalized)


def _encoded(value: object) -> bytes:
    try:
        return orjson.dumps(value, option=orjson.OPT_SORT_KEYS, default=str)
    except orjson.JSONEncodeError as error:
        raise RulesError(str(error)) from error
