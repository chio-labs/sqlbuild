"""Public evaluation faults grouped after per-Rule suppression policy."""

from dataclasses import replace
from pathlib import Path

from sqlbuild.rule_engine.models import Finding


def group_unevaluated_findings(findings: tuple[Finding, ...]) -> tuple[Finding, ...]:
    grouped: dict[tuple[Path, str], list[Finding]] = {}
    result: list[Finding] = []
    for finding in findings:
        if not finding.unevaluated:
            result.append(finding)
            continue
        reason: str = finding.message.removeprefix(
            f"Rule {finding.code} could not be evaluated"
        ).lstrip(": ")
        grouped.setdefault((finding.path, reason), []).append(finding)
    for (_, reason), failures in grouped.items():
        affected_rules: tuple[str, ...] = tuple(sorted({failure.code for failure in failures}))
        first: Finding = min(failures, key=lambda failure: (failure.line, failure.column))
        result.append(
            replace(
                first,
                code="rules-unevaluated",
                affected_rules=affected_rules,
                message=(
                    f"{len(affected_rules)} selected Rules could not evaluate this resource: "
                    f"{reason}"
                ),
            )
        )
    return tuple(result)
