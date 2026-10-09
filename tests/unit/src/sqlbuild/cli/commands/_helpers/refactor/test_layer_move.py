"""The one-step `sqb mv` suggested when a model rename fails only on the layer-folder rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands._helpers.refactor.layer_move import layer_move_suggestion
from sqlbuild.cli.commands.constants import CONTIGUOUS_LAYER_FOLDERS, LAYER_FOLDERS
from sqlbuild.cli.commands.models import LayerMoveSuggestion
from sqlbuild.compiler.refactoring.models import RefactorPlan
from tests.unit.src.sqlbuild.cli.commands._helpers.refactor._test_types import (
    CommandLineQuotingTestCase,
    LayerFolderMappingTestCase,
    LayerMoveSuggestionTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.refactor.helpers import (
    build_rename_plan,
    rule_diagnostics,
)

_LAYER_CODES: tuple[str, str] = ("SQBRPROJECT102", "SQBRPROJECT105")


@pytest.mark.parametrize(
    "test_case",
    [
        LayerMoveSuggestionTestCase(
            description="int_clean to int_enriched keeps domain and sub-folders",
            old_path="models/orders/intermediate/clean/web/orders__int_clean__lines__web.sql",
            new_name="orders__int_enriched__lines__web",
            codes=_LAYER_CODES,
            expected_command=(
                "sqb mv orders__int_clean__lines__web "
                "models/orders/intermediate/enriched/web/orders__int_enriched__lines__web.sql"
            ),
            expected_folder="models/orders/intermediate/enriched",
        ),
        LayerMoveSuggestionTestCase(
            description="staging to a mart view replaces the one-segment layer folder",
            old_path="models/customers/staging/customers__stg__accounts.sql",
            new_name="customers__mart_v__accounts",
            codes=("SQBRPROJECT105",),
            expected_command=(
                "sqb mv customers__stg__accounts models/customers/mart/customers__mart_v__accounts.sql"
            ),
            expected_folder="models/customers/mart",
        ),
        LayerMoveSuggestionTestCase(
            description="a bare intermediate folder becomes the int_clean folder",
            old_path="models/orders/intermediate/orders__int_v__totals.sql",
            new_name="orders__int_clean__totals",
            codes=("SQBRPROJECT102",),
            expected_command=(
                "sqb mv orders__int_v__totals "
                "models/orders/intermediate/clean/orders__int_clean__totals.sql"
            ),
            expected_folder="models/orders/intermediate/clean",
        ),
        LayerMoveSuggestionTestCase(
            description="no layer folder in the current path uses a placeholder",
            old_path="models/orders/web/order_lines.sql",
            new_name="orders__stg__order_lines",
            codes=_LAYER_CODES,
            expected_command="sqb mv order_lines 'models/<folder>/orders__stg__order_lines.sql'",
            expected_folder=None,
        ),
        LayerMoveSuggestionTestCase(
            description="only the current layer's own folder is replaced",
            old_path="models/mart/orders/staging/orders__stg__order_lines_x.sql",
            new_name="orders__int_clean__order_lines_x",
            codes=("SQBRPROJECT102",),
            expected_command=(
                "sqb mv orders__stg__order_lines_x "
                "models/mart/orders/intermediate/clean/orders__int_clean__order_lines_x.sql"
            ),
            expected_folder="models/mart/orders/intermediate/clean",
        ),
        LayerMoveSuggestionTestCase(
            description="a path without the current layer's folder uses a placeholder",
            old_path="models/orders/mart/web/orders__stg__order_lines.sql",
            new_name="orders__int_clean__order_lines",
            codes=_LAYER_CODES,
            expected_command=(
                "sqb mv orders__stg__order_lines 'models/<folder>/orders__int_clean__order_lines.sql'"
            ),
            expected_folder=None,
        ),
        LayerMoveSuggestionTestCase(
            description="a layer without a folder mapping uses a placeholder",
            old_path="models/orders/intermediate/clean/orders__int_clean__totals.sql",
            new_name="orders__int_archive__totals",
            codes=_LAYER_CODES,
            expected_command=(
                "sqb mv orders__int_clean__totals 'models/<folder>/orders__int_archive__totals.sql'"
            ),
            expected_folder=None,
        ),
        LayerMoveSuggestionTestCase(
            description="another rule failing as well gets no suggestion",
            old_path="models/orders/intermediate/clean/orders__int_clean__totals.sql",
            new_name="orders__int_enriched__totals",
            codes=("SQBRPROJECT105", "SQBRMODEL103"),
            expected_command=None,
            expected_folder=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rename_compile_errors_when_suggesting_layer_move_then_one_step_mv_is_exact(
    test_case: LayerMoveSuggestionTestCase,
) -> None:
    plan: RefactorPlan = build_rename_plan(old_path=test_case.old_path, new_name=test_case.new_name)

    suggestion: LayerMoveSuggestion | None = layer_move_suggestion(
        plan=plan,
        diagnostics=rule_diagnostics(codes=test_case.codes, path=plan.changes[0].path),
        project_dir=None,
    )

    assert (
        getattr(suggestion, "command", None),
        getattr(suggestion, "folder", None),
    ) == (test_case.expected_command, test_case.expected_folder)


@pytest.mark.parametrize(
    "test_case",
    [
        CommandLineQuotingTestCase(
            description="posix shells get POSIX quoting",
            os_name="posix",
            project_dir="/srv/order projects/orders",
            expected_command=(
                "sqb mv orders__int_clean__lines__web "
                "models/orders/intermediate/enriched/web/orders__int_enriched__lines__web.sql "
                "--project-dir '/srv/order projects/orders'"
            ),
        ),
        CommandLineQuotingTestCase(
            description="windows gets cmd.exe quoting",
            os_name="nt",
            project_dir="C:\\order projects\\orders",
            expected_command=(
                "sqb mv orders__int_clean__lines__web "
                "models/orders/intermediate/enriched/web/orders__int_enriched__lines__web.sql "
                '--project-dir "C:\\order projects\\orders"'
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_platform_when_suggesting_layer_move_then_command_is_quoted_for_its_shell(
    test_case: CommandLineQuotingTestCase,
) -> None:
    plan: RefactorPlan = build_rename_plan(
        old_path="models/orders/intermediate/clean/web/orders__int_clean__lines__web.sql",
        new_name="orders__int_enriched__lines__web",
    )

    suggestion: LayerMoveSuggestion | None = layer_move_suggestion(
        plan=plan,
        diagnostics=rule_diagnostics(codes=_LAYER_CODES, path=plan.changes[0].path),
        project_dir=Path(test_case.project_dir),
        os_name=test_case.os_name,
    )

    assert getattr(suggestion, "command", None) == test_case.expected_command


@pytest.mark.parametrize(
    "test_case",
    [
        LayerFolderMappingTestCase(
            description="every parse_name layer, mirroring model_layers.rs and domain_layout.rs",
            expected_layers=frozenset(
                {"stg", "stg_v", "int_clean", "int_v", "int_enriched", "mart", "mart_v"}
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rule_grammar_layers_when_reading_layer_folders_then_each_layer_has_both_folders(
    test_case: LayerFolderMappingTestCase,
) -> None:
    """LAYER_FOLDERS mirrors model_layers.rs (SQBRPROJECT105); the other, domain_layout.rs (102)."""
    assert (frozenset(LAYER_FOLDERS), frozenset(CONTIGUOUS_LAYER_FOLDERS)) == (
        test_case.expected_layers,
        test_case.expected_layers,
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
