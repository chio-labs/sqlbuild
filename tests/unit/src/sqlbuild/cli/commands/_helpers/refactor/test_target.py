"""Reading `sqb rename` and `sqb mv` targets, with and without kind prefixes."""

from __future__ import annotations

import pytest

from sqlbuild.cli.commands._helpers.refactor.target import refactor_request_for_target
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import RefactorCommandRequest
from sqlbuild.cli.commands.types import CliCommand
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.refactoring.models import RefactorRequest
from sqlbuild.compiler.refactoring.types import RefactorOperation
from tests.unit.src.sqlbuild.cli.commands._helpers.refactor._test_types import (
    RefactorTargetErrorTestCase,
    RefactorTargetTestCase,
)

_ALL_KEYS: dict[str, CompiledObjectKey] = {
    "stg_orders": CompiledObjectKey(CompiledResourceType.MODEL, "stg_orders"),
    "raw_orders": CompiledObjectKey(CompiledResourceType.SOURCE, "raw_orders"),
    "order_types": CompiledObjectKey(CompiledResourceType.SEED, "order_types"),
    "is_completed": CompiledObjectKey(CompiledResourceType.UDF, "is_completed"),
}
_RENAME_HELP: str = (
    "write the target as <model> or <model>.<column>; the model: and column: prefixes are optional"
)


@pytest.mark.parametrize(
    "test_case",
    [
        RefactorTargetTestCase(
            description="bare model renames the model",
            command=CliCommand.RENAME,
            target="stg_orders",
            cascade=False,
            expected_operation=RefactorOperation.RENAME_MODEL,
            expected_model_name="stg_orders",
            expected_column_name=None,
        ),
        RefactorTargetTestCase(
            description="bare model column renames the column",
            command=CliCommand.RENAME,
            target="stg_orders.amount",
            cascade=True,
            expected_operation=RefactorOperation.RENAME_COLUMN,
            expected_model_name="stg_orders",
            expected_column_name="amount",
        ),
        RefactorTargetTestCase(
            description="model prefix renames the model",
            command=CliCommand.RENAME,
            target="model:stg_orders",
            cascade=False,
            expected_operation=RefactorOperation.RENAME_MODEL,
            expected_model_name="stg_orders",
            expected_column_name=None,
        ),
        RefactorTargetTestCase(
            description="column prefix renames the column",
            command=CliCommand.RENAME,
            target="column:stg_orders.amount",
            cascade=False,
            expected_operation=RefactorOperation.RENAME_COLUMN,
            expected_model_name="stg_orders",
            expected_column_name="amount",
        ),
        RefactorTargetTestCase(
            description="bare model moves the model",
            command=CliCommand.MV,
            target="stg_orders",
            cascade=False,
            expected_operation=RefactorOperation.MOVE_MODEL,
            expected_model_name="stg_orders",
            expected_column_name=None,
        ),
        RefactorTargetTestCase(
            description="model prefix moves the model",
            command=CliCommand.MV,
            target="model:stg_orders",
            cascade=False,
            expected_operation=RefactorOperation.MOVE_MODEL,
            expected_model_name="stg_orders",
            expected_column_name=None,
        ),
        RefactorTargetTestCase(
            description="unknown bare name is left for the planner to report",
            command=CliCommand.RENAME,
            target="missing_model",
            cascade=False,
            expected_operation=RefactorOperation.RENAME_MODEL,
            expected_model_name="missing_model",
            expected_column_name=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_target_when_reading_then_returns_matching_request(
    test_case: RefactorTargetTestCase,
) -> None:
    result: RefactorRequest = refactor_request_for_target(
        request=RefactorCommandRequest(
            command=test_case.command,
            target=test_case.target,
            new_name="renamed",
            destination="models/marts/",
            cascade=test_case.cascade,
        ),
        all_keys=_ALL_KEYS,
    )

    assert result.operation == test_case.expected_operation
    assert result.model_name == test_case.expected_model_name
    assert result.column_name == test_case.expected_column_name


@pytest.mark.parametrize(
    "test_case",
    [
        RefactorTargetErrorTestCase(
            description="bare source is refused and named",
            command=CliCommand.RENAME,
            target="raw_orders",
            cascade=False,
            expected_message=(
                "cannot rename 'raw_orders': raw_orders is a source; "
                "sqb rename renames models and model columns"
            ),
            expected_help=_RENAME_HELP,
        ),
        RefactorTargetErrorTestCase(
            description="source column is refused and named",
            command=CliCommand.RENAME,
            target="raw_orders.id",
            cascade=False,
            expected_message=(
                "cannot rename 'raw_orders.id': raw_orders is a source; "
                "sqb rename renames models and model columns"
            ),
            expected_help=_RENAME_HELP,
        ),
        RefactorTargetErrorTestCase(
            description="seed is refused even with its own prefix",
            command=CliCommand.RENAME,
            target="seed:order_types",
            cascade=False,
            expected_message=(
                "cannot rename 'seed:order_types': order_types is a seed; "
                "sqb rename renames models and model columns"
            ),
            expected_help=_RENAME_HELP,
        ),
        RefactorTargetErrorTestCase(
            description="function cannot be moved",
            command=CliCommand.MV,
            target="is_completed",
            cascade=False,
            expected_message=(
                "cannot move 'is_completed': is_completed is a udf; sqb mv moves models"
            ),
            expected_help="write the target as <model>; the model: prefix is optional",
        ),
        RefactorTargetErrorTestCase(
            description="prefix that contradicts the resource names what it is",
            command=CliCommand.RENAME,
            target="source:stg_orders",
            cascade=False,
            expected_message="cannot rename 'source:stg_orders': stg_orders is a model, not a source",
            expected_help=_RENAME_HELP,
        ),
        RefactorTargetErrorTestCase(
            description="column prefix without a column is refused",
            command=CliCommand.RENAME,
            target="column:stg_orders",
            cascade=False,
            expected_message=(
                "cannot rename 'column:stg_orders': column: needs <model>.<column>, "
                "and stg_orders names a model"
            ),
            expected_help=_RENAME_HELP,
        ),
        RefactorTargetErrorTestCase(
            description="empty column name is refused",
            command=CliCommand.RENAME,
            target="stg_orders.",
            cascade=False,
            expected_message="cannot rename 'stg_orders.'",
            expected_help=_RENAME_HELP,
        ),
        RefactorTargetErrorTestCase(
            description="moving a column points at sqb rename",
            command=CliCommand.MV,
            target="stg_orders.amount",
            cascade=False,
            expected_message="sqb mv moves models; 'stg_orders.amount' names a column",
            expected_help="rename a column with sqb rename stg_orders.amount <new_name>",
        ),
        RefactorTargetErrorTestCase(
            description="cascade on a bare model is refused",
            command=CliCommand.RENAME,
            target="stg_orders",
            cascade=True,
            expected_message="--cascade applies to column renames only",
            expected_help=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_target_when_reading_then_raises_c954(
    test_case: RefactorTargetErrorTestCase,
) -> None:
    with pytest.raises(CliUserError) as raised:
        _ = refactor_request_for_target(
            request=RefactorCommandRequest(
                command=test_case.command,
                target=test_case.target,
                new_name="renamed",
                destination="models/marts/",
                cascade=test_case.cascade,
            ),
            all_keys=_ALL_KEYS,
        )

    assert raised.value.code == "C954"
    assert raised.value.message == test_case.expected_message
    assert raised.value.help == test_case.expected_help


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
