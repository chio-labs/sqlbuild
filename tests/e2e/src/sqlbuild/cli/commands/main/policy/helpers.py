"""Project Policy end-to-end fixture helpers."""

from pathlib import Path


def write_custom_policy_rules(*, project_dir: Path) -> None:
    """Write neutral custom rules that stress AST and compiler-owned facts."""

    rule_file: Path = project_dir / "policy" / "benchmark_rules.py"
    rule_file.parent.mkdir(parents=True)
    (rule_file.parent / "benchmark_input.yaml").write_text("status: required\n", encoding="utf-8")
    header: str = "from sqlbuild.policy import RuleContext, policy\n\n"
    rules: list[str] = [_project_wide_rule()]
    rules.extend(_model_local_rule(index=index) for index in range(2, 21))
    rule_file.write_text(header + "".join(rules), encoding="utf-8")


def _project_wide_rule() -> str:
    return """@policy(
    code="XSQBPB001",
    family="benchmark",
    slug="tracked-project-input",
    message="Tracked policy input is empty",
    remediation="Populate the tracked policy input.",
    enabled_by_default=True,
    project_wide=True,
)
def check_001(*, model, ctx: RuleContext):
    del model
    content = ctx.project_read_text(path="policy/benchmark_input.yaml")
    return [] if content.strip() else [ctx.path_fault()]

"""


def _model_local_rule(*, index: int) -> str:
    return f"""@policy(
    code="XSQBPB{index:03d}",
    family="benchmark",
    slug="bounded-project-fact-{index:03d}",
    message="Compiled model fact does not satisfy the benchmark policy",
    remediation="Correct the compiled resource metadata.",
    enabled_by_default=True,
)
def check_{index:03d}(*, model, ctx: RuleContext):
    select_count = sum(
        1 for node in ctx.ast.walk()
        if str(getattr(node, "key", "")).lower() == "select"
    )
    evidence = (
        model.name,
        ctx.materialization,
        len(ctx.references),
        len(ctx.declared_columns),
        ctx.declared_audit_count,
        ctx.targeting_test_count,
        select_count,
    )
    return [] if evidence[0] and evidence[-1] >= 1 else [ctx.path_fault()]

"""
