"""Reject local opt-outs before Rule selection, caching, or suppression."""

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.lint.main.collect_project_files import collect_project_files
from sqlbuild.lint.main.find_suppression_overrides import find_suppression_overrides
from sqlbuild.rule_engine.models import Finding, RulesConfig


def override_findings(
    *, config: RulesConfig, discovered_inputs: DiscoveredProjectInputs, project_dir: Path
) -> tuple[Finding, ...]:
    if config.allow_model_overrides:
        return ()
    findings: list[Finding] = []
    for model in discovered_inputs.model_files:
        if model.header_values.get("sql_analysis") is False:
            findings.append(
                Finding(
                    code="rules-model-override",
                    path=model.relative_path,
                    line=1,
                    column=1,
                    message="MODEL (sql_analysis false) is forbidden by allow_model_overrides = false",
                    remediation="Remove the MODEL sql_analysis override and resolve compiler findings.",
                )
            )
    files: dict[Path, str] = collect_project_files(project_dir=project_dir, selected_paths=None)
    for violation in find_suppression_overrides(contents_by_path=files):
        findings.append(
            Finding(
                code="rules-model-override",
                path=violation.file_path.relative_to(project_dir),
                line=violation.line,
                column=violation.column,
                message=violation.message,
                remediation=violation.remediation or "Remove the inline suppression.",
            )
        )
    return tuple(findings)
