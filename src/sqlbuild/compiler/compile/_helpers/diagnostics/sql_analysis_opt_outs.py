"""Reject `sql_analysis false` on parseable models when the project requires SQL analysis."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.compile._helpers.analysis.validation import (
    validate_hook_sql_syntax,
    validate_sql_syntax,
)
from sqlbuild.compiler.compile.constants import UNNEEDED_SQL_ANALYSIS_OPT_OUT_CODE
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompilerDiagnostic,
    SqlAnalysisOptOutRequest,
)
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.discovery.constants import (
    PROJECT_CONFIG_FILENAME,
    REQUIRE_SQL_ANALYSIS_SETTING_KEY,
    SETTINGS_SECTION,
    SQL_ANALYSIS_CONFIG_KEY,
)
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile
from sqlbuild.errors.setting_help.main.join_helps import join_helps
from sqlbuild.errors.setting_help.main.setting_help import setting_help
from sqlbuild.errors.setting_help.main.setting_note import setting_note
from sqlbuild.presentation.main.count_noun import format_count_noun
from sqlbuild.spec.contracts.models import SettingsConfig, SourceLocation

_LEGACY_KEY: str = "sql_validation"
_SEMANTIC_CODE_PREFIX: str = "B"
_OPT_OUT_KEYS: tuple[str, ...] = (SQL_ANALYSIS_CONFIG_KEY, _LEGACY_KEY)
_HOOK_KEYS: tuple[str, ...] = ("pre_hooks", "post_hooks")
_OPT_OUT_KEY_PATTERN: re.Pattern[str] = re.compile(r"\b(?:sql_analysis|sql_validation)\b")
_FINDING_KINDS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"^B002$"), "unknown column", "unknown columns"),
    (re.compile(r"^B003$"), "ambiguous column", "ambiguous columns"),
    (re.compile(r"^B00[45]$"), "reference error", "reference errors"),
    (re.compile(r"^B101$"), "unknown function", "unknown functions"),
    (re.compile(r"^B102$"), "function arity error", "function arity errors"),
    (re.compile(r"^B216$"), "column count mismatch", "column count mismatches"),
    (re.compile(r"^B21\d$"), "type mismatch", "type mismatches"),
    (re.compile(r"^B23[0-2]$"), "grouping or window error", "grouping or window errors"),
    (re.compile(r"^B3\d\d$"), "metadata mismatch", "metadata mismatches"),
)


def rejected_sql_analysis_opt_out(request: SqlAnalysisOptOutRequest) -> SourceLocation | None:
    """Return where a model turns SQL analysis off when the project forbids it for that model."""

    settings: SettingsConfig = request.settings
    if (
        not settings.require_sql_analysis
        or not settings.sql_analysis
        or request.no_sql_validation
        or not any(request.config.values.get(key) is False for key in _OPT_OUT_KEYS)
    ):
        return None
    model_name: str = request.model_file.file_path.stem
    try:
        validate_sql_syntax(
            query_sql=request.query_sql,
            model_name=model_name,
            file_path=request.model_file.file_path,
            placeholders=request.placeholders,
        )
        for hook_name in _HOOK_KEYS:
            validate_hook_sql_syntax(
                value=request.config.values.get(hook_name),
                hook_name=hook_name,
                model_name=model_name,
                file_path=request.model_file.file_path,
                placeholders=request.placeholders,
            )
    except CompileInputError:
        return None
    return _opt_out_location(request)


def reject_unneeded_sql_analysis_opt_outs(project: CompiledProject) -> CompiledProject:
    """Replace each rejected opt-out model's findings with one error that counts them."""

    rejected: dict[str, CompiledModel] = {
        model.name: model
        for model in project.models
        if model.rejected_sql_analysis_opt_out is not None
    }
    if not rejected:
        return project
    hidden: dict[str, list[CompilerDiagnostic]] = {name: [] for name in rejected}
    kept: list[CompilerDiagnostic] = []
    for diagnostic in project.diagnostics:
        if (
            diagnostic.resource_name in hidden
            and diagnostic.resource_type in (None, CompiledResourceType.MODEL)
            and diagnostic.code.startswith(_SEMANTIC_CODE_PREFIX)
        ):
            hidden[diagnostic.resource_name].append(diagnostic)
        else:
            kept.append(diagnostic)
    kept.extend(
        _opt_out_diagnostic(model=model, hidden=tuple(hidden[name]))
        for name, model in sorted(rejected.items())
    )
    return replace(project, diagnostics=tuple(kept))


def _opt_out_diagnostic(
    *, model: CompiledModel, hidden: tuple[CompilerDiagnostic, ...]
) -> CompilerDiagnostic:
    location: SourceLocation | None = model.rejected_sql_analysis_opt_out
    return unneeded_opt_out_diagnostic(
        resource_type=CompiledResourceType.MODEL,
        kind="model",
        name=model.name,
        location=location,
        hidden=hidden,
        path_default=location is not None and location.path.name == PROJECT_CONFIG_FILENAME,
    )


def unneeded_opt_out_diagnostic(
    *,
    resource_type: CompiledResourceType,
    kind: str,
    name: str,
    location: SourceLocation | None,
    hidden: tuple[CompilerDiagnostic, ...],
    path_default: bool = False,
) -> CompilerDiagnostic:
    """One P009 error for `sql_analysis false` on SQL that parses, counting what it hid."""

    findings: str = _finding_counts(hidden)
    opt_out: str = (
        "`sql_analysis = false` from this [path_defaults] entry"
        if path_default
        else "`sql_analysis false`"
    )
    fix: str = (
        f"remove {opt_out} and fix the findings it was hiding: {findings} "
        "(run `sqb compile` to see them)"
        if findings
        else f"remove {opt_out}; it is not hiding any findings"
    )
    return CompilerDiagnostic(
        phase=DiagnosticPhase.COMPILE,
        severity=DiagnosticSeverity.ERROR,
        code=UNNEEDED_SQL_ANALYSIS_OPT_OUT_CODE,
        message=f"`sql_analysis false` is not needed for {kind} '{name}'",
        resource_type=resource_type,
        resource_name=name,
        location=location,
        notes=(
            setting_note(
                file_name=PROJECT_CONFIG_FILENAME,
                section=SETTINGS_SECTION,
                key=REQUIRE_SQL_ANALYSIS_SETTING_KEY,
                value=True,
            )
            + ", which only allows `sql_analysis false` on SQL that SQLBuild cannot parse; "
            f"this {kind} parses successfully.",
        ),
        help=join_helps(
            fix,
            setting_help(
                purpose="to allow `sql_analysis false` on any model, SQL test or audit",
                file_name=PROJECT_CONFIG_FILENAME,
                section=SETTINGS_SECTION,
                key=REQUIRE_SQL_ANALYSIS_SETTING_KEY,
                value=False,
            ),
        ),
    )


def _finding_counts(hidden: tuple[CompilerDiagnostic, ...]) -> str:
    counts: Counter[tuple[str, str]] = Counter(_finding_kind(item.code) for item in hidden)
    return ", ".join(
        format_count_noun(count=count, singular=singular, plural=plural)
        for (singular, plural), count in sorted(counts.items(), key=lambda item: -item[1])
    )


def _finding_kind(code: str) -> tuple[str, str]:
    for pattern, singular, plural in _FINDING_KINDS:
        if pattern.match(code):
            return singular, plural
    return "other finding", "other findings"


def _opt_out_location(request: SqlAnalysisOptOutRequest) -> SourceLocation:
    model_file: DiscoveredSqlModelFile = request.model_file
    if any(key in request.config.model_header_keys for key in _OPT_OUT_KEYS):
        return _text_location(path=model_file.relative_path, text=model_file.contents, start=0)
    path_key: str | None = request.config.matched_path_default
    config_text: str = (
        request.project_config_path.read_text(encoding="utf-8")
        if request.project_config_path.is_file()
        else ""
    )
    start: int = config_text.find(path_key) if path_key else -1
    return _text_location(
        path=Path(request.project_config_path.name), text=config_text, start=max(start, 0)
    )


def _text_location(*, path: Path, text: str, start: int) -> SourceLocation:
    match: re.Match[str] | None = _OPT_OUT_KEY_PATTERN.search(text, start)
    offset: int = match.start() if match is not None else 0
    line: int = text.count("\n", 0, offset) + 1
    column: int = offset - (text.rfind("\n", 0, offset) + 1) + 1
    return SourceLocation(path=path, line=line, column=column)
