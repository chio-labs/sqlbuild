from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlbuild.adapter.contract.models import CursorValue


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
    _CURSOR_ASSERTIONS[(expected_cursor is not None, expected_kind is not None)](
        cursor=cursor, expected_cursor=expected_cursor, expected_kind=expected_kind
    )


def _assert_exact_cursor(
    *, cursor: CursorValue | None, expected_cursor: CursorValue | None, expected_kind: str | None
) -> None:
    del expected_kind
    assert cursor == expected_cursor


def _assert_no_cursor(
    *, cursor: CursorValue | None, expected_cursor: CursorValue | None, expected_kind: str | None
) -> None:
    del expected_cursor, expected_kind
    assert cursor is None


def _assert_cursor_kind(
    *, cursor: CursorValue | None, expected_cursor: CursorValue | None, expected_kind: str | None
) -> None:
    del expected_cursor
    assert cursor is not None
    assert cursor.kind == expected_kind


_CURSOR_ASSERTIONS: dict[tuple[bool, bool], Callable[..., None]] = {
    (True, False): _assert_exact_cursor,
    (True, True): _assert_exact_cursor,
    (False, False): _assert_no_cursor,
    (False, True): _assert_cursor_kind,
}
