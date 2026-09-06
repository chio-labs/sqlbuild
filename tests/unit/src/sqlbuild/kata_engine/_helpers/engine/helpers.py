"""Test helpers for native kata engine boundaries."""

import json
from dataclasses import replace
from operator import attrgetter
from pathlib import Path
from typing import Any, cast

import pytest

from sqlbuild.compiler.compile.models import (
    CompiledDirectLogicSqlTestPayload,
    CompiledModelSqlTestPayload,
    CompiledObjectKey,
    CompiledProject,
    CompiledSqlTest,
    CompiledSqlTestResource,
    CompileSqlTestCte,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, SqlTestMode
from sqlbuild.compiler.discovery.models import DiscoveredSqlTestBlock, DiscoveredSqlTestFile
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

    monkeypatch.setattr(native._native, "evaluate_json", evaluate_json)
    native.evaluate_native(
        project=project,
        config=KataConfig(),
        project_dir=project_dir,
        catalogue=(),
    )
    return captured


def direct_sql_test(*, mode: SqlTestMode, name: str, block_index: int) -> CompiledSqlTest:
    test_file: DiscoveredSqlTestFile = DiscoveredSqlTestFile(
        file_path=Path(f"/private/project/tests/unit/{name}.sql"),
        relative_path=Path(f"tests/unit/{name}.sql"),
        contents="secret fixture value",
        blocks=(),
    )
    test_block: DiscoveredSqlTestBlock = DiscoveredSqlTestBlock(
        test_index=block_index,
        header_values={"name": name},
        sql_body="SELECT 'secret fixture value'",
        name=name,
        mode=mode,
    )
    return CompiledSqlTest(
        key=CompiledObjectKey(CompiledResourceType.SQL_TEST, name),
        scope_deps=(CompiledObjectKey(CompiledResourceType.MODEL, "orders"),),
        name=name,
        test_file=test_file,
        test_block=test_block,
        sql_body=test_block.sql_body,
        mode=mode,
        payload=CompiledDirectLogicSqlTestPayload(
            actual_cte=CompileSqlTestCte("__actual", "SELECT 1"),
            expected_cte=CompileSqlTestCte("__expected", "SELECT 1"),
            mode=mode,
            tested_resource_names=(name,),
        ),
        tested_resources=(CompiledSqlTestResource(kind=mode, name=name),),
    )


def model_sql_test() -> CompiledSqlTest:
    name: str = "orders: keeps paid orders"
    test_file: DiscoveredSqlTestFile = DiscoveredSqlTestFile(
        file_path=Path("/private/project/tests/unit/test_orders__keeps_paid.sql"),
        relative_path=Path("tests/unit/test_orders__keeps_paid.sql"),
        contents="secret model fixture",
        blocks=(),
    )
    test_block: DiscoveredSqlTestBlock = DiscoveredSqlTestBlock(
        test_index=1,
        header_values={"name": name},
        sql_body="SELECT 1",
        name=name,
        mode=SqlTestMode.MODEL,
    )
    return CompiledSqlTest(
        key=CompiledObjectKey(CompiledResourceType.SQL_TEST, name),
        scope_deps=(),
        name=name,
        test_file=test_file,
        test_block=test_block,
        sql_body=test_block.sql_body,
        mode=SqlTestMode.MODEL,
        payload=CompiledModelSqlTestPayload(),
        expected_model_names=("orders",),
        assertion_names=("paid",),
        assertion_target_model_names=("orders",),
        target_model_names=("orders",),
    )


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
