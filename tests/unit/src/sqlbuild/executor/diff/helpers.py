from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.adapter.models import CursorValue


@dataclass(frozen=True)
class FakeModelConfig:
    values: dict[str, object]


@dataclass(frozen=True)
class FakeModel:
    name: str
    config: FakeModelConfig


def build_fake_model(*, config_values: dict[str, object]) -> FakeModel:
    return FakeModel(name="orders", config=FakeModelConfig(values=config_values))


def assert_cursor_matches_expectation(
    *,
    cursor: CursorValue | None,
    expected_cursor: CursorValue | None,
    expected_kind: str | None,
) -> None:
    if expected_cursor is not None:
        assert cursor == expected_cursor
        return
    if expected_kind is None:
        assert cursor is None
        return
    assert cursor is not None
    assert cursor.kind == expected_kind
