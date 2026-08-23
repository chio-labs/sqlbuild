"""Test helpers for custom kata rules."""

from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.kata_engine.constants import MIN_CUSTOM_RULE_TEST_CASES
from sqlbuild.kata_engine.models import KataCacheConfig, KataConfig
from tests.unit.src.sqlbuild.kata_engine._helpers.engine._test_types import CustomRuleTestCase
from tests.unit.src.sqlbuild.kata_engine.main.evaluate.helpers import build_project

_MODEL_SQL: str = "WITH final AS (SELECT 1 AS id) SELECT id FROM final"


def write_rule(*, root: Path, body: str) -> Path:
    path: Path = root / "kata" / "rules" / "custom.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "\n".join(
            (
                "from sqlbuild.kata import RuleContext, kata",
                "",
                "@kata(",
                '    code="XSQBKT001",',
                '    family="project",',
                '    slug="test-rule",',
                '    message="test rule fault",',
                '    remediation="Fix this model at its models/<domain>/ path.",',
                ")",
                "def check(*, model, ctx: RuleContext):",
                f"    {body}",
                "",
            )
        ),
        encoding="utf-8",
    )
    return path.relative_to(root)


def custom_rule_inputs(
    *, tmp_path: Path, test_case: CustomRuleTestCase
) -> tuple[CompiledProject, KataConfig]:
    rule_path: Path = write_rule(root=tmp_path, body=test_case.body)
    project: CompiledProject = build_project(
        name="market__mart__prices",
        relative_path="models/mart/market__mart__prices.sql",
        sql=_MODEL_SQL,
        config_values={},
    )
    config: KataConfig = KataConfig(
        select=("XSQBKT001",),
        rule_paths=(rule_path.as_posix(),),
        thresholds={MIN_CUSTOM_RULE_TEST_CASES: test_case.minimum_custom_rule_cases},
        cache=KataCacheConfig(require_cacheable=test_case.require_cacheable),
    )
    return project, config
