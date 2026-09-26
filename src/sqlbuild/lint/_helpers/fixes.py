"""Conservative, compiler-verified fixed-point Rule repair planning."""

from __future__ import annotations

import os
import tempfile
from dataclasses import replace
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledModel, CompiledObjectKey, CompiledProject
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.project import compile_project
from sqlbuild.compiler.sql_analysis.main.identifier_case import ignores_quoted_case
from sqlbuild.lint._helpers.native_format import with_newline_style
from sqlbuild.lint.constants import LINT_ENGINE_NATIVE, VIOLATION_SEVERITY_FAULT
from sqlbuild.lint.exceptions import ProjectCompileError
from sqlbuild.lint.main.build_relation_catalog import build_relation_catalog
from sqlbuild.lint.main.run_lint import run_lint
from sqlbuild.lint.models import (
    FormatChange,
    LintConfig,
    LintEdit,
    LintRunResult,
    LintViolation,
    RuleFixResult,
)

_SAFE_RULES: frozenset[str] = frozenset(
    {
        "SQBRSQL002",
        "SQBRSQL003",
        "SQBRSQL005",
        "SQBRSQL006",
        "SQBRSQL008",
        "SQBRSQL042",
        "SQBRSQL044",
    }
)
_MAX_PASSES: int = 128
_APPLIED: str = "applied"
_CONDITIONLESS_JOIN_CODE: str = "SQBRSQL003"
_SNOWFLAKE_DIALECT: str = "snowflake"


def failed_model_proofs(
    *,
    before: CompiledProject,
    after: CompiledProject,
    changed_paths: frozenset[Path],
    project_dir: Path,
) -> frozenset[CompiledObjectKey] | None:
    """Require complete final-output proofs for edits and all transitive consumers."""
    if any(diagnostic.is_error for diagnostic in (*before.diagnostics, *after.diagnostics)):
        return None
    originals: dict[CompiledObjectKey, CompiledModel] = {
        model.key: model for model in before.models
    }
    candidates: dict[CompiledObjectKey, CompiledModel] = {
        model.key: model for model in after.models
    }
    if originals.keys() != candidates.keys():
        return None
    affected: set[CompiledObjectKey] = {
        model.key for model in after.models if project_dir / model.relative_path in changed_paths
    }
    while True:
        consumers: set[CompiledObjectKey] = set()
        for model in (*before.models, *after.models):
            if any(dependency in affected for dependency in model.deps):
                consumers.add(model.key)
        if consumers <= affected:
            break
        affected.update(consumers)
    failed: set[CompiledObjectKey] = set()
    for key, original in originals.items():
        candidate: CompiledModel = candidates[key]
        complete: bool = (
            original.inferred_columns is not None
            and candidate.inferred_columns is not None
            and original.fast_lineage_columns is not None
            and candidate.fast_lineage_columns is not None
        )
        if key in affected and not complete:
            failed.add(key)
        before_lineage: tuple[object, ...] | None = (
            tuple(original.fast_lineage_columns)
            if original.fast_lineage_columns is not None
            else None
        )
        after_lineage: tuple[object, ...] | None = (
            tuple(candidate.fast_lineage_columns)
            if candidate.fast_lineage_columns is not None
            else None
        )
        if (
            original.inferred_columns != candidate.inferred_columns
            or original.deps != candidate.deps
            or before_lineage != after_lineage
        ):
            failed.add(key)
    return frozenset(failed)


def responsible_edit_paths(
    *,
    before: CompiledProject,
    after: CompiledProject,
    failed: frozenset[CompiledObjectKey],
    proposed_paths: frozenset[Path],
    project_dir: Path,
) -> frozenset[Path]:
    """Conservatively refuse every proposed upstream edit of a failed output proof."""
    models: dict[CompiledObjectKey, list[CompiledModel]] = {}
    for model in (*before.models, *after.models):
        models.setdefault(model.key, []).append(model)
    pending: list[CompiledObjectKey] = list(failed)
    visited: set[CompiledObjectKey] = set()
    paths: set[Path] = set()
    while pending:
        key: CompiledObjectKey = pending.pop()
        if key in visited:
            continue
        visited.add(key)
        for model in models.get(key, ()):
            path: Path = project_dir / model.relative_path
            if path in proposed_paths:
                paths.add(path)
            pending.extend(model.deps)
    return frozenset(paths)


def persist_changes(
    *, files: dict[Path, str], updated: dict[Path, str], newlines: dict[Path, str], write: bool
) -> tuple[FormatChange, ...]:
    changes: list[FormatChange] = []
    for path, contents in sorted(updated.items()):
        after: str = with_newline_style(contents=contents, newline=newlines[path])
        before: str = with_newline_style(contents=files[path], newline=newlines[path])
        if after == before:
            continue
        changes.append(FormatChange(file_path=path, before=before, after=after))
        if write:
            write_atomically(path=path, contents=after)
    return tuple(changes)


def finalize_fix_reports(
    *, reports: tuple[RuleFixResult, ...], declined_paths: set[Path]
) -> tuple[RuleFixResult, ...]:
    return tuple(
        replace(
            report,
            status="refused",
            reason="Final layout formatting failed; original file retained",
        )
        if report.status == _APPLIED and report.file_path in declined_paths
        else report
        for report in reports
    )


def write_atomically(*, path: Path, contents: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path: Path = Path(temporary_name)
    try:
        os.fchmod(descriptor, path.stat().st_mode)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            _ = handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def plan_rule_fixes(
    *,
    project_dir: Path,
    files: dict[Path, str],
    config: LintConfig,
    adapter: TypedSqlValueRenderer | None,
    discovered_inputs: DiscoveredProjectInputs | None,
    enabled: bool,
) -> tuple[dict[Path, str], tuple[RuleFixResult, ...], list[LintViolation]]:
    """Plan in memory; never expose an unverified intermediate version on disk."""

    if not enabled:
        return files, (), []
    if not isinstance(adapter, BaseAdapter) or discovered_inputs is None:
        raise ProjectCompileError("format --fix requires discovered compiler inputs and an adapter")
    current: dict[Path, str] = dict(files)
    inputs: DiscoveredProjectInputs = discovered_inputs
    reports: list[RuleFixResult] = []
    unavailable: dict[Path, RuleFixResult] = {}
    refused_paths: set[Path] = set()
    model_paths: frozenset[Path] = frozenset(model.file_path for model in inputs.model_files)
    baseline: CompiledProject | None = None
    try:
        baseline = compile_project(discovered_inputs=inputs, adapter=adapter)
    except Exception:
        baseline = None
    if baseline is not None:
        config = replace(
            config,
            relation_columns=build_relation_catalog(project=baseline),
            quoted_identifiers_ignore_case=ignores_quoted_case(
                connection=baseline.effective_connection, dialect=config.dialect
            ),
        )
    seen: set[tuple[tuple[Path, str], ...]] = set()
    for _ in range(_MAX_PASSES):
        state: tuple[tuple[Path, str], ...] = tuple(sorted(current.items()))
        if state in seen:
            return _decline(files=files, reports=reports, reason="Rule fixes did not converge")
        seen.add(state)
        result: LintRunResult = run_lint(
            project_dir=project_dir,
            config=replace(config, enabled_native_rules=("SQBRSQL",), header_rules_enabled=False),
            value_renderer=adapter,
            discovered_inputs=inputs,
            source_files=current,
            selected_paths=frozenset(current),
        )
        if result.faults:
            if any(current[fault.file_path] != files[fault.file_path] for fault in result.faults):
                return _decline(
                    files=files,
                    reports=reports,
                    reason="Rule analysis failed after an automatic edit",
                )
            for fault in result.faults:
                unavailable[fault.file_path] = RuleFixResult(
                    file_path=fault.file_path,
                    code=fault.code,
                    line=fault.line,
                    status="unavailable",
                    reason=f"SQL Rule analysis is unavailable: {fault.message}",
                )
        edits: dict[Path, list[LintEdit]] = {}
        pending: list[RuleFixResult] = []
        remaining: list[RuleFixResult] = []
        for violation in result.violations:
            if violation.file_path in unavailable or violation.file_path in refused_paths:
                continue
            if not violation.code.startswith("SQBRSQL"):
                continue
            reason: str | None = violation.fix_unavailable_reason
            if violation.file_path not in model_paths:
                reason = "Compiler-verified Rule fixes currently require a model SQL body"
            elif violation.fix is not None and violation.code not in _SAFE_RULES:
                reason = "This proposed rewrite is not proven meaning-preserving in this dialect"
            elif (
                violation.code == _CONDITIONLESS_JOIN_CODE and config.dialect != _SNOWFLAKE_DIALECT
            ):
                reason = "Conditionless JOIN equivalence is only established for Snowflake"
            if reason is not None or violation.fix is None:
                remaining.append(
                    RuleFixResult(
                        file_path=violation.file_path,
                        code=violation.code,
                        line=violation.line,
                        status="refused" if reason is not None else "unavailable",
                        reason=reason or "No meaning-preserving automatic fix is available",
                    )
                )
                continue
            edit: LintEdit = violation.fix
            chosen: list[LintEdit] = edits.setdefault(edit.file_path, [])
            if any(edit.start < other.end and other.start < edit.end for other in chosen):
                continue
            chosen.append(edit)
            pending.append(
                RuleFixResult(
                    file_path=edit.file_path,
                    code=edit.code,
                    line=violation.line,
                    status="applied",
                    reason="Meaning-preserving rewrite; compiler invariants verified",
                )
            )
        if not edits:
            return current, tuple([*reports, *remaining, *unavailable.values()]), []
        candidate: dict[Path, str] = _apply_edits(files=current, edits=edits)
        candidate_inputs: DiscoveredProjectInputs = _updated_inputs(inputs=inputs, files=candidate)
        valid: bool
        rejected: frozenset[Path]
        valid, rejected = _verify_candidate(
            baseline=baseline,
            inputs=candidate_inputs,
            adapter=adapter,
            project_dir=project_dir,
            proposed_paths=frozenset(edits),
            changed_paths=frozenset(edits)
            | frozenset(report.file_path for report in reports if report.status == _APPLIED),
        )
        if rejected:
            refused_paths.update(rejected)
            reports.extend(
                replace(
                    report,
                    status="refused",
                    reason=(
                        "Compiler could not prove unchanged final outputs, types, "
                        "nullability, dependencies and lineage"
                    ),
                )
                for report in pending
                if report.file_path in rejected
            )
            seen.remove(state)
            continue
        if not valid:
            return _decline(
                files=files,
                reports=reports + pending + remaining,
                reason=(
                    "Compilation could not prove unchanged output columns, types, "
                    "dependencies and lineage"
                ),
            )
        current, inputs = candidate, candidate_inputs
        reports.extend(pending)
    return _decline(files=files, reports=reports, reason="Rule fix pass limit exceeded")


def _updated_inputs(
    *, inputs: DiscoveredProjectInputs, files: dict[Path, str]
) -> DiscoveredProjectInputs:
    return replace(
        inputs,
        model_files=tuple(
            replace(
                model,
                contents=files[model.file_path],
                query_sql=files[model.file_path][model.contents.index(model.query_sql) :].strip(),
            )
            if model.file_path in files and files[model.file_path] != model.contents
            else model
            for model in inputs.model_files
        ),
    )


def _verify_candidate(
    *,
    baseline: CompiledProject | None,
    inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    project_dir: Path,
    proposed_paths: frozenset[Path],
    changed_paths: frozenset[Path],
) -> tuple[bool, frozenset[Path]]:
    if baseline is None:
        return False, frozenset()
    try:
        compiled: CompiledProject = compile_project(discovered_inputs=inputs, adapter=adapter)
        failed: frozenset[CompiledObjectKey] | None = failed_model_proofs(
            before=baseline,
            after=compiled,
            project_dir=project_dir,
            changed_paths=changed_paths,
        )
        rejected: frozenset[Path] = (
            responsible_edit_paths(
                before=baseline,
                after=compiled,
                failed=failed,
                proposed_paths=proposed_paths,
                project_dir=project_dir,
            )
            if failed
            else frozenset()
        )
        return failed is not None and not failed, rejected
    except Exception:
        return False, frozenset()


def _apply_edits(
    *,
    files: dict[Path, str],
    edits: dict[Path, list[LintEdit]],
) -> dict[Path, str]:
    candidate: dict[Path, str] = dict(files)
    for path, path_edits in edits.items():
        contents: str = candidate[path]
        for edit in sorted(path_edits, key=lambda item: item.start, reverse=True):
            contents = contents[: edit.start] + edit.replacement + contents[edit.end :]
        candidate[path] = contents
    return candidate


def _decline(
    *, files: dict[Path, str], reports: list[RuleFixResult], reason: str
) -> tuple[dict[Path, str], tuple[RuleFixResult, ...], list[LintViolation]]:
    affected: set[Path] = {report.file_path for report in reports if report.status == _APPLIED}
    return (
        files,
        tuple(
            replace(report, status="refused", reason=reason)
            if report.status == _APPLIED
            else report
            for report in reports
        ),
        [
            LintViolation(
                file_path=path,
                line=1,
                column=1,
                code="format-fix-verification-failed",
                message=reason,
                severity=VIOLATION_SEVERITY_FAULT,
                engine=LINT_ENGINE_NATIVE,
                remediation=(
                    "Restructure the SQL manually and recompile; the original file was retained."
                ),
            )
            for path in sorted(affected)
        ],
    )
