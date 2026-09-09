from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledProject, CompiledSqlTest
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.rule_engine.classes.model_test_facts import TestFacts as ModelTestFacts
from sqlbuild.rule_engine.models import Model
from tests.unit.src.sqlbuild.rule_engine._helpers.engine.helpers import (
    direct_sql_test,
    model_sql_test,
)
from tests.unit.src.sqlbuild.rule_engine.main.evaluate.helpers import build_project


def test_given_model_and_non_model_tests_when_querying_model_then_returns_each_matching_test_once() -> (
    None
):
    matching: CompiledSqlTest = replace(model_sql_test(), target_model_names=("orders", "orders"))
    other_model: CompiledSqlTest = replace(
        model_sql_test(), name="customers", target_model_names=("customers",)
    )
    direct: CompiledSqlTest = direct_sql_test(
        mode=SqlTestMode.UDF, name="order_status", block_index=1
    )
    project: CompiledProject = replace(
        build_project(
            name="orders",
            relative_path="models/orders.sql",
            sql="SELECT 1 AS order_id",
            config_values={},
        ),
        sql_tests=(matching, other_model, direct),
    )

    facts = ModelTestFacts(project=project)

    assert facts.for_model(
        Model(name="orders", path=Path("models/orders.sql"), materialization="view")
    ) == (matching,)
    assert facts.all() == (matching, other_model, direct)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
