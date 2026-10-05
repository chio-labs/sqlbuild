"""Layered render storage must round-trip exactly and treat every fault as no stored renders."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.compile_render_reuse._helpers.render_state_file import (
    read_render_state,
    render_state_layer,
)
from sqlbuild.cli.compile_render_reuse.models import StoredRenderState
from sqlbuild.cli.compile_reuse.models import RenderStateLayer
from sqlbuild.compiler.compile.models import RenderReuseState
from tests.unit.src.sqlbuild.cli.compile_render_reuse._helpers._test_types import (
    RenderEditChainTestCase,
    RenderLayerTestCase,
    StoredRenderReadTestCase,
)
from tests.unit.src.sqlbuild.cli.compile_render_reuse._helpers.helpers import (
    MODEL_PATHS,
    chain_payload_bytes,
    changed_macro,
    emptied,
    flipped_last_byte,
    intact,
    next_render_state,
    overlay_without_base,
    payload_bytes,
    store_edit_chain,
    stored_base,
    truncated,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RenderLayerTestCase(
            description="one_model_changed",
            changed_models=(MODEL_PATHS[3],),
            removed_models=(),
            expected_overlay=True,
        ),
        RenderLayerTestCase(
            description="most_models_changed",
            changed_models=MODEL_PATHS[:15],
            removed_models=(),
            expected_overlay=False,
        ),
        RenderLayerTestCase(
            description="stored_render_dropped",
            changed_models=(MODEL_PATHS[3],),
            removed_models=(MODEL_PATHS[5],),
            expected_overlay=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_released_reused_renders_when_storing_then_only_a_small_overlay_needs_no_rewrite(
    test_case: RenderLayerTestCase, tmp_path: Path
) -> None:
    _, stored = stored_base(tmp_path)
    current: RenderReuseState = next_render_state(
        stored=stored, edited=test_case.changed_models, removed=test_case.removed_models
    )

    layer: RenderStateLayer | None = render_state_layer(state=current, stored=stored.layers)

    assert (layer is not None) is test_case.expected_overlay


@pytest.mark.parametrize(
    "test_case",
    [
        RenderEditChainTestCase(
            description="different_models_edited",
            edits=(MODEL_PATHS[1], MODEL_PATHS[2]),
            expected_overlay_models=frozenset({MODEL_PATHS[1], MODEL_PATHS[2]}),
        ),
        RenderEditChainTestCase(
            description="same_model_edited_twice",
            edits=(MODEL_PATHS[1], MODEL_PATHS[1]),
            expected_overlay_models=frozenset({MODEL_PATHS[1]}),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_overlay_when_storing_again_then_earlier_overlay_renders_are_kept(
    test_case: RenderEditChainTestCase, tmp_path: Path
) -> None:
    stored: StoredRenderState = store_edit_chain(directory=tmp_path, edits=test_case.edits)

    assert stored.layers.overlay_models == test_case.expected_overlay_models
    assert payload_bytes(stored.state) == chain_payload_bytes(test_case.edits)


@pytest.mark.parametrize(
    "test_case",
    [
        StoredRenderReadTestCase(
            description="intact_with_changed_model", prepare=intact, expected_readable=True
        ),
        StoredRenderReadTestCase(
            description="flipped_payload_byte", prepare=flipped_last_byte, expected_readable=False
        ),
        StoredRenderReadTestCase(
            description="truncated", prepare=truncated, expected_readable=False
        ),
        StoredRenderReadTestCase(description="empty", prepare=emptied, expected_readable=False),
        StoredRenderReadTestCase(
            description="overlay_whose_base_is_missing",
            prepare=overlay_without_base,
            expected_readable=False,
        ),
        StoredRenderReadTestCase(
            description="changed_path_is_not_a_stored_model",
            prepare=changed_macro,
            expected_readable=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stored_render_file_when_reading_then_only_intact_relevant_renders_are_returned(
    test_case: StoredRenderReadTestCase, tmp_path: Path
) -> None:
    path, changed_paths = test_case.prepare(tmp_path)

    stored: StoredRenderState | None = read_render_state(path=path, changed_paths=changed_paths)

    assert (stored is not None) is test_case.expected_readable


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
