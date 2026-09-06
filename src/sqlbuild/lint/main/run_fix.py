"""Plan and apply deterministic native lint repairs."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models import SqlExpansionContext
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.lint._helpers.expansion import build_lint_expansion_context
from sqlbuild.lint._helpers.fixes import (
    apply_edits,
    apply_header_repairs,
    fix_record,
    lint_contents,
    planned_edits,
    write_atomically,
)
from sqlbuild.lint._helpers.project_files import collect_project_files, sort_violations
from sqlbuild.lint._helpers.suppressions import apply_suppressions
from sqlbuild.lint.constants import FIX_STATUS_SKIPPED, MAX_FIX_PASSES
from sqlbuild.lint.models import (
    FixRunResult,
    FormatChange,
    LintConfig,
    LintFixRecord,
    LintViolation,
)


def run_fix(
    *,
    project_dir: Path,
    config: LintConfig,
    value_renderer: TypedSqlValueRenderer | None = None,
    selected_paths: frozenset[Path] | None = None,
    write: bool = True,
) -> FixRunResult:
    """Apply eligible lint repairs and report findings that still require attention."""

    original: dict[Path, str] = collect_project_files(
        project_dir=project_dir, selected_paths=selected_paths
    )
    current: dict[Path, str]
    records: list[LintFixRecord]
    current, records = apply_header_repairs(files=original, config=config)
    context: SqlExpansionContext | None = (
        build_lint_expansion_context(project_dir=project_dir, value_renderer=value_renderer)
        if config.native_enabled
        else None
    )
    for _pass_index in range(MAX_FIX_PASSES):
        violations: list[LintViolation] = lint_contents(
            files=current,
            config=config,
            context=context,
        )
        retained: list[LintViolation] = apply_suppressions(
            violations=violations,
            contents_by_path=current,
        )
        edits, pass_records = planned_edits(violations=retained)
        records.extend(pass_records)
        if not edits:
            break
        updated: dict[Path, str] = apply_edits(files=current, edits=edits)
        if updated == current:
            break
        current = updated

    remaining: list[LintViolation] = apply_suppressions(
        violations=lint_contents(files=current, config=config, context=context),
        contents_by_path=current,
    )
    records.extend(
        fix_record(
            violation=violation,
            status=FIX_STATUS_SKIPPED,
            reason=violation.fix_unavailable_reason,
        )
        for violation in remaining
        if violation.fix_unavailable_reason is not None
    )
    changes: tuple[FormatChange, ...] = tuple(
        FormatChange(file_path=path, before=original[path], after=current[path])
        for path in sorted(original)
        if original[path] != current[path]
    )
    if write:
        for change in changes:
            write_atomically(path=change.file_path, contents=change.after)
    return FixRunResult(
        files_checked=len(original),
        violations=sort_violations(remaining),
        changed_files=tuple(change.file_path for change in changes),
        changes=changes,
        fixes=tuple(records),
        source_texts=current,
    )
