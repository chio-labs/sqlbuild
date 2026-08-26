import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.compiler.scopes.main.scope_metadata import scope_metadata_projection
from sqlbuild.compiler.scopes.models import DeclarationRecord, ScopeCompleteness, ScopeIndex
from tests.unit.src.sqlbuild.compiler.scopes.helpers import scope_index
from tests.unit.src.sqlbuild.kata_engine._helpers.engine._test_types import ScopePayloadTestCase
from tests.unit.src.sqlbuild.kata_engine._helpers.engine.helpers import (
    captured_native_request,
    project_with_scope,
)


@pytest.mark.parametrize(
    "test_case",
    [ScopePayloadTestCase(description="canonical_scope_projection", expected_result=True)],
    ids=lambda case: case.description,
)
def test_given_compiler_scope_index_when_evaluating_native_then_payload_equals_safe_projection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, test_case: ScopePayloadTestCase
) -> None:
    index: ScopeIndex = scope_index()

    request: dict[str, Any] = captured_native_request(
        monkeypatch=monkeypatch,
        project=project_with_scope(index=index),
        project_dir=tmp_path,
    )

    assert (request["scope_index"] == scope_metadata_projection(index=index)) is (
        test_case.expected_result
    )
    assert request["scope_index"]["declarations"][0]["metadata"]["constant"] == {
        "logical_type": "integer",
        "collection_kind": None,
        "item_count": None,
        "nullable": False,
        "render_as": "value_list",
    }
    assert request["scope_index"]["declarations"][1]["metadata"]["enum"] == {
        "members": [{"name": "OPEN"}, {"name": "CLOSED"}],
        "scalar_type": "VARCHAR",
    }
    assert str(tmp_path.resolve()) not in json.dumps(request["scope_index"])


@pytest.mark.parametrize(
    "test_case",
    [ScopePayloadTestCase(description="complete_and_partial_facts", expected_result=True)],
    ids=lambda case: case.description,
)
def test_given_complete_and_partial_scope_indexes_when_evaluating_then_completeness_is_projected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, test_case: ScopePayloadTestCase
) -> None:
    complete: ScopeIndex = scope_index()
    complete = replace(complete, completeness=ScopeCompleteness())
    partial: ScopeIndex = replace(
        complete,
        completeness=ScopeCompleteness(runtime_usage=False, placement=False),
    )

    complete_request: dict[str, Any] = captured_native_request(
        monkeypatch=monkeypatch,
        project=project_with_scope(index=complete),
        project_dir=tmp_path,
    )
    partial_request: dict[str, Any] = captured_native_request(
        monkeypatch=monkeypatch,
        project=project_with_scope(index=partial),
        project_dir=tmp_path,
    )

    assert complete_request["scope_index"]["complete"] is test_case.expected_result
    assert partial_request["scope_index"]["complete"] is False
    assert partial_request["scope_index"]["completeness"]["runtime_usage"] is False
    assert partial_request["scope_index"]["completeness"]["placement"] is False


@pytest.mark.parametrize(
    "test_case",
    [ScopePayloadTestCase(description="stable_safe_projection", expected_result=True)],
    ids=lambda case: case.description,
)
def test_given_unsorted_and_absolute_scope_facts_when_projecting_then_order_is_stable_and_paths_safe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, test_case: ScopePayloadTestCase
) -> None:
    index: ScopeIndex = scope_index()
    absolute: DeclarationRecord = replace(
        index.declarations[0],
        path=(tmp_path / "secret" / "macro.py").as_posix(),
    )
    first: ScopeIndex = replace(
        index,
        declarations=(absolute, *index.declarations[1:]),
    )
    second: ScopeIndex = replace(first, declarations=tuple(reversed(first.declarations)))

    first_request: dict[str, Any] = captured_native_request(
        monkeypatch=monkeypatch,
        project=project_with_scope(index=first),
        project_dir=tmp_path,
    )
    second_request: dict[str, Any] = captured_native_request(
        monkeypatch=monkeypatch,
        project=project_with_scope(index=second),
        project_dir=tmp_path,
    )

    assert (first_request["scope_index"] == second_request["scope_index"]) is (
        test_case.expected_result
    )
    assert str(tmp_path.resolve()) not in json.dumps(first_request["scope_index"])
    assert first_request["scope_index"]["declarations"][2]["path"] == (
        "<invalid-project-relative-path>"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
