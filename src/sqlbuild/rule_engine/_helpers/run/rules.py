"""Unified compiler-rule orchestration implementation."""

from __future__ import annotations

import hashlib
import json
import os
import time
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from importlib.metadata import version
from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledSqlExpansion,
    CompileProjectInputs,
    SqlExpansionContext,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.lint.main.build_expansion_context import build_expansion_context
from sqlbuild.lint.main.collect_project_files import collect_project_files
from sqlbuild.lint.main.run_lint import run_lint
from sqlbuild.lint.models import LintConfig, LintRunResult, LintViolation
from sqlbuild.rule_engine._helpers.engine.catalogue import build_catalogue, select_rules
from sqlbuild.rule_engine._helpers.engine.config import resolve_rule_ignore_selectors
from sqlbuild.rule_engine._helpers.engine.hermeticity import verify_custom_rules
from sqlbuild.rule_engine._helpers.engine.native import (
    evaluate_native,
    finalize_native_findings,
    native_catalogue,
)
from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.rule_engine.main.load_config import load_rules_config
from sqlbuild.rule_engine.models import (
    Finding,
    PreparedSqlLint,
    PreparedSqlLintResult,
    Rule,
    RulesConfig,
    RulesResult,
    RulesRunResult,
)

_SQL_RULE_CACHE_VERSION: str = "sql-rules-v2"
_SQLBUILD_VERSION: str = version("sqlbuild")
_SQL_RULE_SUPPRESSION_CODE: str = "SQBRSQL000"


@dataclass(frozen=True)
class _SqlRulesEvaluation:
    findings: tuple[Finding, ...]
    cache_hits: int
    cache_misses: int


def evaluate_rules(
    *,
    graph: ProjectGraph,
    discovered_inputs: DiscoveredProjectInputs,
    config: RulesConfig,
    project_dir: Path,
    dialect: str,
    selected_keys: frozenset[CompiledObjectKey] | None = None,
    prepared_sql: PreparedSqlLint | None = None,
) -> RulesRunResult:
    """Evaluate independent rule phases concurrently, then finalize their combined findings."""
    effective_config: RulesConfig = resolve_rule_ignore_selectors(
        config=config, project=graph.project
    )

    resolved_project_dir: Path = project_dir.resolve()
    include_custom: bool = _config_references_custom_rules(effective_config)
    catalogue: tuple[Rule, ...] = build_catalogue(
        config=effective_config,
        project_dir=resolved_project_dir,
        include_custom=include_custom,
    )
    selected: tuple[Rule, ...] = select_rules(
        catalogue=catalogue, config=effective_config, project_dir=resolved_project_dir
    )
    native_rules: tuple[Rule, ...] = tuple(rule for rule in selected if not rule.custom)
    custom_rules: tuple[Rule, ...] = tuple(rule for rule in selected if rule.custom)
    if custom_rules:
        _ = verify_custom_rules(rules=custom_rules, project_dir=resolved_project_dir)
    model_paths: frozenset[str] | None = _selected_model_paths(
        graph=graph, selected_keys=selected_keys
    )
    selected_project: CompiledProject = _selected_project(graph=graph, model_paths=model_paths)
    selected_config: RulesConfig = replace(
        _selection_rules_config(config=effective_config, model_paths=model_paths),
        select=tuple(rule.code for rule in selected),
        ignore=(),
    )
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="sqlbuild-rules") as executor:
        native_result: Future[RulesResult] = executor.submit(
            evaluate_native,
            project=selected_project,
            config=selected_config,
            project_dir=resolved_project_dir,
            catalogue=catalogue,
            dialect=dialect,
            defer_suppressions=True,
        )
        sql_started: float = time.monotonic()
        sql_result: _SqlRulesEvaluation = _run_sql_rules(
            rules=native_rules,
            project_dir=resolved_project_dir,
            discovered_inputs=discovered_inputs,
            project=selected_project,
            dialect=dialect,
            selected_model_paths=model_paths,
            cache_enabled=effective_config.cache.enabled,
            prepared_sql=prepared_sql,
        )
        sql_ms: int = round((time.monotonic() - sql_started) * 1000)
        result: RulesResult = native_result.result()
    finalized: tuple[Finding, ...] = finalize_native_findings(
        config=selected_config,
        project_dir=resolved_project_dir,
        evaluated_codes=tuple(rule.code for rule in selected),
        findings=(*sql_result.findings, *result.findings),
    )
    findings: tuple[Finding, ...] = tuple(
        sorted(
            finalized,
            key=lambda item: (item.path.as_posix(), item.line, item.column, item.code),
        )
    )
    return RulesRunResult(
        findings=findings,
        evaluated_models=result.evaluated_models,
        built_in_ms=sql_ms + result.built_in_ms,
        custom_ms=result.custom_ms,
        cache_hits=result.cache_hits + sql_result.cache_hits,
        cache_misses=result.cache_misses + sql_result.cache_misses,
    )


def _config_references_custom_rules(config: RulesConfig) -> bool:
    ignore_selectors: list[str] = []
    for entry in config.rule_ignores:
        ignore_selectors.extend(entry.rules)
    selectors: tuple[str, ...] = (
        *config.select,
        *config.ignore,
        *config.rule_options,
        *(entry.rule for entry in config.rule_exceptions),
        *ignore_selectors,
    )
    return any(selector.startswith("XSQBR") for selector in selectors)


def prepare_sql_rules(
    *, inputs: CompileProjectInputs, executor: Executor, dialect: str
) -> PreparedSqlLint | None:
    project_dir: Path | None = inputs.discovered_inputs.project_dir
    if project_dir is None or any(diagnostic.is_error for diagnostic in inputs.diagnostics):
        return None
    try:
        config: RulesConfig = load_rules_config(project_dir=project_dir)
    except RulesError:
        return None
    if not config.select or (config.cache.enabled and _read_sql_rule_cache(project_dir)):
        return None
    codes: tuple[str, ...] = _selected_sql_codes(config)
    if not codes:
        return None
    return PreparedSqlLint(
        codes=codes,
        future=executor.submit(
            _prepare_sql_lint,
            project_dir=project_dir,
            config=LintConfig(
                dialect=dialect, enabled_native_rules=codes, header_rules_enabled=False
            ),
            discovered_inputs=inputs.discovered_inputs,
            compiled_expansions={
                model.model_file.file_path: model.sql_expansion
                for model in inputs.model_inputs
                if model.sql_expansion is not None
            },
        ),
    )


def _prepare_sql_lint(
    *,
    project_dir: Path,
    config: LintConfig,
    discovered_inputs: DiscoveredProjectInputs,
    compiled_expansions: dict[Path, CompiledSqlExpansion],
) -> PreparedSqlLintResult:
    context: SqlExpansionContext = build_expansion_context(
        project_dir=project_dir, discovered_inputs=discovered_inputs
    )
    result: LintRunResult = run_lint(
        project_dir=project_dir,
        config=config,
        discovered_inputs=discovered_inputs,
        compiled_expansions=compiled_expansions,
        expansion_context=context,
    )
    return PreparedSqlLintResult(result=result, context=context)


def _selection_rules_config(
    *, config: RulesConfig, model_paths: frozenset[str] | None
) -> RulesConfig:
    if model_paths is None:
        return config
    return replace(
        config,
        rule_exceptions=tuple(
            entry for entry in config.rule_exceptions if Path(entry.path).as_posix() in model_paths
        ),
    )


def _selected_sql_codes(config: RulesConfig) -> tuple[str, ...]:
    codes: list[str] = []
    for rule in native_catalogue():
        code: str = str(rule["code"])
        if not code.startswith("SQBRSQL"):
            continue
        selected: bool = any(code.startswith(selector) for selector in config.select)
        ignored: bool = any(code.startswith(selector) for selector in config.ignore)
        if selected and not ignored:
            codes.append(code)
    return tuple(codes)


def _selected_project(
    *, graph: ProjectGraph, model_paths: frozenset[str] | None
) -> CompiledProject:
    if model_paths is None:
        return graph.project
    return replace(
        graph.project,
        models=tuple(
            model for model in graph.project.models if model.relative_path.as_posix() in model_paths
        ),
    )


def _run_prepared_lint(
    *,
    project_dir: Path,
    config: LintConfig,
    selected_paths: frozenset[Path],
    discovered_inputs: DiscoveredProjectInputs,
    compiled_expansions: dict[Path, CompiledSqlExpansion],
    dynamic_output_paths: frozenset[Path],
    prepared_sql: PreparedSqlLint | None,
) -> LintRunResult:
    if prepared_sql is None or set(prepared_sql.codes) != set(config.enabled_native_rules or ()):
        return run_lint(
            project_dir=project_dir,
            config=config,
            selected_paths=selected_paths,
            discovered_inputs=discovered_inputs,
            compiled_expansions=compiled_expansions,
            dynamic_output_paths=dynamic_output_paths,
        )
    completed: PreparedSqlLintResult = prepared_sql.future.result()
    prepared: LintRunResult = completed.result
    proof_paths: frozenset[Path] = selected_paths & dynamic_output_paths
    violations: tuple[LintViolation, ...] = tuple(
        violation
        for violation in prepared.violations
        if violation.file_path in selected_paths and violation.file_path not in proof_paths
    )
    if proof_paths:
        proven: LintRunResult = run_lint(
            project_dir=project_dir,
            config=config,
            selected_paths=proof_paths,
            discovered_inputs=discovered_inputs,
            compiled_expansions=compiled_expansions,
            dynamic_output_paths=proof_paths,
            expansion_context=completed.context,
        )
        violations = (*violations, *proven.violations)
    return replace(prepared, violations=violations, files_checked=len(selected_paths))


def _run_sql_rules(
    *,
    rules: tuple[Rule, ...],
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    project: CompiledProject,
    dialect: str,
    selected_model_paths: frozenset[str] | None,
    cache_enabled: bool,
    prepared_sql: PreparedSqlLint | None = None,
) -> _SqlRulesEvaluation:
    codes: tuple[str, ...] = tuple(rule.code for rule in rules if rule.code.startswith("SQBRSQL"))
    if not codes:
        return _SqlRulesEvaluation(findings=(), cache_hits=0, cache_misses=0)
    models_by_path: dict[str, CompiledModel] = {
        model.relative_path.as_posix(): model for model in project.models
    }
    bucket: dict[str, dict[str, object]] = (
        _read_sql_rule_cache(project_dir) if cache_enabled else {}
    )
    identities: dict[str, str] = {
        path: _sql_rule_identity(model=model, codes=codes, dialect=dialect)
        for path, model in models_by_path.items()
    }
    findings: list[Finding] = []
    misses: set[str] = set()
    for path, identity in identities.items():
        cached: tuple[Finding, ...] | None = _cached_sql_findings(
            entry=bucket.get(path), identity=identity
        )
        if cached is None:
            misses.add(path)
        else:
            findings.extend(cached)
    selected_paths: set[Path] = {project_dir / path for path in misses}
    if selected_model_paths is None:
        model_paths: frozenset[Path] = frozenset(project_dir / path for path in models_by_path)
        selected_paths.update(
            path
            for path in collect_project_files(project_dir=project_dir, selected_paths=None)
            if path not in model_paths
        )
    result: LintRunResult | None = (
        _run_prepared_lint(
            project_dir=project_dir,
            config=LintConfig(
                dialect=dialect, enabled_native_rules=codes, header_rules_enabled=False
            ),
            selected_paths=frozenset(selected_paths),
            discovered_inputs=discovered_inputs,
            compiled_expansions=project.sql_expansions,
            dynamic_output_paths=frozenset(
                (project_dir / model.relative_path).resolve()
                for model in models_by_path.values()
                if model.dynamic_column_contract is not None
                and model.dynamic_column_contract.output_proven
            ),
            prepared_sql=prepared_sql,
        )
        if selected_paths
        else None
    )
    selected_codes: frozenset[str] = frozenset((*codes, _SQL_RULE_SUPPRESSION_CODE))
    evaluated: tuple[Finding, ...] = tuple(
        _lint_finding(violation=violation, project_dir=project_dir)
        for violation in (() if result is None else result.violations)
        if violation.code in selected_codes
    )
    findings.extend(evaluated)
    if cache_enabled and misses:
        by_path: dict[str, list[Finding]] = {path: [] for path in misses}
        for finding in evaluated:
            path: str = finding.path.as_posix()
            if path in by_path:
                by_path[path].append(finding)
        for path in misses:
            bucket[path] = {
                "identity": identities[path],
                "findings": [_finding_cache_payload(item) for item in by_path[path]],
            }
        _write_sql_rule_cache(project_dir=project_dir, bucket=bucket)
    return _SqlRulesEvaluation(
        findings=tuple(findings),
        cache_hits=len(identities) - len(misses),
        cache_misses=len(misses),
    )


def _lint_finding(*, violation: LintViolation, project_dir: Path) -> Finding:
    path: Path = violation.file_path
    if path.is_absolute() and path.is_relative_to(project_dir.resolve()):
        path = path.relative_to(project_dir.resolve())
    return Finding(
        code=violation.code,
        path=path,
        line=violation.line,
        column=violation.column,
        message=violation.message,
        remediation=violation.remediation or "Update the authored SQL to satisfy this rule.",
    )


def _sql_rule_identity(*, model: CompiledModel, codes: tuple[str, ...], dialect: str) -> str:
    digest: Any = hashlib.sha256()
    digest.update(_SQL_RULE_CACHE_VERSION.encode())
    digest.update(_SQLBUILD_VERSION.encode())
    digest.update(dialect.encode())
    digest.update("\0".join(codes).encode())
    digest.update(model.authored_sql.encode())
    digest.update(model.query_sql.encode())
    if model.dynamic_column_contract is not None:
        digest.update(
            json.dumps(
                asdict(model.dynamic_column_contract),
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode()
        )
    return digest.hexdigest()


def _sql_rule_cache_path(project_dir: Path) -> Path:
    return project_dir / "target" / "rules-cache" / "bulk" / "sql.json"


def _read_sql_rule_cache(project_dir: Path) -> dict[str, dict[str, object]]:
    path: Path = _sql_rule_cache_path(project_dir)
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("version") != _SQL_RULE_CACHE_VERSION:
        return {}
    entries: object = payload.get("entries")
    if not isinstance(entries, dict):
        return {}
    return {str(key): value for key, value in entries.items() if isinstance(value, dict)}


def _cached_sql_findings(
    *, entry: dict[str, object] | None, identity: str
) -> tuple[Finding, ...] | None:
    if entry is None or entry.get("identity") != identity:
        return None
    values: object = entry.get("findings")
    if not isinstance(values, list):
        return None
    try:
        return tuple(_finding_from_cache_payload(value) for value in values)
    except (KeyError, RulesError, TypeError, ValueError):
        return None


def _finding_from_cache_payload(value: object) -> Finding:
    if not isinstance(value, dict):
        raise RulesError("cached SQL finding must be an object")
    payload: dict[str, object] = {str(key): item for key, item in value.items()}
    code: object = payload["code"]
    path: object = payload["path"]
    line: object = payload["line"]
    column: object = payload["column"]
    message: object = payload["message"]
    remediation: object = payload["remediation"]
    if (
        not isinstance(code, str)
        or not isinstance(path, str)
        or not isinstance(line, int)
        or not isinstance(column, int)
        or not isinstance(message, str)
        or not isinstance(remediation, str)
    ):
        raise RulesError("cached SQL finding has invalid fields")
    return Finding(
        code=code,
        path=Path(path),
        line=line,
        column=column,
        message=message,
        remediation=remediation,
    )


def _finding_cache_payload(finding: Finding) -> dict[str, object]:
    return {
        "code": finding.code,
        "path": finding.path.as_posix(),
        "line": finding.line,
        "column": finding.column,
        "message": finding.message,
        "remediation": finding.remediation,
    }


def _write_sql_rule_cache(*, project_dir: Path, bucket: dict[str, dict[str, object]]) -> None:
    path: Path = _sql_rule_cache_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path = path.with_suffix(f".tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(
            {"version": _SQL_RULE_CACHE_VERSION, "entries": bucket},
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def _selected_model_paths(
    *, graph: ProjectGraph, selected_keys: frozenset[CompiledObjectKey] | None
) -> frozenset[str] | None:
    if selected_keys is None:
        return None
    selected_names: frozenset[str] = frozenset(
        key.name for key in selected_keys if key.resource_type is CompiledResourceType.MODEL
    )
    return frozenset(
        model.relative_path.as_posix()
        for model in graph.project.models
        if model.name in selected_names
    )
