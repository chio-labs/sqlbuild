"""Reject `sql_analysis false` on parseable models when the project requires SQL analysis."""

from __future__ import annotations

import re
from collections import Counter

from sqlbuild.compiler.compile.constants import UNNEEDED_SQL_ANALYSIS_OPT_OUT_CODE
from sqlbuild.compiler.compile.models import (
    CompilerDiagnostic,
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
)
from sqlbuild.errors.setting_help.main.join_helps import join_helps
from sqlbuild.errors.setting_help.main.setting_help import setting_help
from sqlbuild.errors.setting_help.main.setting_note import setting_note
from sqlbuild.presentation.main.count_noun import format_count_noun
from sqlbuild.spec.contracts.models import SourceLocation

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
