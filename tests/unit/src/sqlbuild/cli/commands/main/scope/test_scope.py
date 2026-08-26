"""Offline scope command behavior tests."""

from __future__ import annotations

import json
from io import StringIO

import pytest

from sqlbuild.cli.commands._helpers.runtime import adapter_context, connection
from sqlbuild.cli.commands._helpers.scope.command import run_scope_command
from sqlbuild.cli.commands.models import ScopeCommandRequest
from sqlbuild.compiler.scopes.models import ScopeCompleteness, ScopeIndex
from tests.unit.src.sqlbuild.cli.commands.main.scope._test_types import ScopeCommandCase
from tests.unit.src.sqlbuild.compiler.scopes.helpers import report_scope_lookup


@pytest.mark.parametrize(
    "test_case", (ScopeCommandCase("offline", 0),), ids=lambda case: case.description
)
def test_given_offline_index_loader_when_running_then_connection_runtime_is_not_called(
    monkeypatch: pytest.MonkeyPatch, test_case: ScopeCommandCase
) -> None:
    def fail(**_kwargs: object) -> None:
        pytest.fail("scope must not resolve adapters or warehouse credentials")

    monkeypatch.setattr(connection, "resolve_project_connection_config", fail)
    monkeypatch.setattr(adapter_context, "resolve_adapter_connection_context", fail)
    exit_code: int = run_scope_command(
        request=ScopeCommandRequest(target="model:orders", json_output=True),
        load_scope_index=lambda **_kwargs: report_scope_lookup().index,
        output_stream=StringIO(),
    )
    assert exit_code == test_case.expected_exit_code


@pytest.mark.parametrize(
    "test_case", (ScopeCommandCase("deterministic", 0),), ids=lambda case: case.description
)
def test_given_scope_index_when_rendering_json_twice_then_bytes_are_deterministic(
    test_case: ScopeCommandCase,
) -> None:
    index: ScopeIndex = report_scope_lookup(extra_globals=3).index
    request: ScopeCommandRequest = ScopeCommandRequest(
        target="model:orders",
        include_nearby=True,
        explain="macro:normalize",
        json_output=True,
    )
    outputs: list[str] = []
    for _ in range(2):
        stream: StringIO = StringIO()
        exit_code: int = run_scope_command(
            request=request,
            load_scope_index=lambda **_kwargs: index,
            output_stream=stream,
        )
        assert exit_code == test_case.expected_exit_code
        outputs.append(stream.getvalue())
    assert outputs[0] == outputs[1]
    assert outputs[0].endswith("\n") and not outputs[0].endswith("\n\n")
    assert "\x1b[" not in outputs[0]
    assert json.loads(outputs[0])["schema_version"] == 1
    assert "secret-source-digest" not in outputs[0]
    assert "/home/" not in outputs[0]


@pytest.mark.parametrize(
    "test_case", (ScopeCommandCase("partial", 1),), ids=lambda case: case.description
)
def test_given_incomplete_index_when_running_then_prints_useful_payload_and_exits_one(
    test_case: ScopeCommandCase,
) -> None:
    index: ScopeIndex = ScopeIndex(completeness=ScopeCompleteness(discovery=False))
    stream: StringIO = StringIO()
    exit_code: int = run_scope_command(
        request=ScopeCommandRequest(at="models/new.sql", json_output=True),
        load_scope_index=lambda **_kwargs: index,
        output_stream=stream,
    )
    payload: dict[str, object] = json.loads(stream.getvalue())
    resource: dict[str, object] = payload["resource"]
    assert exit_code == test_case.expected_exit_code
    assert resource["path"] == "models/new.sql"
    assert payload["complete"] is False


@pytest.mark.parametrize(
    "test_case", (ScopeCommandCase("directory", 1),), ids=lambda case: case.description
)
def test_given_prospective_directory_with_trailing_slash_when_running_then_preserves_input(
    test_case: ScopeCommandCase,
) -> None:
    index: ScopeIndex = report_scope_lookup().index
    stream: StringIO = StringIO()
    exit_code: int = run_scope_command(
        request=ScopeCommandRequest(at="models/staging/", json_output=True),
        load_scope_index=lambda **_kwargs: index,
        output_stream=stream,
    )
    payload: dict[str, object] = json.loads(stream.getvalue())
    resource: dict[str, object] = payload["resource"]
    assert exit_code == test_case.expected_exit_code
    assert resource["target"] == "models/staging/"
    assert resource["directory"] is True


@pytest.mark.parametrize(
    "test_case", (ScopeCommandCase("move", 0),), ids=lambda case: case.description
)
def test_given_existing_target_and_destination_when_running_then_text_has_move_sections(
    test_case: ScopeCommandCase,
) -> None:
    stream: StringIO = StringIO()
    exit_code: int = run_scope_command(
        request=ScopeCommandRequest(target="model:orders", as_path="models/marts/orders.sql"),
        load_scope_index=lambda **_kwargs: report_scope_lookup().index,
        output_stream=stream,
    )
    assert exit_code == test_case.expected_exit_code
    assert all(
        section in stream.getvalue()
        for section in ("Move preview", "Retained", "Gained", "Lost", "Invalidated usages")
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
