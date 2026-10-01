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
from sqlbuild.lint._helpers.native_format import with_newline_style
from sqlbuild.lint.constants import LINT_ENGINE_NATIVE, VIOLATION_SEVERITY_FAULT
from sqlbuild.lint.exceptions import ProjectCompileError
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
    {"SQBRSQL002", "SQBRSQL003", "SQBRSQL005", "SQBRSQL006", "SQBRSQL008"}
)
_MAX_PASSES: int = 128
_APPLIED: str = "applied"
_CONDITIONLESS_JOIN_CODE: str = "SQBRSQL003"
_SNOWFLAKE_DIALECT: str = "snowflake"


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
    model_paths: frozenset[Path] = frozenset(model.file_path for model in inputs.model_files)
    baseline: CompiledProject | None = None
    seen: set[tuple[tuple[Path, str], ...]] = set()
    for _ in range(_MAX_PASSES):
        state: tuple[tuple[Path, str], ...] = tuple(sorted(current.items()))
        if state in seen:
            return _decline(files=files, reports=reports, reason="Rule fixes did not converge")
        seen.add(state)
        result: LintRunResult = run_lint(
            project_dir=project_dir,
            config=replace(config, enabled_native_rules=("SQBRSQL",)),
            value_renderer=adapter,
            discovered_inputs=inputs,
            source_files=current,
            selected_paths=frozenset(current),
        )
        edits: dict[Path, list[LintEdit]] = {}
        pending: list[RuleFixResult] = []
        remaining: list[RuleFixResult] = []
        for violation in result.violations:
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
            return current, tuple(reports + remaining), []
        candidate: dict[Path, str] = dict(current)
        for path, path_edits in edits.items():
            contents: str = candidate[path]
            for edit in sorted(path_edits, key=lambda item: item.start, reverse=True):
                contents = contents[: edit.start] + edit.replacement + contents[edit.end :]
            candidate[path] = contents
        candidate_inputs: DiscoveredProjectInputs = _updated_inputs(inputs=inputs, files=candidate)
        try:
            if baseline is None:
                baseline = compile_project(discovered_inputs=discovered_inputs, adapter=adapter)
            compiled: CompiledProject = compile_project(
                discovered_inputs=candidate_inputs, adapter=adapter
            )
            valid: bool = _equivalent(before=baseline, after=compiled)
        except Exception:
            valid = False
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


def _equivalent(*, before: CompiledProject, after: CompiledProject) -> bool:
    if any(diagnostic.is_error for diagnostic in (*before.diagnostics, *after.diagnostics)):
        return False
    if len(before.models) != len(after.models):
        return False
    after_models: dict[CompiledObjectKey, CompiledModel] = {
        model.key: model for model in after.models
    }
    for model in before.models:
        candidate: CompiledModel | None = after_models.get(model.key)
        if (
            candidate is None
            or model.inferred_columns is None
            or candidate.inferred_columns is None
            or model.fast_lineage_columns is None
            or candidate.fast_lineage_columns is None
            or model.inferred_columns != candidate.inferred_columns
            or model.deps != candidate.deps
            or tuple(model.fast_lineage_columns) != tuple(candidate.fast_lineage_columns)
        ):
            return False
    return True


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
