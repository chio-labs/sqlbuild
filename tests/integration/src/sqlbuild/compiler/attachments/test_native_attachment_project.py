"""Every attachment kind compiles like Python under preview, with macros through the bridge."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.frontier.types import CompilerEngine
from tests.integration.src.sqlbuild.compiler.attachments._test_types import (
    AttachmentProjectTestCase,
)
from tests.integration.src.sqlbuild.compiler.attachments.helpers import (
    attachment_engine_outcome,
)

_BRIDGED_CONSUMERS: frozenset[str] = frozenset(
    {
        "bridged:<built-in>/audits/generic/accepted_values.sql",
        "bridged:<built-in>/audits/generic/not_null.sql",
        "bridged:<project>/audits/generic/amount_floor.sql",
        "bridged:<project>/functions/sql/order_label.sql",
        "bridged:<project>/models/orders.sql",
        "bridged:<project>/sources/events.yml",
        "bridged:<project>/tests/scenarios/orders_scenario.sql",
        "bridged:<project>/tests/unit/test_orders.sql",
    }
)
_PREVIEW_ONLY_ENTRIES: frozenset[str] = (
    frozenset({"pair_seed_files", "render_attached_generic_audit", "expand_config_templates"})
    | _BRIDGED_CONSUMERS
)
_ATTACHMENT_ENTRIES: frozenset[str] = frozenset(
    {
        "pair_seed_files",
        "render_attached_generic_audit",
        "expand_config_templates",
        "substitute_static_project_vars",
        "scan_sql_declaration_references",
    }
)


@pytest.mark.parametrize(
    "test_case",
    [
        AttachmentProjectTestCase(
            description="macros in every attachment kind, seeds, templates and generic audits",
            expected_preview_entries=_ATTACHMENT_ENTRIES | _BRIDGED_CONSUMERS,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_attachment_project_when_building_inputs_then_preview_matches_python(
    test_case: AttachmentProjectTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcomes: dict[CompilerEngine, tuple[frozenset[str], str]] = {
        engine: attachment_engine_outcome(
            project_dir=tmp_path / engine.value,
            engine=engine,
            monkeypatch=monkeypatch,
        )
        for engine in CompilerEngine
    }
    python_called, python_outcome = outcomes[CompilerEngine.PYTHON]
    native_called, native_outcome = outcomes[CompilerEngine.NATIVE]
    preview_called, preview_outcome = outcomes[CompilerEngine.NATIVE_PREVIEW]

    assert (
        preview_outcome.replace(CompilerEngine.NATIVE_PREVIEW.value, "python"),
        native_outcome.replace(CompilerEngine.NATIVE.value, "python"),
        preview_called >= test_case.expected_preview_entries,
        (python_called | native_called) & _PREVIEW_ONLY_ENTRIES,
    ) == (python_outcome, python_outcome, True, frozenset()), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
