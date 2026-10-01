"""Conservative, compiler-verified fixed-point Rule repair planning."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field, replace
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
from sqlbuild.lint.types import RuleFixStatus

_SAFE_RULES: frozenset[str] = frozenset(
    {
        "SQBRSQL002",
        "SQBRSQL003",
        "SQBRSQL005",
        "SQBRSQL006",
        "SQBRSQL008",
        "SQBRSQL017",
        "SQBRSQL025",
    }
)
_MAX_PASSES: int = 128
_APPLIED: str = "applied"
_CONDITIONLESS_JOIN_CODE: str = "SQBRSQL003"
_SNOWFLAKE_DIALECT: str = "snowflake"
_APPLIED_REASON: str = "Meaning-preserving rewrite; compiler invariants verified"
_VERIFICATION_FAILURE: str = (
    "Compilation could not prove unchanged output columns, types, dependencies and lineage"
)


@dataclass
class _FixSession:
    """One fixed-point run that verifies each file's edits and reverts only failing files."""

    project_dir: Path
    original: dict[Path, str]
    config: LintConfig
    adapter: BaseAdapter
    inputs: DiscoveredProjectInputs
    reports: list[RuleFixResult] = field(default_factory=list)
    blocked: set[Path] = field(default_factory=set)
    baseline: CompiledProject | None = None

    def run(self) -> tuple[dict[Path, str], tuple[RuleFixResult, ...], list[LintViolation]]:
        current: dict[Path, str] = dict(self.original)
        model_paths: frozenset[Path] = frozenset(
            model.file_path for model in self.inputs.model_files
        )
        seen: set[tuple[tuple[Path, str], ...]] = set()
        for _ in range(_MAX_PASSES):
            state: tuple[tuple[Path, str], ...] = tuple(sorted(current.items()))
            if state in seen:
                return self._decline(reason="Rule fixes did not converge")
            seen.add(state)
            edits, pending, remaining = self._plan_pass(files=current, model_paths=model_paths)
            if not edits:
                return current, tuple(self.reports + remaining), self._blocked_faults()
            verified: dict[Path, str] | None = self._verify_pass(
                current=current, edits=edits, pending=pending
            )
            if verified is None:
                self.reports.extend(pending)
                return self._decline(reason=_VERIFICATION_FAILURE)
            current = verified
        return self._decline(reason="Rule fix pass limit exceeded")

    def _plan_pass(
        self, *, files: dict[Path, str], model_paths: frozenset[Path]
    ) -> tuple[dict[Path, list[LintEdit]], list[RuleFixResult], list[RuleFixResult]]:
        result: LintRunResult = run_lint(
            project_dir=self.project_dir,
            config=replace(self.config, enabled_native_rules=("SQBRSQL",)),
            value_renderer=self.adapter,
            discovered_inputs=_updated_inputs(inputs=self.inputs, files=files),
            source_files=files,
            selected_paths=frozenset(files),
        )
        edits: dict[Path, list[LintEdit]] = {}
        pending: list[RuleFixResult] = []
        remaining: list[RuleFixResult] = []
        for violation in result.violations:
            if not violation.code.startswith("SQBRSQL"):
                continue
            reason: str | None = self._refusal(violation=violation, model_paths=model_paths)
            if reason is not None or violation.fix is None:
                remaining.append(
                    _report(
                        violation=violation,
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
            pending.append(_report(violation=violation, status="applied", reason=_APPLIED_REASON))
        return edits, pending, remaining

    def _refusal(self, *, violation: LintViolation, model_paths: frozenset[Path]) -> str | None:
        if violation.file_path in self.blocked:
            return _VERIFICATION_FAILURE
        if violation.file_path not in model_paths:
            return "Compiler-verified Rule fixes currently require a model SQL body"
        if violation.fix is not None and violation.code not in _SAFE_RULES:
            return "This proposed rewrite is not proven meaning-preserving in this dialect"
        if violation.code == _CONDITIONLESS_JOIN_CODE and self.config.dialect != _SNOWFLAKE_DIALECT:
            return "Conditionless JOIN equivalence is only established for Snowflake"
        return violation.fix_unavailable_reason

    def _verify_pass(
        self,
        *,
        current: dict[Path, str],
        edits: dict[Path, list[LintEdit]],
        pending: list[RuleFixResult],
    ) -> dict[Path, str] | None:
        """Accept every file whose edits verify; revert failing files to their originals."""

        candidate: dict[Path, str] = _with_edits(files=current, edits=edits)
        if self._equivalent_to_baseline(files=candidate):
            self.reports.extend(pending)
            return candidate
        failing: set[Path] = {
            path
            for path in edits
            if not self._equivalent_to_baseline(
                files=_with_edits(files=current, edits={path: edits[path]})
            )
        }
        if not failing:
            return None
        self.blocked.update(failing)
        reverted: dict[Path, str] = {
            path: self.original[path] if path in self.blocked else contents
            for path, contents in current.items()
        }
        accepted: dict[Path, list[LintEdit]] = {
            path: path_edits for path, path_edits in edits.items() if path not in failing
        }
        candidate = _with_edits(files=reverted, edits=accepted)
        if not self._equivalent_to_baseline(files=candidate):
            return None
        self.reports[:] = [
            _refused(report=report) if report.file_path in self.blocked else report
            for report in (*self.reports, *pending)
        ]
        return candidate

    def _equivalent_to_baseline(self, *, files: dict[Path, str]) -> bool:
        try:
            if self.baseline is None:
                self.baseline = compile_project(discovered_inputs=self.inputs, adapter=self.adapter)
            compiled: CompiledProject = compile_project(
                discovered_inputs=_updated_inputs(inputs=self.inputs, files=files),
                adapter=self.adapter,
            )
            valid: bool = _equivalent(
                before=self.baseline,
                after=compiled,
                affected=_affected_models(
                    project=self.baseline,
                    changed=frozenset(
                        path for path, contents in files.items() if contents != self.original[path]
                    ),
                    project_dir=self.project_dir,
                ),
            )
        except Exception:
            valid = False
        return valid

    def _blocked_faults(self) -> list[LintViolation]:
        return [_verification_fault(path=path) for path in sorted(self.blocked)]

    def _decline(
        self, *, reason: str
    ) -> tuple[dict[Path, str], tuple[RuleFixResult, ...], list[LintViolation]]:
        affected: set[Path] = {
            report.file_path for report in self.reports if report.status == _APPLIED
        } | self.blocked
        return (
            self.original,
            tuple(_refused(report=report, reason=reason) for report in self.reports),
            [_verification_fault(path=path, reason=reason) for path in sorted(affected)],
        )


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
    session: _FixSession = _FixSession(
        project_dir=project_dir,
        original=files,
        config=config,
        adapter=adapter,
        inputs=discovered_inputs,
    )
    return session.run()


def _with_edits(*, files: dict[Path, str], edits: dict[Path, list[LintEdit]]) -> dict[Path, str]:
    candidate: dict[Path, str] = dict(files)
    for path, path_edits in edits.items():
        contents: str = candidate[path]
        for edit in sorted(path_edits, key=lambda item: item.start, reverse=True):
            contents = contents[: edit.start] + edit.replacement + contents[edit.end :]
        candidate[path] = contents
    return candidate


def _report(*, violation: LintViolation, status: RuleFixStatus, reason: str) -> RuleFixResult:
    return RuleFixResult(
        file_path=violation.file_path,
        code=violation.code,
        line=violation.line,
        status=status,
        reason=reason,
    )


def _refused(*, report: RuleFixResult, reason: str = _VERIFICATION_FAILURE) -> RuleFixResult:
    if report.status != _APPLIED:
        return report
    return replace(report, status="refused", reason=reason)


def _verification_fault(*, path: Path, reason: str = _VERIFICATION_FAILURE) -> LintViolation:
    return LintViolation(
        file_path=path,
        line=1,
        column=1,
        code="format-fix-verification-failed",
        message=reason,
        severity=VIOLATION_SEVERITY_FAULT,
        engine=LINT_ENGINE_NATIVE,
        remediation="Restructure the SQL manually and recompile; the original file was retained.",
    )


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


def _affected_models(
    *, project: CompiledProject, changed: frozenset[Path], project_dir: Path
) -> frozenset[CompiledObjectKey]:
    """Models in changed files and everything downstream; all models if a file is unmatched."""

    resolved: frozenset[Path] = frozenset(path.resolve() for path in changed)
    affected: set[CompiledObjectKey] = {
        model.key
        for model in project.models
        if (project_dir / model.relative_path).resolve() in resolved
    }
    if len(affected) < len(resolved):
        return frozenset(model.key for model in project.models)
    grew: bool = True
    while grew:
        grew = False
        for model in project.models:
            if model.key not in affected and any(dep in affected for dep in model.deps):
                affected.add(model.key)
                grew = True
    return frozenset(affected)


def _equivalent(
    *, before: CompiledProject, after: CompiledProject, affected: frozenset[CompiledObjectKey]
) -> bool:
    """Affected models must prove unchanged columns, dependencies and lineage."""

    if any(diagnostic.is_error for diagnostic in (*before.diagnostics, *after.diagnostics)):
        return False
    if {model.key for model in before.models} != {model.key for model in after.models}:
        return False
    after_models: dict[CompiledObjectKey, CompiledModel] = {
        model.key: model for model in after.models
    }
    for model in before.models:
        if model.key not in affected:
            continue
        candidate: CompiledModel = after_models[model.key]
        if (
            model.inferred_columns is None
            or candidate.inferred_columns is None
            or model.fast_lineage_columns is None
            or candidate.fast_lineage_columns is None
            or model.inferred_columns != candidate.inferred_columns
            or model.deps != candidate.deps
            or tuple(model.fast_lineage_columns) != tuple(candidate.fast_lineage_columns)
        ):
            return False
    return True
