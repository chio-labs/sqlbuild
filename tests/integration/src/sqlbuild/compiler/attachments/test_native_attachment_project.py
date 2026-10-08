"""Compile inputs of a project with every attachment kind match Python under the preview engine."""

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

_PREVIEW_ONLY_ENTRIES: frozenset[str] = frozenset(
    {"pair_seed_files", "render_attached_generic_audit", "expand_config_templates"}
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
            description="seeds, templated source and function, and an attached generic audit",
            expected_preview_entries=_ATTACHMENT_ENTRIES,
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
        preview_called & _ATTACHMENT_ENTRIES >= test_case.expected_preview_entries,
        (python_called | native_called) & _PREVIEW_ONLY_ENTRIES,
    ) == (python_outcome, python_outcome, True, frozenset()), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
