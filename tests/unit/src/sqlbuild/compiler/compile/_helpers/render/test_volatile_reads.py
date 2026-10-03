"""Per-run reads recorded while attachment renders templates and SQL."""

from pathlib import Path

import pytest

from sqlbuild.compiler.compile._helpers.render.sql_vars import substitute_sql_vars
from sqlbuild.compiler.compile._helpers.render.templating import expand_template_data
from sqlbuild.compiler.compile._helpers.render.volatile_reads import record_volatile_reads
from tests.unit.src.sqlbuild.compiler.compile._helpers.render._test_types import (
    VolatileReadTestCase,
)

_CONTEXT_VALUES: dict[str, str | None] = {
    "run.id": "20260101T000000Z_000000000000",
    "run.target": "dev",
    "model.name": "orders",
}


@pytest.mark.parametrize(
    "test_case",
    [
        VolatileReadTestCase(
            description="deterministic_context_and_vars",
            template="${CTX:model.name}_${CTX:run.target}_${suffix}",
            sql="SELECT '@@CTX:model.name' AS name, @@suffix AS suffix",
            expected_reads=frozenset(),
        ),
        VolatileReadTestCase(
            description="run_id_in_template_and_sql",
            template="${CTX:run.id}",
            sql="SELECT '@@CTX:run.id' AS run_id",
            expected_reads=frozenset({"CTX:run.id"}),
        ),
        VolatileReadTestCase(
            description="environment_in_template_and_sql",
            template="${coalesce(ENV:ORDERS_SCHEMA, 'fallback')}",
            sql="SELECT '@@ENV:ORDERS_REGION' AS region",
            expected_reads=frozenset({"ENV:ORDERS_SCHEMA", "ENV:ORDERS_REGION"}),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rendering_when_recording_then_only_per_run_values_are_reported(
    test_case: VolatileReadTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORDERS_REGION", "east")
    monkeypatch.setenv("ORDERS_SCHEMA", "sales")

    with record_volatile_reads() as reads:
        _ = expand_template_data(
            value={"schema": test_case.template},
            variables={"suffix": "v2"},
            context_values=_CONTEXT_VALUES,
            context_label="model config",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        )
        _ = substitute_sql_vars(
            sql=test_case.sql,
            file_path=Path("models/orders.sql"),
            effective_vars={"suffix": "1"},
            context_values=_CONTEXT_VALUES,
        )

    assert reads == test_case.expected_reads


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-vv"]))
