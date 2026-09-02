from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.main.identity._version_identity_config import (
    build_version_identity_config,
)
from tests.unit.src.sqlbuild.compiler.planner.main.identity._test_types import (
    CursorRoleIdentityTestCase,
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
            description="maximum start distance participates in model version identity",
            config_key="cursor_start_max_ahead",
            expected_in_identity=True,
        ),
        VersionIdentityConfigTestCase(
            description="maximum start action participates in model version identity",
            config_key="cursor_start_max_action",
            expected_in_identity=True,
        ),
        VersionIdentityConfigTestCase(
            description="future cursor distance participates in model version identity",
            config_key="cursor_future_max_distance",
            expected_in_identity=True,
        ),
        VersionIdentityConfigTestCase(
            description="future cursor action participates in model version identity",
            config_key="cursor_future_action",
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


@pytest.mark.parametrize(
    "test_case",
    [
        CursorRoleIdentityTestCase(
            description="legacy alias migration preserves semantic identity",
            original_config={"cursor_inputs": {"orders": "event_time"}},
            changed_config={"cursor_filter_inputs": {"orders": "event_time"}},
            expected_equal=True,
        ),
        CursorRoleIdentityTestCase(
            description="explicit watermark change updates semantic identity",
            original_config={"cursor_filter_inputs": {"orders": "event_time"}},
            changed_config={
                "cursor_filter_inputs": {"orders": "event_time"},
                "cursor_watermark_inputs": {"raw_orders": "loaded_at"},
            },
            expected_equal=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cursor_role_migration_when_building_identity_then_compares_semantics(
    test_case: CursorRoleIdentityTestCase,
) -> None:
    original: dict[str, object] = build_version_identity_config(test_case.original_config)
    changed: dict[str, object] = build_version_identity_config(test_case.changed_config)

    assert (original == changed) is test_case.expected_equal


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
