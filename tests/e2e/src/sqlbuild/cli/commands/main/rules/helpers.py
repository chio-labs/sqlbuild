"""Compiler Rules end-to-end fixture helpers."""

from pathlib import Path


def write_custom_rules(*, project_dir: Path, rule_count: int = 20) -> None:
    """Write neutral custom rules that stress AST and compiler-owned facts."""

    if not 1 <= rule_count <= 999:
        raise ValueError("rule_count must be between 1 and 999")
    rule_file: Path = project_dir / "rules" / "benchmark_rules.py"
    rule_file.parent.mkdir(parents=True, exist_ok=True)
    (rule_file.parent / "benchmark_input.yaml").write_text("status: required\n", encoding="utf-8")
    header: str = "from sqlbuild.rules import Finding, Model, Project, RuleContext, rule\n\n"
    rules: list[str] = [_project_wide_rule()]
    rules.extend(_model_local_rule(index=index) for index in range(2, rule_count + 1))
    rule_file.write_text(header + "".join(rules), encoding="utf-8")


def _project_wide_rule() -> str:
    return """@rule(
    code="XSQBRB001",
    slug="tracked-project-input",
    message="Tracked Rules input is empty",
    remediation="Populate the tracked Rules input.",
    enabled_by_default=True,
)
def check_001(*, project: Project, ctx: RuleContext) -> list[Finding]:
    del project
    content = ctx.project.tree.read_text("rules/benchmark_input.yaml")
    return [] if content.strip() else [ctx.finding(subject="rules/benchmark_input.yaml")]

"""


def _model_local_rule(*, index: int) -> str:
    sql_fact: str = {
        2: (
            "(sum(1 for node in ctx.sql.for_model(model).expanded.polyglot_ast().walk() "
            'if str(getattr(node, "key", "")).lower() == "select") '
            'if model.name == "model_00000" else 1)'
        )
    }.get(index, "1")
    return f"""@rule(
    code="XSQBRB{index:03d}",
    slug="bounded-project-fact-{index:03d}",
    message="Compiled model fact does not satisfy the benchmark rule",
    remediation="Correct the compiled resource metadata.",
    enabled_by_default=True,
)
def check_{index:03d}(*, model: Model, ctx: RuleContext) -> list[Finding]:
    select_count = {sql_fact}
    evidence = (
        model.name,
        model.materialization,
        len(ctx.graph.dependencies(model)),
        len(ctx.columns.declared(model)),
        len(ctx.audits.for_model(model)),
        len(ctx.tests.for_model(model)),
        select_count,
    )
    return [] if evidence[0] and evidence[-1] >= 1 else [ctx.finding(subject=model)]

"""
