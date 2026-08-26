"""Test helpers for native kata engine boundaries."""

import json
from dataclasses import replace
from operator import attrgetter
from pathlib import Path
from typing import Any, cast

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.scopes.models import ScopeIndex
from sqlbuild.kata_engine._helpers.engine import native
from sqlbuild.kata_engine._helpers.engine.catalogue import build_catalogue
from sqlbuild.kata_engine.constants import MIN_CUSTOM_RULE_TEST_CASES
from sqlbuild.kata_engine.models import KataCacheConfig, KataConfig, KataRule
from tests.unit.src.sqlbuild.kata_engine._helpers.engine._test_types import CustomRuleTestCase
from tests.unit.src.sqlbuild.kata_engine.main.evaluate.helpers import build_project

_MODEL_SQL: str = "WITH final AS (SELECT 1 AS id) SELECT id FROM final"


def project_with_scope(*, index: ScopeIndex) -> CompiledProject:
    """Return a minimal compiled project carrying canonical scope facts."""

    project: CompiledProject = build_project(
        name="orders",
        relative_path="models/orders.sql",
        sql="SELECT 1 AS id",
        config_values={},
    )
    return replace(project, scope_index=index)


def captured_native_request(
    *, monkeypatch: pytest.MonkeyPatch, project: CompiledProject, project_dir: Path
) -> dict[str, Any]:
    """Evaluate through the Python boundary and capture the serialized request."""

    captured: dict[str, Any] = {}

    def evaluate_json(request_json: str) -> str:
        captured.update(cast(dict[str, Any], json.loads(request_json)))
        return json.dumps(
            {
                "version": 1,
                "faults": [],
                "evaluated_models": 0,
                "cache_hits": 0,
                "cache_misses": 0,
            }
        )

    monkeypatch.setattr(native._kata_native, "evaluate_json", evaluate_json)
    native.evaluate_native(
        project=project,
        config=KataConfig(),
        project_dir=project_dir,
        catalogue=(),
    )
    return captured


def write_rule(
    *,
    root: Path,
    body: str,
    enabled_by_default: bool = False,
    filename: str = "custom.py",
    code: str = "XSQBKT001",
    check_name: str = "check",
    module_import: str = "",
) -> Path:
    path: Path = root / "kata" / "rules" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            (
                "from sqlbuild.kata import RuleContext, kata",
                module_import,
                "",
                "@kata(",
                f'    code="{code}",',
                '    family="project",',
                '    slug="test-rule",',
                '    message="test rule fault",',
                '    remediation="Fix this model at its models/<domain>/ path.",',
                f"    enabled_by_default={enabled_by_default},",
                ")",
                f"def {check_name}(*, model, ctx: RuleContext):",
                f"    {body}",
                "",
            )
        ),
        encoding="utf-8",
    )
    return path.relative_to(root)


def load_custom_rule(*, root: Path, configured_path: Path) -> KataRule:
    config: KataConfig = KataConfig(rule_paths=(configured_path.as_posix(),))
    catalogue: tuple[KataRule, ...] = build_catalogue(config=config, project_dir=root)
    custom_rules: tuple[KataRule, ...] = tuple(filter(attrgetter("custom"), catalogue))
    return custom_rules[0]


def custom_rule_inputs(
    *, tmp_path: Path, test_case: CustomRuleTestCase
) -> tuple[CompiledProject, KataConfig]:
    rule_path: Path = write_rule(
        root=tmp_path,
        body=test_case.body,
        enabled_by_default=test_case.enabled_by_default,
    )
    project: CompiledProject = build_project(
        name="market__mart__prices",
        relative_path="models/mart/market__mart__prices.sql",
        sql=_MODEL_SQL,
        config_values={},
    )
    config: KataConfig = KataConfig(
        select=test_case.select,
        rule_paths=(rule_path.as_posix(),),
        thresholds={MIN_CUSTOM_RULE_TEST_CASES: test_case.minimum_custom_rule_cases},
        cache=KataCacheConfig(require_cacheable=test_case.require_cacheable),
    )
    return project, config
