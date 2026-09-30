"""CLI e2e coverage for `sqb mv` carrying scoped declarations to where placement requires."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.refactor._test_types import (
    DeclarationMoveE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.refactor.helpers import (
    CENTS_MACRO,
    ORDER_REFUNDS,
    ORDER_SHAPE,
    existing_files,
    relation_type,
    sqb,
    write_orders_project,
)

_CENTS: str = "models/staging/_sqlbuild/_macros/cents.py"
_PRIORITY_ENUM: dict[str, str] = {
    "models/marts/_sqlbuild/_enums/priority.sql": (
        "ENUM (\n  name priority,\n  members (LOW 1, HIGH 3),\n);\n"
    ),
    "models/marts/fact_orders.sql": ORDER_SHAPE["models/marts/fact_orders.sql"].replace(
        "SELECT", 'SELECT\n  @enum("priority").LOW AS priority,', 1
    ),
}


@pytest.mark.parametrize(
    "test_case",
    [
        DeclarationMoveE2ETestCase(
            description="declarations only the moved model uses move with it",
            model="fact_orders",
            extra_files={**ORDER_SHAPE, **_PRIORITY_ENUM},
            destination="models/reporting/",
            expected_moved={
                "models/marts/_sqlbuild/_schemas/order_shape.sql": (
                    "models/reporting/_sqlbuild/_schemas/order_shape.sql"
                ),
                "models/marts/_sqlbuild/_enums/priority.sql": (
                    "models/reporting/_sqlbuild/_enums/priority.sql"
                ),
            },
        ),
        DeclarationMoveE2ETestCase(
            description="a macro still used at the old folder moves up to the shared owner",
            model="stg_order_cents",
            extra_files={**CENTS_MACRO, **ORDER_REFUNDS},
            destination="models/staging/eu/",
            expected_moved={_CENTS: "models/staging/_sqlbuild/macros/cents.py"},
        ),
        DeclarationMoveE2ETestCase(
            description="a macro shared across the models root moves to the top-level role",
            model="stg_order_cents",
            extra_files={**CENTS_MACRO, **ORDER_REFUNDS},
            destination="models/marts/",
            expected_moved={_CENTS: "macros/cents.py"},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_scoped_declarations_when_moving_model_then_they_follow_placement_rules(
    tmp_path: Path, test_case: DeclarationMoveE2ETestCase
) -> None:
    project_dir: Path = write_orders_project(tmp_path=tmp_path, files=test_case.extra_files)
    model: str = test_case.model

    moved: subprocess.CompletedProcess[str] = sqb(
        project_dir, "mv", f"model:{model}", test_case.destination
    )
    compiled: subprocess.CompletedProcess[str] = sqb(project_dir, "compile")
    built: subprocess.CompletedProcess[str] = sqb(project_dir, "build")

    assert moved.returncode == 0, moved.stdout + moved.stderr
    assert existing_files(
        project_dir=project_dir,
        paths=(*test_case.expected_moved, *test_case.expected_moved.values()),
    ) == tuple(sorted(test_case.expected_moved.values())), moved.stdout
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    assert "error[S0" not in compiled.stdout + compiled.stderr
    assert built.returncode == 0, built.stdout + built.stderr
    assert relation_type(project_dir=project_dir, name=model) is not None
