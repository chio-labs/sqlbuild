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
    check: str = {
        2: (
            "(sum(1 for node in ctx.sql.for_model(model).expanded.polyglot_ast().walk() "
            'if str(getattr(node, "key", "")).lower() == "select") '
            '>= 1 if model.name == "model_00000" else True)'
        ),
        3: "len(ctx.graph.dependencies(model)) >= 0",
        4: "len(ctx.graph.dependents(model)) >= 0",
        5: "len(ctx.columns.declared(model)) >= 0",
        6: "ctx.columns.names(model) is None or len(ctx.columns.names(model) or ()) >= 0",
        7: "isinstance(ctx.contracts.enforced(model), bool)",
        8: "len(ctx.contracts.grain(model)) >= 0",
        9: "len(ctx.tests.for_model(model)) >= 0",
        10: "len(ctx.audits.for_model(model)) >= 0",
        11: "bool(ctx.sql.for_model(model).authored.source)",
        12: "bool(ctx.sql.for_model(model).expanded.source)",
        13: "len(ctx.declarations.enums) >= 0",
        14: "len(ctx.declarations.constants) >= 0",
        15: "len(ctx.project.tree.relative_parts(path=model.path, under='models')) >= 1",
        16: "bool(model.materialization)",
        17: "len(ctx.project.sources) >= 0",
        18: "len(ctx.project.seeds) >= 0",
        19: "len(ctx.project.functions) >= 0",
        20: "all(len(dependency.path.parts) >= 2 for dependency in ctx.graph.dependencies(model))",
    }.get(index, "len(ctx.graph.dependencies(model)) >= 0")
    return f"""@rule(
    code="XSQBRB{index:03d}",
    slug="bounded-project-fact-{index:03d}",
    message="Compiled model fact does not satisfy the benchmark rule",
    remediation="Correct the compiled resource metadata.",
    enabled_by_default=True,
)
def check_{index:03d}(*, model: Model, ctx: RuleContext) -> list[Finding]:
    valid = {check}
    return [] if valid else [ctx.finding(subject=model)]

"""
