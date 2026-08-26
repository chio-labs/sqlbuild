from __future__ import annotations

import pytest

from sqlbuild.spec.contracts.main.resolve_effective_collection_rendering import (
    resolve_effective_collection_rendering,
)
from sqlbuild.spec.contracts.models import ConstantsConfig, ProjectConfig
from sqlbuild.sql_values.types import CollectionRendering
from tests.unit.src.sqlbuild.spec.contracts.main._test_types import (
    EffectiveCollectionRenderingResolutionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        EffectiveCollectionRenderingResolutionTestCase(
            description="uses value-list default when no values override it",
            project_config=ProjectConfig(name="demo", adapter="duckdb"),
            declaration_override=None,
            expected_collection_rendering=CollectionRendering.VALUE_LIST,
        ),
        EffectiveCollectionRenderingResolutionTestCase(
            description="uses project collection rendering without declaration override",
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                constants=ConstantsConfig(collection_rendering=CollectionRendering.ARRAY),
            ),
            declaration_override=None,
            expected_collection_rendering=CollectionRendering.ARRAY,
        ),
        EffectiveCollectionRenderingResolutionTestCase(
            description="declaration collection rendering overrides project config",
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                constants=ConstantsConfig(collection_rendering=CollectionRendering.ARRAY),
            ),
            declaration_override=CollectionRendering.VALUE_LIST,
            expected_collection_rendering=CollectionRendering.VALUE_LIST,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rendering_configuration_when_resolving_then_precedence_is_applied(
    test_case: EffectiveCollectionRenderingResolutionTestCase,
) -> None:
    collection_rendering: CollectionRendering = resolve_effective_collection_rendering(
        project_config=test_case.project_config,
        declaration_override=test_case.declaration_override,
    )

    assert collection_rendering is test_case.expected_collection_rendering
