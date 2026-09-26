"""Dependency-ready models bind against producer outputs in their first analysis."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from sqlbuild.compiler.compile._helpers.assembly import project
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import NativeCatalogCase


@pytest.mark.parametrize(
    "test_case",
    [NativeCatalogCase("closed dependency waves", 'SELECT id FROM __ref("orders")')],
    ids=lambda case: case.description,
)
def test_given_inferred_producer_when_binding_consumers_then_avoids_deferred_requests_and_invalidates_changed_shapes(
    test_case: NativeCatalogCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = []\n'
    )
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources/orders.yml").write_text(
        "sources:\n  - name: raw_orders\n    expression: SELECT 1 AS id, 2 AS quantity\n"
    )
    (tmp_path / "models").mkdir()
    producer: Path = tmp_path / "models/orders.sql"
    producer.write_text('MODEL (materialized view); SELECT id FROM __source("raw_orders")')
    (tmp_path / "models/report.sql").write_text("MODEL (materialized view); " + test_case.sql)
    original: Callable[..., Any] = project.get_schema_validations
    requests: list[Any] = []

    def traced(**kwargs: Any) -> Any:
        requests.extend(kwargs["requests"])
        return original(**kwargs)

    monkeypatch.setattr(project, "get_schema_validations", traced)
    args: list[str] = ["--project-dir", str(tmp_path), "compile", "--json"]
    assert main(args) == 0
    cold: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert tuple(item["code"] for item in cold["diagnostics"]) == test_case.expected_codes
    assert requests == []
    assert main(args) == 0
    warm: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert warm["resources"] == cold["resources"]
    producer.write_text(producer.read_text().replace("SELECT id", "SELECT quantity"))
    assert main(args) == 1
    changed: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert [item["code"] for item in changed["diagnostics"]] == ["B002"]
    assert requests == []
    assert main([*args, "--no-cache"]) == 1
    oracle: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert oracle["diagnostics"] == changed["diagnostics"]
    producer.write_text(producer.read_text().replace("SELECT quantity", "SELECT id"))
    assert main(args) == 0
    restored: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert restored["resources"] == cold["resources"]
    assert restored["diagnostics"] == cold["diagnostics"]


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
