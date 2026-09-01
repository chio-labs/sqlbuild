from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.main.identity._version_identity_config import (
    build_version_identity_config,
)
from tests.unit.src.sqlbuild.compiler.planner.main.identity._test_types import (
    VersionIdentityConfigTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VersionIdentityConfigTestCase(
            description="filter inputs participate in model version identity",
            config_key="cursor_filter_inputs",
            expected_in_identity=True,
        ),
        VersionIdentityConfigTestCase(
            description="watermark inputs participate in model version identity",
            config_key="cursor_watermark_inputs",
            expected_in_identity=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cursor_role_config_when_building_identity_then_field_participates(
    test_case: VersionIdentityConfigTestCase,
) -> None:
    identity: dict[str, object] = build_version_identity_config(
        {test_case.config_key: {"orders": "event_time"}}
    )

    assert (test_case.config_key in identity) is test_case.expected_in_identity


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
