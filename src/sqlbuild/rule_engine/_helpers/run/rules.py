"""Unified compiler-rule orchestration implementation."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from sqlbuild._native import (
    build_lint_expansion_context,
    build_rule_catalogue,
    collect_lint_project_files,
    compiled_relation_keys,
    declared_relation_keys,
    encode_sql_rule_findings,
    load_sql_rule_cache,
    lookup_sql_rule_cache,
    project_with,
    release_freed_memory,
    resolve_rule_ignore_selectors,
    rules_bulk_cache_path,
    run_lint,
    select_catalogue_rules,
    selected_sql_rule_codes,
    sql_file_rule_key,
    sql_model_rule_keys,
    sql_rule_lint_key,
    valid_rules_config,
    with_duplicate_literal_hints,
    write_sql_rule_cache,
)
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledSqlExpansion,
    DeclarationScopeBuild,
    SqlExpansionContext,
)
from sqlbuild.compiler.compile.types import (
    CompiledModelView,
    CompiledProjectView,
    CompiledResourceType,
    CompileInputsView,
    ModelInput,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.lint.constants import (
    DEFAULT_MAX_LITERAL_LENGTH,
    DEFAULT_MAX_RANKING_ORDER_BY,
    MAX_LITERAL_LENGTH_THRESHOLD,
    MAX_RANKING_ORDER_BY_THRESHOLD,
    SAFE_RULE_FIX_CODES,
)
from sqlbuild.lint.exceptions import NativeLintError
from sqlbuild.lint.models import LintConfig, LintRunResult, LintViolation
from sqlbuild.lint.types import RelationKeys
from sqlbuild.rule_engine._helpers.engine.custom_payloads import custom_rule_payloads
from sqlbuild.rule_engine._helpers.engine.hermeticity import verify_custom_rules
from sqlbuild.rule_engine.constants import SQL_RULES_CACHE_FILE, TYPE_PROOF_RULE_CODES
from sqlbuild.rule_engine.models import (
    Finding,
    PreparedSqlLint,
    PreparedSqlLintResult,
    Rule,
    RuleRunPlan,
    RulesConfig,
    SqlExpansionReuse,
    SqlRulesEvaluation,
)

_SQL_RULE_SUPPRESSION_CODE: str = "SQBRSQL000"


@dataclass(frozen=True)
class _SqlRuleInputs:
    identities: dict[str, str]
    project_files: dict[Path, str] | None


def plan_rule_run(
    *,
    graph: ProjectGraph,
    config: RulesConfig,
    project_dir: Path,
    selected_keys: frozenset[CompiledObjectKey] | None,
    no_sql_analysis: bool,
) -> RuleRunPlan:
    """Build the catalogue and select the rules, project slice and settings one run evaluates."""

    release_freed_memory()
    effective_config: RulesConfig = resolve_rule_ignore_selectors(
        config=config, project=graph.project
    )
    resolved_project_dir: Path = project_dir.resolve()
    include_custom: bool = _config_references_custom_rules(effective_config)
    catalogue: tuple[Rule, ...] = build_rule_catalogue(
        config=effective_config,
        project_dir=resolved_project_dir,
        include_custom=include_custom,
    )
    custom_payloads: list[dict[str, object]] = custom_rule_payloads(
        catalogue=catalogue, project_dir=resolved_project_dir
    )
    selected: tuple[Rule, ...] = select_catalogue_rules(
        catalogue=catalogue,
        config=effective_config,
        project_dir=resolved_project_dir,
        custom_payloads=custom_payloads,
    )
    skipped_type_proof_rules: tuple[str, ...] = ()
    if no_sql_analysis or not graph.project.settings.sql_analysis:
        skipped_type_proof_rules = tuple(
            rule.code for rule in selected if rule.code in TYPE_PROOF_RULE_CODES
        )
        selected = tuple(rule for rule in selected if rule.code not in TYPE_PROOF_RULE_CODES)
    custom_rules: tuple[Rule, ...] = tuple(rule for rule in selected if rule.custom)
    if custom_rules:
        _ = verify_custom_rules(rules=custom_rules, project_dir=resolved_project_dir)
    model_paths: frozenset[str] | None = _selected_model_paths(
        graph=graph, selected_keys=selected_keys
    )
    selected_project: CompiledProjectView = _selected_project(graph=graph, model_paths=model_paths)
    selected_config: RulesConfig = replace(
        _selection_rules_config(
            config=effective_config,
            model_paths=model_paths,
            project=selected_project,
        ),
        select=tuple(rule.code for rule in selected),
        ignore=(),
    )
    return RuleRunPlan(
        effective_config=effective_config,
        project_dir=resolved_project_dir,
        catalogue=catalogue,
        custom_payloads=custom_payloads,
        selected=selected,
        skipped_type_proof_rules=skipped_type_proof_rules,
        model_paths=model_paths,
        project=selected_project,
        config=selected_config,
    )


def run_planned_sql_rules(
    *,
    plan: RuleRunPlan,
    graph: ProjectGraph,
    discovered_inputs: DiscoveredProjectInputs,
    dialect: str,
    prepared_sql: PreparedSqlLint | None,
    expansion_reuse: SqlExpansionReuse | None,
) -> SqlRulesEvaluation:
    """Run the planned SQL rules on the caller while built-in rules evaluate natively."""

    native_rules: tuple[Rule, ...] = tuple(rule for rule in plan.selected if not rule.custom)
    lint_config: LintConfig = sql_lint_config(
        dialect=dialect,
        codes=_sql_rule_codes(native_rules),
        thresholds=plan.effective_config.thresholds,
        relation_keys=compiled_relation_keys(graph.project),
        allow_suppressions=plan.effective_config.allow_exceptions,
    )
    sql_rule_inputs: _SqlRuleInputs = _prepare_sql_rule_inputs(
        rules=native_rules,
        project=plan.project,
        dialect=sql_rule_lint_key(config=lint_config),
        project_dir=plan.project_dir,
        collect_files=prepared_sql is None and plan.model_paths is None,
        discovered_inputs=discovered_inputs,
    )
    sql_started: float = time.monotonic()
    sql_result: SqlRulesEvaluation = _run_sql_rules(
        rules=native_rules,
        project_dir=plan.project_dir,
        discovered_inputs=discovered_inputs,
        project=plan.project,
        lint_config=lint_config,
        selected_model_paths=plan.model_paths,
        cache_enabled=plan.effective_config.cache.enabled,
        prepared_sql=prepared_sql,
        expansion_reuse=expansion_reuse,
        prepared_inputs=sql_rule_inputs,
    )
    return replace(sql_result, sql_ms=round((time.monotonic() - sql_started) * 1000))


def _prepare_sql_rule_inputs(
    *,
    rules: tuple[Rule, ...],
    project: CompiledProjectView,
    dialect: str,
    project_dir: Path,
    collect_files: bool,
    discovered_inputs: DiscoveredProjectInputs,
) -> _SqlRuleInputs:
    """Hash SQL and read the project files on the caller while built-in rules evaluate natively."""

    identities: dict[str, str] = _sql_model_rule_identities(
        rules=rules, project=project, dialect=dialect
    )
    return _SqlRuleInputs(
        identities=identities,
        project_files=(
            collect_lint_project_files(project_dir=project_dir, selected_paths=None)
            if identities and collect_files
            else None
        ),
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


def sql_lint_preparation(
    *, inputs: CompileInputsView, dialect: str
) -> tuple[Path, tuple[str, ...], LintConfig] | None:
    """The project, SQL rule codes and lint settings early SQL lint runs with, if it should run."""

    project_dir: Path | None = inputs.discovered_inputs.project_dir
    if project_dir is None or any(diagnostic.is_error for diagnostic in inputs.diagnostics):
        return None
    config: RulesConfig | None = valid_rules_config(project_dir=project_dir)
    if (
        config is None
        or not config.select
        or (config.cache.enabled and _read_sql_rule_cache(project_dir))
    ):
        return None
    codes: tuple[str, ...] = _selected_sql_codes(config)
    if not codes:
        return None
    return (
        project_dir,
        codes,
        sql_lint_config(
            dialect=dialect,
            codes=codes,
            thresholds=config.thresholds,
            allow_suppressions=config.allow_exceptions,
            relation_keys=declared_relation_keys(
                model_rows=(model.relation_key_row for model in inputs.model_inputs),
                seeds=(seed.schema_entry for seed in inputs.seed_inputs),
                sources=(source.source_entry for source in inputs.source_inputs),
            ),
        ),
    )


def early_lint_expansions(
    model_inputs: tuple[ModelInput, ...],
) -> dict[Path, CompiledSqlExpansion]:
    """Each model's compile expansion for early lint, whole when the compile handed one over."""

    expansions: dict[Path, CompiledSqlExpansion] = {}
    for model in model_inputs:
        expansion: CompiledSqlExpansion | None = model.lint_expansion or model.sql_expansion
        if expansion is not None:
            expansions[model.model_file.file_path] = expansion
    return expansions


def _selection_rules_config(
    *,
    config: RulesConfig,
    model_paths: frozenset[str] | None,
    project: CompiledProjectView,
) -> RulesConfig:
    if model_paths is None:
        return config
    selected_model_names: frozenset[str] = frozenset(model.name for model in project.models)
    return replace(
        config,
        rule_exceptions=tuple(
            entry for entry in config.rule_exceptions if Path(entry.path).as_posix() in model_paths
        ),
        graph_edge_exceptions=tuple(
            entry
            for entry in config.graph_edge_exceptions
            if entry.consumer in selected_model_names
        ),
    )


def _selected_sql_codes(config: RulesConfig) -> tuple[str, ...]:
    return tuple(selected_sql_rule_codes(select=list(config.select), ignore=list(config.ignore)))


def _selected_project(
    *, graph: ProjectGraph, model_paths: frozenset[str] | None
) -> CompiledProjectView:
    if model_paths is None:
        return graph.project
    return project_with(
        project=graph.project,
        models=tuple(
            model for model in graph.project.models if model.relative_path.as_posix() in model_paths
        ),
    )


def _prepared_project_files(
    *, prepared_sql: PreparedSqlLint | None, project_dir: Path, codes: tuple[str, ...]
) -> dict[Path, str] | None:
    """Reuse the full-project read of a matching early SQL lint for this invocation."""

    if (
        prepared_sql is None
        or prepared_sql.project_dir != project_dir
        or set(prepared_sql.codes) != set(codes)
        or prepared_sql.future.exception() is not None
    ):
        return None
    return dict(prepared_sql.future.result().result.source_texts)


def _run_prepared_lint(
    *,
    project_dir: Path,
    config: LintConfig,
    selected_paths: frozenset[Path],
    discovered_inputs: DiscoveredProjectInputs,
    compiled_expansions: dict[Path, CompiledSqlExpansion],
    dynamic_output_paths: frozenset[Path],
    prepared_sql: PreparedSqlLint | None,
    expansion_reuse: SqlExpansionReuse | None,
    source_files: dict[Path, str] | None,
) -> LintRunResult:
    if prepared_sql is None or set(prepared_sql.codes) != set(config.enabled_native_rules or ()):
        return run_lint(
            project_dir=project_dir,
            config=config,
            selected_paths=selected_paths,
            discovered_inputs=discovered_inputs,
            compiled_expansions=compiled_expansions,
            dynamic_output_paths=dynamic_output_paths,
            expansion_context=(
                _lint_expansion_context(
                    project_dir=project_dir,
                    discovered_inputs=discovered_inputs,
                    expansion_reuse=expansion_reuse,
                )
                if config.native_enabled
                else None
            ),
            source_files=source_files,
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
            source_files=dict(prepared.source_texts),
        )
        violations = (*violations, *proven.violations)
    return replace(prepared, violations=violations, files_checked=len(selected_paths))


def _run_sql_rules(
    *,
    rules: tuple[Rule, ...],
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    project: CompiledProjectView,
    lint_config: LintConfig,
    selected_model_paths: frozenset[str] | None,
    cache_enabled: bool,
    prepared_sql: PreparedSqlLint | None = None,
    expansion_reuse: SqlExpansionReuse | None = None,
    prepared_inputs: _SqlRuleInputs | None = None,
) -> SqlRulesEvaluation:
    codes: tuple[str, ...] = _sql_rule_codes(rules)
    if not codes:
        return SqlRulesEvaluation(findings=(), cache_hits=0, cache_misses=0)
    models_by_path: dict[str, CompiledModelView] = _sql_rule_models(project)
    bucket: dict[str, tuple[str, str]] = _read_sql_rule_cache(project_dir) if cache_enabled else {}
    identities: dict[str, str] = (
        prepared_inputs.identities
        if prepared_inputs is not None
        else _sql_model_rule_identities(
            rules=rules, project=project, dialect=sql_rule_lint_key(config=lint_config)
        )
    )
    findings: list[Finding] = []
    model_hits: dict[str, tuple[Finding, ...]] = _cached_sql_findings(
        bucket=bucket, keys=identities
    )
    misses: set[str] = set(identities) - set(model_hits)
    for path in identities:
        findings.extend(model_hits.get(path, ()))
    selected_paths: set[Path] = {project_dir / path for path in misses}
    file_identities: dict[str, str] = {}
    project_files: dict[Path, str] | None = None
    if selected_model_paths is None:
        model_paths: frozenset[Path] = frozenset(
            project_dir / model.relative_path for model in project.models
        )
        project_files = _prepared_project_files(
            prepared_sql=prepared_sql, project_dir=project_dir, codes=codes
        )
        if project_files is None:
            project_files = (
                prepared_inputs.project_files
                if prepared_inputs is not None and prepared_inputs.project_files is not None
                else collect_lint_project_files(project_dir=project_dir, selected_paths=None)
            )
        lint_key: str = sql_rule_lint_key(config=lint_config)
        file_keys: dict[str, str | None] = {
            file_path.relative_to(project_dir).as_posix(): sql_file_rule_key(
                lint_key=lint_key,
                codes=list(codes),
                relative_path=file_path.relative_to(project_dir).as_posix(),
                contents=contents,
                expanded=file_path in project.sql_expansions,
            )
            for file_path, contents in project_files.items()
            if file_path not in model_paths
        }
        file_hits: dict[str, tuple[Finding, ...]] = _cached_sql_findings(
            bucket=bucket,
            keys={path: key for path, key in file_keys.items() if key is not None},
        )
        file_path: Path
        for file_path in project_files:
            if file_path in model_paths:
                continue
            relative_path: str = file_path.relative_to(project_dir).as_posix()
            file_identity: str | None = file_keys[relative_path]
            cached_file: tuple[Finding, ...] | None = file_hits.get(relative_path)
            if cached_file is None:
                selected_paths.add(file_path)
                if file_identity is not None:
                    file_identities[relative_path] = file_identity
            else:
                findings.extend(cached_file)
    result: LintRunResult | None = (
        _run_prepared_lint(
            project_dir=project_dir,
            config=lint_config,
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
            expansion_reuse=expansion_reuse,
            source_files=project_files,
        )
        if selected_paths
        else None
    )
    selected_codes: frozenset[str] = frozenset((*codes, _SQL_RULE_SUPPRESSION_CODE))
    evaluated: list[Finding] = []
    for violation in () if result is None else result.violations:
        if violation.code in selected_codes:
            evaluated.append(
                _lint_finding(
                    violation=violation,
                    project_dir=project_dir,
                    fixable_paths=frozenset(models_by_path),
                )
            )
        elif violation.code == NativeLintError.code:
            finding: Finding = _lint_finding(
                violation=violation, project_dir=project_dir, fixable_paths=frozenset()
            )
            evaluated.extend(
                replace(
                    finding,
                    code=code,
                    message=f"Rule {code} could not be evaluated: {violation.message}",
                    unevaluated=True,
                )
                for code in codes
            )
    findings.extend(evaluated)
    written_identities: dict[str, str] = {
        **{path: identities[path] for path in misses},
        **file_identities,
    }
    if cache_enabled and written_identities:
        by_path: dict[str, list[Finding]] = {path: [] for path in written_identities}
        for finding in evaluated:
            path: str = finding.path.as_posix()
            if path in by_path:
                by_path[path].append(finding)
        for path, identity in written_identities.items():
            bucket[path] = (identity, encode_sql_rule_findings(findings=by_path[path]))
        write_sql_rule_cache(path=_sql_rule_cache_path(project_dir), entries=bucket)
    return SqlRulesEvaluation(
        findings=with_duplicate_literal_hints(findings=tuple(findings), project_dir=project_dir),
        cache_hits=len(identities) - len(misses),
        cache_misses=len(misses),
    )


def _lint_expansion_context(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    expansion_reuse: SqlExpansionReuse | None,
) -> SqlExpansionContext:
    """Build lint expansion, reusing the compiler's scope only for the same discovery."""

    declaration_scope: DeclarationScopeBuild | None = (
        expansion_reuse.declaration_scope
        if expansion_reuse is not None and expansion_reuse.discovered_inputs is discovered_inputs
        else None
    )
    return build_lint_expansion_context(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        declaration_scope=declaration_scope,
    )


def _lint_finding(
    *, violation: LintViolation, project_dir: Path, fixable_paths: frozenset[str]
) -> Finding:
    """Convert one lint violation; fixable when `format --fix` would attempt its edit."""

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
        fixable=violation.fix is not None
        and violation.code in SAFE_RULE_FIX_CODES
        and path.as_posix() in fixable_paths,
    )


def sql_lint_config(
    *,
    dialect: str,
    codes: tuple[str, ...],
    thresholds: dict[str, int],
    relation_keys: RelationKeys,
    allow_suppressions: bool,
) -> LintConfig:
    """Build the native SQL lint configuration that SQL Rules run with."""

    return LintConfig(
        dialect=dialect,
        enabled_native_rules=codes,
        header_rules_enabled=False,
        max_literal_length=thresholds.get(MAX_LITERAL_LENGTH_THRESHOLD, DEFAULT_MAX_LITERAL_LENGTH),
        max_ranking_order_by=thresholds.get(
            MAX_RANKING_ORDER_BY_THRESHOLD, DEFAULT_MAX_RANKING_ORDER_BY
        ),
        relation_keys=relation_keys,
        allow_suppressions=allow_suppressions,
    )


def _sql_rule_codes(rules: tuple[Rule, ...]) -> tuple[str, ...]:
    return tuple(rule.code for rule in rules if rule.code.startswith("SQBRSQL"))


def _sql_rule_models(project: CompiledProjectView) -> dict[str, CompiledModelView]:
    return {
        model.relative_path.as_posix(): model
        for model in project.models
        if project.settings.sql_analysis and model.config.values.get("sql_analysis") is not False
    }


def _sql_model_rule_identities(
    *, rules: tuple[Rule, ...], project: CompiledProjectView, dialect: str
) -> dict[str, str]:
    codes: tuple[str, ...] = _sql_rule_codes(rules)
    if not codes:
        return {}
    models: list[tuple[str, str, str, str | None]] = [
        (path, model.authored_sql, model.query_sql, _contract_text(model))
        for path, model in _sql_rule_models(project).items()
    ]
    keys: dict[str, str] = sql_model_rule_keys(lint_key=dialect, codes=list(codes), models=models)
    return {path: keys[path] for path, *_ in models}


def _contract_text(model: CompiledModelView) -> str | None:
    """Canonical text of the dynamic column contract that SQL rule findings depend on."""

    if model.dynamic_column_contract is None:
        return None
    return json.dumps(
        asdict(model.dynamic_column_contract),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sql_rule_cache_path(project_dir: Path) -> Path:
    return rules_bulk_cache_path(project_dir=project_dir, file_name=SQL_RULES_CACHE_FILE)


def _read_sql_rule_cache(project_dir: Path) -> dict[str, tuple[str, str]]:
    """Return usable entries so incompatible builds cannot suppress early lint."""

    return load_sql_rule_cache(path=_sql_rule_cache_path(project_dir))


def _cached_sql_findings(
    *, bucket: dict[str, tuple[str, str]], keys: dict[str, str]
) -> dict[str, tuple[Finding, ...]]:
    """Decoded stored findings of each path whose key still matches; undecodable ones miss."""

    hits: dict[str, list[Finding]] = lookup_sql_rule_cache(entries=bucket, keys=list(keys.items()))
    return {path: tuple(findings) for path, findings in hits.items()}


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
