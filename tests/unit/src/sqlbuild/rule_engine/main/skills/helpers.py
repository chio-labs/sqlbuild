"""Test helpers for generated rules skills."""

from pathlib import Path


def write_custom_rule(*, root: Path) -> Path:
    path: Path = root / "rules" / "skill_rule.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """from sqlbuild.rules import Model, RuleContext, RuleOption, rule

@rule(
    code="XSQBRT105",
    slug="skill-test-rule",
    message="custom guidance message",
    remediation="Apply the custom guidance remediation.",
    options=(
        RuleOption.string(
            name="required_domain",
            default="default_domain",
            description="Domain required by the rule.",
        ),
    ),
)
def check(*, model: Model, ctx: RuleContext):
    del model, ctx
    return []
""",
        encoding="utf-8",
    )
    return path.relative_to(root)
