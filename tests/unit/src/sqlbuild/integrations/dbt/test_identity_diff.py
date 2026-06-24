from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sqlbuild.integrations.dbt.helpers.identity_diff.core import (
    build_dbt_identity_diff_result,
    format_dbt_identity_diff_json,
    render_dbt_identity_diff_result,
)
from sqlbuild.integrations.dbt.helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.main.identity_diff import build_dbt_identity_diff_output
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandResult,
    DbtIdentityDiffResult,
    DbtReuseFromCompileResult,
)
from sqlbuild.spec.models.project import DbtReuseFromConfig
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtIdentityDiffProgressTestCase,
    DbtIdentityDiffTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_identity_diff_manifest_model_node,
    build_manifest_data,
)

IDENTITY_DIFF_TEST_CASES: tuple[DbtIdentityDiffTestCase, ...] = (
    DbtIdentityDiffTestCase(
        description="reports would reuse for identical identity",
        current_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.orders", checksum="same", raw_code="select 1 as order_id"
            ),
        ),
        ref_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.orders", checksum="same", raw_code="select 1 as order_id"
            ),
        ),
        selected_unique_ids=("model.analytics.orders",),
        expected_output_fragments=("Selected (1)", "WOULD-REUSE", "No identity differences"),
        expected_json_fragments=('"verdict": "would_reuse"',),
    ),
    DbtIdentityDiffTestCase(
        description="reports direct sql cause",
        current_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.orders", checksum="new", raw_code="select 2 as order_id"
            ),
        ),
        ref_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.orders", checksum="old", raw_code="select 1 as order_id"
            ),
        ),
        selected_unique_ids=("model.analytics.orders",),
        expected_output_fragments=(
            "Selected (1)",
            "Causes (1)",
            "query",
            "-select 1 as order_id",
            "+select 2 as order_id",
        ),
        expected_json_fragments=('"query"', '"model.analytics.orders"'),
    ),
    DbtIdentityDiffTestCase(
        description="collapses downstream and reports upstream sql cause",
        current_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.stg_orders", checksum="new", raw_code="select 2 as order_id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.fact_orders",
                checksum="fact",
                raw_code="select * from stg_orders",
                depends_on_nodes=("model.analytics.stg_orders",),
            ),
        ),
        ref_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.stg_orders", checksum="old", raw_code="select 1 as order_id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.fact_orders",
                checksum="fact",
                raw_code="select * from stg_orders",
                depends_on_nodes=("model.analytics.stg_orders",),
            ),
        ),
        selected_unique_ids=("model.analytics.fact_orders",),
        expected_output_fragments=("Inherited only (1)", "stg_orders", "query"),
        expected_json_fragments=('"inherited_only"', '"query"'),
    ),
    DbtIdentityDiffTestCase(
        description="reports config and schema causes",
        current_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.orders",
                checksum="new",
                raw_code="select 1 as order_id",
                materialized="table",
                columns={"order_id": {"name": "order_id", "data_type": "integer"}},
            ),
        ),
        ref_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.orders",
                checksum="old",
                raw_code="select 1 as order_id",
                materialized="view",
                columns={"order_id": {"name": "order_id", "data_type": "varchar"}},
            ),
        ),
        selected_unique_ids=("model.analytics.orders",),
        expected_output_fragments=("config", "schema", "materialized", "data_type"),
        expected_json_fragments=('"config"', '"schema"'),
    ),
    DbtIdentityDiffTestCase(
        description="reports multiple independent upstream causes",
        current_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.left", checksum="left_new", raw_code="select 10 as id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.right", checksum="right_new", raw_code="select 20 as id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.joined",
                checksum="joined",
                raw_code="select * from left join right using (id)",
                depends_on_nodes=("model.analytics.left", "model.analytics.right"),
            ),
        ),
        ref_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.left", checksum="left_old", raw_code="select 1 as id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.right", checksum="right_old", raw_code="select 2 as id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.joined",
                checksum="joined",
                raw_code="select * from left join right using (id)",
                depends_on_nodes=("model.analytics.left", "model.analytics.right"),
            ),
        ),
        selected_unique_ids=("model.analytics.joined",),
        expected_output_fragments=("Causes (2)", "left", "right"),
        expected_json_fragments=('"model.analytics.left"', '"model.analytics.right"'),
    ),
    DbtIdentityDiffTestCase(
        description="reports upstream set change",
        current_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.base", checksum="base", raw_code="select 1 as id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.orders",
                checksum="new",
                raw_code="select * from base",
                depends_on_nodes=("model.analytics.base",),
            ),
        ),
        ref_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.base", checksum="base", raw_code="select 1 as id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.orders", checksum="old", raw_code="select * from base"
            ),
        ),
        selected_unique_ids=("model.analytics.orders",),
        expected_output_fragments=("upstream set", "+ model.analytics.base"),
        expected_json_fragments=('"upstream_set"', '"model.analytics.base"'),
    ),
    DbtIdentityDiffTestCase(
        description="reports deep root cause with sql diff",
        current_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.root", checksum="root_new", raw_code="select 2 as id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.mid_1",
                checksum="mid_1",
                raw_code="select * from root",
                depends_on_nodes=("model.analytics.root",),
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.mid_2",
                checksum="mid_2",
                raw_code="select * from mid_1",
                depends_on_nodes=("model.analytics.mid_1",),
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.mid_3",
                checksum="mid_3",
                raw_code="select * from mid_2",
                depends_on_nodes=("model.analytics.mid_2",),
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.selected",
                checksum="selected",
                raw_code="select * from mid_3",
                depends_on_nodes=("model.analytics.mid_3",),
            ),
        ),
        ref_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.root", checksum="root_old", raw_code="select 1 as id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.mid_1",
                checksum="mid_1",
                raw_code="select * from root",
                depends_on_nodes=("model.analytics.root",),
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.mid_2",
                checksum="mid_2",
                raw_code="select * from mid_1",
                depends_on_nodes=("model.analytics.mid_1",),
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.mid_3",
                checksum="mid_3",
                raw_code="select * from mid_2",
                depends_on_nodes=("model.analytics.mid_2",),
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.selected",
                checksum="selected",
                raw_code="select * from mid_3",
                depends_on_nodes=("model.analytics.mid_3",),
            ),
        ),
        selected_unique_ids=("model.analytics.selected",),
        expected_output_fragments=("Inherited only (4)", "root", "-select 1 as id"),
        expected_json_fragments=('"model.analytics.root"', '"query"'),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    IDENTITY_DIFF_TEST_CASES,
    ids=[case.description for case in IDENTITY_DIFF_TEST_CASES],
)
def test_given_current_and_ref_manifests_when_building_identity_diff_then_reports_expected_causes(
    test_case: DbtIdentityDiffTestCase,
) -> None:
    current_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=test_case.current_nodes)
    )
    ref_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=test_case.ref_nodes)
    )

    result: DbtIdentityDiffResult = build_dbt_identity_diff_result(
        current_manifest=current_manifest,
        ref_manifest=ref_manifest,
        selected_unique_ids=test_case.selected_unique_ids,
        against="main",
    )
    rendered: str = render_dbt_identity_diff_result(
        result=result,
        quiet=False,
        show_inherited=False,
        show_paths=False,
        use_color=False,
    )
    rendered_json: str = format_dbt_identity_diff_json(result)
    json.loads(rendered_json)

    for fragment in test_case.expected_output_fragments:
        assert fragment in rendered
    for fragment in test_case.expected_json_fragments:
        assert fragment in rendered_json
    for fragment in test_case.expected_absent_fragments:
        assert fragment not in rendered


@pytest.mark.parametrize(
    "test_case",
    [
        DbtIdentityDiffTestCase(
            description="suppresses very large changed sql diff",
            current_nodes=(
                build_identity_diff_manifest_model_node(
                    "model.analytics.large_sql",
                    checksum="new",
                    raw_code="\n".join(
                        f"select {index} as c_{index}, '{'x' * 80}' as payload"
                        for index in range(2600, 5200)
                    ),
                ),
            ),
            ref_nodes=(
                build_identity_diff_manifest_model_node(
                    "model.analytics.large_sql",
                    checksum="old",
                    raw_code="\n".join(
                        f"select {index} as c_{index}, '{'y' * 80}' as payload"
                        for index in range(2600)
                    ),
                ),
            ),
            selected_unique_ids=("model.analytics.large_sql",),
            expected_output_fragments=("SQL differs", "full diff suppressed", "--max-diff"),
            expected_json_fragments=(),
            expected_absent_fragments=("-select 0 as c_0", "+select 2600 as c_2600"),
        )
    ],
    ids=["suppresses very large changed sql diff"],
)
def test_given_large_changed_sql_when_rendering_identity_diff_then_suppresses_expensive_diff(
    test_case: DbtIdentityDiffTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=test_case.current_nodes)
    )
    ref_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=test_case.ref_nodes)
    )

    def fail_format_query_diff(previous_query: str, current_query: str) -> tuple[str, ...]:
        raise AssertionError("large SQL should not call format_query_diff")

    monkeypatch.setattr(
        "sqlbuild.integrations.dbt.helpers.identity_diff.core.format_query_diff",
        fail_format_query_diff,
    )

    result: DbtIdentityDiffResult = build_dbt_identity_diff_result(
        current_manifest=current_manifest,
        ref_manifest=ref_manifest,
        selected_unique_ids=test_case.selected_unique_ids,
        against="main",
    )
    rendered: str = render_dbt_identity_diff_result(
        result=result,
        quiet=False,
        show_inherited=False,
        show_paths=False,
        use_color=False,
    )

    for fragment in test_case.expected_output_fragments:
        assert fragment in rendered
    for fragment in test_case.expected_absent_fragments:
        assert fragment not in rendered


@pytest.mark.parametrize(
    "test_case",
    [
        DbtIdentityDiffTestCase(
            description="quiet output suppresses diff bodies",
            current_nodes=(
                build_identity_diff_manifest_model_node(
                    "model.analytics.orders", checksum="new", raw_code="select 2 as order_id"
                ),
            ),
            ref_nodes=(
                build_identity_diff_manifest_model_node(
                    "model.analytics.orders", checksum="old", raw_code="select 1 as order_id"
                ),
            ),
            selected_unique_ids=("model.analytics.orders",),
            expected_output_fragments=("Causes (1)", "query"),
            expected_json_fragments=(),
        )
    ],
    ids=["quiet output suppresses diff bodies"],
)
def test_given_quiet_identity_diff_when_rendering_then_suppresses_diff_bodies(
    test_case: DbtIdentityDiffTestCase,
) -> None:
    current_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=test_case.current_nodes)
    )
    ref_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=test_case.ref_nodes)
    )

    result: DbtIdentityDiffResult = build_dbt_identity_diff_result(
        current_manifest=current_manifest,
        ref_manifest=ref_manifest,
        selected_unique_ids=test_case.selected_unique_ids,
        against="main",
    )
    rendered: str = render_dbt_identity_diff_result(
        result=result,
        quiet=True,
        show_inherited=False,
        show_paths=False,
        use_color=False,
    )

    for fragment in test_case.expected_output_fragments:
        assert fragment in rendered
    assert "-select 1 as order_id" not in rendered
    assert "+select 2 as order_id" not in rendered


@pytest.mark.parametrize(
    "test_case",
    [
        DbtIdentityDiffTestCase(
            description="shared upstream cause is rendered once for multiple selected nodes",
            current_nodes=(
                build_identity_diff_manifest_model_node(
                    "model.analytics.shared_source", checksum="new", raw_code="select 2 as id"
                ),
                build_identity_diff_manifest_model_node(
                    "model.analytics.left_selected",
                    checksum="left",
                    raw_code="select * from shared_source",
                    depends_on_nodes=("model.analytics.shared_source",),
                ),
                build_identity_diff_manifest_model_node(
                    "model.analytics.right_selected",
                    checksum="right",
                    raw_code="select * from shared_source",
                    depends_on_nodes=("model.analytics.shared_source",),
                ),
            ),
            ref_nodes=(
                build_identity_diff_manifest_model_node(
                    "model.analytics.shared_source", checksum="old", raw_code="select 1 as id"
                ),
                build_identity_diff_manifest_model_node(
                    "model.analytics.left_selected",
                    checksum="left",
                    raw_code="select * from shared_source",
                    depends_on_nodes=("model.analytics.shared_source",),
                ),
                build_identity_diff_manifest_model_node(
                    "model.analytics.right_selected",
                    checksum="right",
                    raw_code="select * from shared_source",
                    depends_on_nodes=("model.analytics.shared_source",),
                ),
            ),
            selected_unique_ids=(
                "model.analytics.left_selected",
                "model.analytics.right_selected",
            ),
            expected_output_fragments=("Causes (1)", "affects: left_selected, right_selected"),
            expected_json_fragments=(),
        )
    ],
    ids=["shared upstream cause is rendered once"],
)
def test_given_shared_upstream_when_building_identity_diff_then_diffs_cause_once(
    test_case: DbtIdentityDiffTestCase,
) -> None:
    current_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=test_case.current_nodes)
    )
    ref_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=test_case.ref_nodes)
    )

    result: DbtIdentityDiffResult = build_dbt_identity_diff_result(
        current_manifest=current_manifest,
        ref_manifest=ref_manifest,
        selected_unique_ids=test_case.selected_unique_ids,
        against="main",
    )
    rendered: str = render_dbt_identity_diff_result(
        result=result,
        quiet=False,
        show_inherited=False,
        show_paths=False,
        use_color=False,
    )

    assert len(result.causes) == 1
    assert result.causes[0].unique_id == "model.analytics.shared_source"
    assert result.causes[0].affects_selected == test_case.selected_unique_ids
    for fragment in test_case.expected_output_fragments:
        assert fragment in rendered


@pytest.mark.parametrize(
    "test_case",
    [
        DbtIdentityDiffTestCase(
            description=(
                "show inherited and paths expose pass-through lineage without duplicate paths"
            ),
            current_nodes=(
                build_identity_diff_manifest_model_node(
                    "model.analytics.root", checksum="root_new", raw_code="select 2 as id"
                ),
                build_identity_diff_manifest_model_node(
                    "model.analytics.mid",
                    checksum="mid",
                    raw_code="select * from root",
                    depends_on_nodes=("model.analytics.root",),
                ),
                build_identity_diff_manifest_model_node(
                    "model.analytics.selected",
                    checksum="selected",
                    raw_code="select * from mid",
                    depends_on_nodes=("model.analytics.mid",),
                ),
            ),
            ref_nodes=(
                build_identity_diff_manifest_model_node(
                    "model.analytics.root", checksum="root_old", raw_code="select 1 as id"
                ),
                build_identity_diff_manifest_model_node(
                    "model.analytics.mid",
                    checksum="mid",
                    raw_code="select * from root",
                    depends_on_nodes=("model.analytics.root",),
                ),
                build_identity_diff_manifest_model_node(
                    "model.analytics.selected",
                    checksum="selected",
                    raw_code="select * from mid",
                    depends_on_nodes=("model.analytics.mid",),
                ),
            ),
            selected_unique_ids=("model.analytics.selected",),
            expected_output_fragments=(
                "Cause paths (1)",
                "selected <- mid <- root",
                "mid",
                "upstream only",
            ),
            expected_json_fragments=(),
        )
    ],
    ids=["show inherited and paths"],
)
def test_given_pass_through_chain_when_requested_then_lists_inherited_and_one_cause_path(
    test_case: DbtIdentityDiffTestCase,
) -> None:
    current_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=test_case.current_nodes)
    )
    ref_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=test_case.ref_nodes)
    )

    result: DbtIdentityDiffResult = build_dbt_identity_diff_result(
        current_manifest=current_manifest,
        ref_manifest=ref_manifest,
        selected_unique_ids=test_case.selected_unique_ids,
        against="main",
        show_paths=True,
    )
    rendered: str = render_dbt_identity_diff_result(
        result=result,
        quiet=False,
        show_inherited=True,
        show_paths=True,
        use_color=False,
    )

    assert tuple(cause.unique_id for cause in result.causes) == ("model.analytics.root",)
    assert tuple(node.unique_id for node in result.inherited_only) == (
        "model.analytics.mid",
        "model.analytics.selected",
    )
    assert len(result.paths) == 1
    assert result.paths[0].path == (
        "model.analytics.selected",
        "model.analytics.mid",
        "model.analytics.root",
    )
    for fragment in test_case.expected_output_fragments:
        assert fragment in rendered


@pytest.mark.parametrize(
    "test_case",
    [
        DbtIdentityDiffProgressTestCase(
            description="reports every identity diff phase with timings",
            args=("--select", "orders", "--against", "main"),
            expected_progress_fragments=(
                "Parsing identity-diff arguments...",
                "Parsed identity-diff arguments. (",
                "Inspecting project configuration...",
                "Inspected project configuration. (",
                "Resolving dbt identity-diff options...",
                "Resolved dbt identity-diff options. (",
                "Compiling current dbt project...",
                "Compiled current dbt project. (",
                "Loading current dbt manifest...",
                "Loaded current dbt manifest. (",
                "Resolving dbt identity-diff selection...",
                "Resolved dbt identity-diff selection. (",
                "Compiling dbt identity ref 'main'...",
                "Compiled dbt identity ref 'main'. (",
                "Indexing dbt identity ref manifest...",
                "Indexed dbt identity ref manifest. (",
                "Building dbt identity diff...",
                "Built dbt identity diff. (",
                "Rendering dbt identity diff output...",
                "Rendered dbt identity diff output. (",
            ),
            expected_output_fragments=("dbt identity diff", "orders", "WOULD-REUSE"),
        )
    ],
    ids=["reports every identity diff phase with timings"],
)
def test_given_identity_diff_command_when_running_then_reports_each_phase(
    test_case: DbtIdentityDiffProgressTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    node: dict[str, object] = build_identity_diff_manifest_model_node(
        "model.analytics.orders",
        checksum="same",
        raw_code="select 1 as order_id",
    )
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=(node,))
    )
    manifest_contents: str = json.dumps(build_manifest_data(nodes=(node,)))

    class FakeRunner:
        def compile(self, *, options: DbtCliOptions) -> DbtCommandResult:
            return DbtCommandResult(argv=("dbt", "compile"), returncode=0)

        def ls(
            self,
            *,
            options: DbtCliOptions,
            select: tuple[str, ...],
            exclude: tuple[str, ...],
            resource_types: tuple[str, ...],
        ) -> SimpleNamespace:
            return SimpleNamespace(
                command=DbtCommandResult(argv=("dbt", "ls"), returncode=0),
                nodes=(SimpleNamespace(unique_id="model.analytics.orders"),),
            )

    discovered_inputs: SimpleNamespace = SimpleNamespace(
        project_config=SimpleNamespace(
            dbt=SimpleNamespace(
                reuse_from=DbtReuseFromConfig(git_ref="main"),
            )
        )
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.dbt.main.identity_diff.discover_project_inputs",
        lambda *, project_dir: discovered_inputs,
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.dbt.main.identity_diff.resolve_dbt_plan_options",
        lambda *, project_dir, discovered_inputs, dbt_args: DbtCliOptions(project_dir=project_dir),
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.dbt.main.identity_diff.DbtRunner",
        FakeRunner,
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.dbt.main.identity_diff.resolve_dbt_manifest_path",
        lambda *, options: Path("target/manifest.json"),
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.dbt.main.identity_diff.load_dbt_manifest_index",
        lambda *, manifest_path: manifest,
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.dbt.main.identity_diff.compile_reuse_from_manifest",
        lambda *, sqlbuild_project_dir, dbt_options, reuse_from, runner: DbtReuseFromCompileResult(
            git_ref="main",
            manifest_contents=manifest_contents,
            command=DbtCommandResult(argv=("dbt", "compile"), returncode=0),
        ),
    )
    progress_messages: list[str] = []

    output: str = build_dbt_identity_diff_output(
        project_dir=Path("/tmp/project"),
        args=test_case.args,
        use_color=False,
        on_progress=progress_messages.append,
    )

    progress_output: str = "\n".join(progress_messages)
    for fragment in test_case.expected_progress_fragments:
        assert fragment in progress_output
    for fragment in test_case.expected_output_fragments:
        assert fragment in output
