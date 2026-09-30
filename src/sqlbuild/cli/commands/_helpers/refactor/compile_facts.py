"""Offline compiles that feed and verify a refactoring."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands._helpers.compile.pipeline import analyze_compile_project
from sqlbuild.cli.commands._helpers.compile.target_writer import (
    static_sql_test_planning_diagnostics,
)
from sqlbuild.cli.commands.models import RefactorCompile
from sqlbuild.cli.commands.types import CompileLineageMode
from sqlbuild.cli.compile.models import CompileAnalysis, CompileProfileFlags
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileAnalysisSelection, CompilerDiagnostic
from sqlbuild.compiler.compile.types import DiagnosticPhase, DiagnosticSeverity
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.refactoring.models import RefactorProject
from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.spec.contracts.exceptions import SpecConfigError


def compile_for_refactor(*, project_dir: Path, no_cache: bool = False) -> RefactorCompile:
    """Compile a project the way `sqb compile` does and collect every error."""

    try:
        analysis: CompileAnalysis = analyze_compile_project(
            project_dir=project_dir,
            no_sql_validation=False,
            selected_target=None,
            lineage_mode=CompileLineageMode.NONE,
            cli_vars=None,
            profile_flags=CompileProfileFlags(),
            analysis_selection=CompileAnalysisSelection(no_cache=no_cache),
            status=None,
        )
    except (ValueError, RulesError, SpecConfigError) as error:
        return RefactorCompile(
            project=None,
            errors=(
                CompilerDiagnostic(
                    phase=DiagnosticPhase.COMPILE,
                    severity=DiagnosticSeverity.ERROR,
                    code=str(getattr(error, "code", "E001")),
                    message=str(getattr(error, "message", str(error))),
                ),
            ),
        )
    errors: list[CompilerDiagnostic] = [
        diagnostic for diagnostic in analysis.diagnostics if diagnostic.is_error
    ]
    if not errors:
        try:
            errors.extend(
                diagnostic
                for diagnostic in static_sql_test_planning_diagnostics(
                    target_dir=project_dir / "target",
                    adapter=analysis.adapter,
                    project=analysis.graph.project,
                )
                if diagnostic.is_error
            )
        except (CompileInputError, PlannerInputError) as error:
            errors.append(
                CompilerDiagnostic(
                    phase=DiagnosticPhase.TEST,
                    severity=DiagnosticSeverity.ERROR,
                    code=error.code,
                    message=str(error),
                )
            )
    return RefactorCompile(
        project=RefactorProject(
            project_dir=project_dir,
            graph=analysis.graph,
            discovered=analysis.discovered_inputs,
        ),
        errors=tuple(errors),
    )
