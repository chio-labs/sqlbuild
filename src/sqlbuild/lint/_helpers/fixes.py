"""Conservative, compiler-verified fixed-point Rule repair planning."""

from __future__ import annotations

import os
import tempfile
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.project import compile_project
from sqlbuild.lint._helpers.native_format import with_newline_style
from sqlbuild.lint.constants import (
    LINT_ENGINE_NATIVE,
    SAFE_RULE_FIX_CODES,
    VIOLATION_SEVERITY_FAULT,
    VIOLATION_SEVERITY_WARNING,
)
from sqlbuild.lint.exceptions import ProjectCompileError
from sqlbuild.lint.main.compile_facts import compile_facts
from sqlbuild.lint.main.compiled_relation_keys import compiled_relation_keys
from sqlbuild.lint.main.fix_verdict import fix_verdict
from sqlbuild.lint.main.run_lint import run_lint
from sqlbuild.lint.models import (
    CompileFacts,
    FixVerdict,
    FormatChange,
    LintConfig,
    LintEdit,
    LintRunResult,
    LintViolation,
    RuleFixResult,
)
from sqlbuild.lint.types import RelationKeys, RuleFixStatus

_MAX_PASSES: int = 128
_APPLIED: str = "applied"
_CONDITIONLESS_JOIN_CODE: str = "SQBRSQL003"
_SNOWFLAKE_DIALECT: str = "snowflake"
_APPLIED_REASON: str = "Meaning-preserving rewrite; compiler invariants verified"
_VERIFICATION_FAILURE: str = (
    "Compilation could not prove unchanged output columns, types, dependencies and lineage"
)
_SKIPPED_CODE: str = "format-fix-skipped"


@dataclass
class _FixSession:
    """One fixed-point run that verifies each file's edits and reverts only failing files."""

    project_dir: Path
    original: dict[Path, str]
    config: LintConfig
    adapter: BaseAdapter
    inputs: DiscoveredProjectInputs
    reports: list[RuleFixResult] = field(default_factory=list)
    blocked: dict[Path, str] = field(default_factory=dict)
    skipped: dict[Path, str] = field(default_factory=dict)
    baseline: CompiledProject | None = None
    baseline_facts: CompileFacts | None = None

    def run(self) -> tuple[dict[Path, str], tuple[RuleFixResult, ...], list[LintViolation]]:
        current: dict[Path, str] = dict(self.original)
        model_paths: frozenset[Path] = frozenset(
            model.file_path for model in self.inputs.model_files
        )
        seen: set[tuple[tuple[tuple[Path, str], ...], tuple[Path, ...]]] = set()
        for _ in range(_MAX_PASSES):
            state: tuple[tuple[tuple[Path, str], ...], tuple[Path, ...]] = (
                tuple(sorted(current.items())),
                tuple(sorted(self.blocked)),
            )
            if state in seen:
                return self._decline(reason="Rule fixes did not converge")
            seen.add(state)
            edits, pending, remaining = self._plan_pass(files=current, model_paths=model_paths)
            if not edits:
                return (
                    current,
                    (*self.reports, *_not_yet_reported(reports=self.reports, remaining=remaining)),
                    [*self._blocked_faults(), *self._skipped_warnings()],
                )
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
            config=replace(
                self.config,
                enabled_native_rules=("SQBRSQL",),
                relation_keys=self._relation_keys(),
            ),
            value_renderer=self.adapter,
            discovered_inputs=_updated_inputs(inputs=self.inputs, files=files),
            source_files=files,
            selected_paths=frozenset(files),
            skip_unexpandable=True,
        )
        self.skipped.update(result.unexpandable)
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
        if violation.file_path not in model_paths:
            return "Compiler-verified Rule fixes currently require a model SQL body"
        if violation.fix is not None and violation.code not in SAFE_RULE_FIX_CODES:
            return "This proposed rewrite is not proven meaning-preserving in this dialect"
        if violation.code == _CONDITIONLESS_JOIN_CODE and self.config.dialect != _SNOWFLAKE_DIALECT:
            return "Conditionless JOIN equivalence is only established for Snowflake"
        if violation.fix_unavailable_reason is not None or violation.fix is None:
            return violation.fix_unavailable_reason
        return self.blocked.get(violation.file_path)

    def _verify_pass(
        self,
        *,
        current: dict[Path, str],
        edits: dict[Path, list[LintEdit]],
        pending: list[RuleFixResult],
    ) -> dict[Path, str] | None:
        """Attribute failures from one compile of all edits; isolate files when none is to blame."""

        accepted: dict[Path, list[LintEdit]] = dict(edits)
        confirmed: bool = False
        while accepted:
            verdict: FixVerdict | None = self._verdict(
                files=_with_edits(files=self._unblocked(current), edits=accepted)
            )
            if verdict is not None and verdict.verified:
                confirmed = True
                break
            hits: dict[Path, str] = (
                {} if verdict is None else _failing_edits(verdict=verdict, edits=accepted)
            )
            if not hits:
                accepted = self._isolate(current=current, edits=accepted)
                break
            for path, reason in hits.items():
                self.blocked[path] = reason
                del accepted[path]
        candidate: dict[Path, str] = _with_edits(files=self._unblocked(current), edits=accepted)
        if accepted and not confirmed and not self._verified(files=candidate):
            return None
        self.reports[:] = [
            _refused(report=report, reason=self.blocked[report.file_path])
            if report.file_path in self.blocked
            else report
            for report in (*self.reports, *pending)
        ]
        return candidate

    def _isolate(
        self, *, current: dict[Path, str], edits: dict[Path, list[LintEdit]]
    ) -> dict[Path, list[LintEdit]]:
        """Check each file's edits alone and keep only the files that verify."""

        base: dict[Path, str] = self._unblocked(current)
        accepted: dict[Path, list[LintEdit]] = {}
        for path, path_edits in edits.items():
            verdict: FixVerdict | None = self._verdict(
                files=_with_edits(files=base, edits={path: path_edits})
            )
            if verdict is not None and verdict.verified:
                accepted[path] = path_edits
            else:
                self.blocked[path] = (
                    _failing_edits(verdict=verdict, edits={path: path_edits}).get(
                        path, _VERIFICATION_FAILURE
                    )
                    if verdict is not None
                    else _VERIFICATION_FAILURE
                )
        return accepted

    def _unblocked(self, files: dict[Path, str]) -> dict[Path, str]:
        return {
            path: self.original[path] if path in self.blocked else contents
            for path, contents in files.items()
        }

    def _relation_keys(self) -> RelationKeys:
        """Declared keys from the baseline compile, so determinism proofs match compile."""

        if self.baseline is None:
            try:
                self.baseline = compile_project(discovered_inputs=self.inputs, adapter=self.adapter)
            except CompileInputError:
                return {}
        return compiled_relation_keys(self.baseline)

    def _verdict(self, *, files: dict[Path, str]) -> FixVerdict | None:
        """Compare one candidate compilation with the baseline; None when it cannot compile."""

        verdict: FixVerdict | None
        try:
            if self.baseline is None:
                self.baseline = compile_project(discovered_inputs=self.inputs, adapter=self.adapter)
            if self.baseline_facts is None:
                self.baseline_facts = compile_facts(
                    project=self.baseline, project_dir=self.project_dir
                )
            compiled: CompiledProject = compile_project(
                discovered_inputs=_updated_inputs(inputs=self.inputs, files=files),
                adapter=self.adapter,
            )
            verdict = fix_verdict(
                before=self.baseline_facts,
                after=compile_facts(project=compiled, project_dir=self.project_dir),
                edited=frozenset(
                    path.resolve()
                    for path, contents in files.items()
                    if contents != self.original[path]
                ),
            )
        except Exception:
            verdict = None
        return verdict

    def _verified(self, *, files: dict[Path, str]) -> bool:
        verdict: FixVerdict | None = self._verdict(files=files)
        return verdict is not None and verdict.verified

    def _blocked_faults(self) -> list[LintViolation]:
        return [
            _verification_fault(path=path, reason=reason)
            for path, reason in sorted(self.blocked.items())
        ]

    def _skipped_warnings(self) -> list[LintViolation]:
        return [
            LintViolation(
                file_path=path,
                line=1,
                column=1,
                code=_SKIPPED_CODE,
                message=f"Rule fixes skipped this file: {reason}",
                severity=VIOLATION_SEVERITY_WARNING,
                engine=LINT_ENGINE_NATIVE,
                remediation="Fix the reported problem, then rerun `sqb format --fix`.",
            )
            for path, reason in sorted(self.skipped.items())
        ]

    def _decline(
        self, *, reason: str
    ) -> tuple[dict[Path, str], tuple[RuleFixResult, ...], list[LintViolation]]:
        affected: set[Path] = {
            report.file_path for report in self.reports if report.status == _APPLIED
        } | set(self.blocked)
        return (
            self.original,
            tuple(_refused(report=report, reason=reason) for report in self.reports),
            [
                *(_verification_fault(path=path, reason=reason) for path in sorted(affected)),
                *self._skipped_warnings(),
            ],
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


def _failing_edits(*, verdict: FixVerdict, edits: dict[Path, list[LintEdit]]) -> dict[Path, str]:
    """Failing files of a verdict among the edited files, keyed as the edits are."""

    by_resolved: dict[Path, Path] = {path.resolve(): path for path in edits}
    return {
        by_resolved[path]: reason for path, reason in verdict.failing.items() if path in by_resolved
    }


def _with_edits(*, files: dict[Path, str], edits: dict[Path, list[LintEdit]]) -> dict[Path, str]:
    candidate: dict[Path, str] = dict(files)
    for path, path_edits in edits.items():
        contents: str = candidate[path]
        for edit in sorted(path_edits, key=lambda item: item.start, reverse=True):
            contents = contents[: edit.start] + edit.replacement + contents[edit.end :]
        candidate[path] = contents
    return candidate


def _not_yet_reported(
    *, reports: list[RuleFixResult], remaining: list[RuleFixResult]
) -> list[RuleFixResult]:
    """Final-pass outcomes, minus those an earlier pass already recorded identically."""

    recorded: Counter[RuleFixResult] = Counter(reports)
    fresh: list[RuleFixResult] = []
    for report in remaining:
        if recorded[report] > 0:
            recorded[report] -= 1
        else:
            fresh.append(report)
    return fresh


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
