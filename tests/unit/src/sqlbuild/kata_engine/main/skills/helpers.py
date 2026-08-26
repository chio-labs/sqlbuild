"""Test helpers for generated kata skills."""

from pathlib import Path


def write_custom_rule(*, root: Path) -> Path:
    path: Path = root / "kata" / "rules" / "skill_rule.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        """from sqlbuild.kata import RuleContext, RuleOption, kata

@kata(
    code="XSQBKT101",
    family="project",
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
def check(*, model, ctx: RuleContext):
    del model, ctx
    return []
""",
        encoding="utf-8",
    )
    return path.relative_to(root)
