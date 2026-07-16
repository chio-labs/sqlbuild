from __future__ import annotations

from datetime import datetime

import pytest

from sqlbuild.cli.commands._helpers.state.checkpoints import (
    _format_checkpoint_diff,
    _format_checkpoint_list,
    _format_checkpoint_show,
)
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.virtual.state.models import (
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointSeedRefRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentSeedRefRecord,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.state._test_types import (
    CheckpointColorOutputTestCase,
    CheckpointOutputTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CheckpointOutputTestCase(
            description="preserves no-color checkpoint list output",
            expected_rendered="\nVirtual environment checkpoints  dev\n\n"
            "  cp_1  2026-05-29 12:00:00\n"
            "  cp_2  unknown\n",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_checkpoints_when_formatting_list_without_color_then_preserves_output(
    test_case: CheckpointOutputTestCase,
) -> None:
    rendered: str = _format_checkpoint_list(
        virtual_environment_name="dev",
        checkpoints=(
            VirtualEnvironmentCheckpointRecord(
                checkpoint_id="cp_1",
                virtual_environment_name="dev",
                created_at=datetime(2026, 5, 29, 12, 0, 0),
            ),
            VirtualEnvironmentCheckpointRecord(
                checkpoint_id="cp_2",
                virtual_environment_name="dev",
                created_at=None,
            ),
        ),
        style=CliStyle(use_color=False),
    )

    assert rendered == test_case.expected_rendered


@pytest.mark.parametrize(
    "test_case",
    [
        CheckpointOutputTestCase(
            description="preserves no-color checkpoint show output",
            expected_rendered="\nVirtual environment checkpoint\n\n"
            "  checkpoint           cp_1\n\n"
            "Refs\n"
            "  model_a                  hash_a\n\n"
            "Seed refs\n"
            "  seed_a                   seed_hash_a\n",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_checkpoint_model_refs_when_formatting_show_without_color_then_preserves_output(
    test_case: CheckpointOutputTestCase,
) -> None:
    rendered: str = _format_checkpoint_show(
        checkpoint_id="cp_1",
        refs=(
            VirtualEnvironmentCheckpointModelRefRecord(
                checkpoint_id="cp_1", model_name="model_a", version_hash="hash_a"
            ),
        ),
        seed_refs=(
            VirtualEnvironmentCheckpointSeedRefRecord(
                checkpoint_id="cp_1", seed_name="seed_a", version_hash="seed_hash_a"
            ),
        ),
        style=CliStyle(use_color=False),
    )

    assert rendered == test_case.expected_rendered


@pytest.mark.parametrize(
    "test_case",
    [
        CheckpointOutputTestCase(
            description="preserves no-color checkpoint diff output",
            expected_rendered="\nVirtual environment checkpoint diff  dev\n\n"
            "  checkpoint       cp_1\n"
            "  changed refs     1\n"
            "  current only     1\n"
            "  checkpoint only  1\n"
            "  changed seeds    1\n"
            "  current seeds    1\n"
            "  checkpoint seeds 1\n\n"
            "Changed refs\n"
            "  shared                   current_hash -> checkpoint_hash\n\n"
            "Current only\n"
            "  current_only             current_only_hash -> <missing>\n\n"
            "Checkpoint only\n"
            "  checkpoint_only          <missing> -> checkpoint_only_hash\n\n"
            "Changed seed refs\n"
            "  seed_a                   current_seed_hash -> checkpoint_seed_hash\n\n"
            "Current only seed refs\n"
            "  seed_current_only        current_only_seed_hash -> <missing>\n\n"
            "Checkpoint only seed refs\n"
            "  seed_checkpoint_only     <missing> -> checkpoint_only_seed_hash\n",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_checkpoint_model_refs_when_formatting_diff_without_color_then_preserves_output(
    test_case: CheckpointOutputTestCase,
) -> None:
    rendered: str = _format_checkpoint_diff(
        virtual_environment_name="dev",
        checkpoint_id="cp_1",
        current_refs=(
            VirtualEnvironmentModelRefRecord(
                virtual_environment_name="dev", model_name="shared", version_hash="current_hash"
            ),
            VirtualEnvironmentModelRefRecord(
                virtual_environment_name="dev",
                model_name="current_only",
                version_hash="current_only_hash",
            ),
        ),
        current_seed_refs=(
            VirtualEnvironmentSeedRefRecord(
                virtual_environment_name="dev",
                seed_name="seed_a",
                version_hash="current_seed_hash",
            ),
            VirtualEnvironmentSeedRefRecord(
                virtual_environment_name="dev",
                seed_name="seed_current_only",
                version_hash="current_only_seed_hash",
            ),
        ),
        checkpoint_model_refs=(
            VirtualEnvironmentCheckpointModelRefRecord(
                checkpoint_id="cp_1", model_name="shared", version_hash="checkpoint_hash"
            ),
            VirtualEnvironmentCheckpointModelRefRecord(
                checkpoint_id="cp_1",
                model_name="checkpoint_only",
                version_hash="checkpoint_only_hash",
            ),
        ),
        checkpoint_seed_refs=(
            VirtualEnvironmentCheckpointSeedRefRecord(
                checkpoint_id="cp_1", seed_name="seed_a", version_hash="checkpoint_seed_hash"
            ),
            VirtualEnvironmentCheckpointSeedRefRecord(
                checkpoint_id="cp_1",
                seed_name="seed_checkpoint_only",
                version_hash="checkpoint_only_seed_hash",
            ),
        ),
        style=CliStyle(use_color=False),
    )

    assert rendered == test_case.expected_rendered


@pytest.mark.parametrize(
    "test_case",
    [
        CheckpointColorOutputTestCase(
            description="uses semantic checkpoint colors",
            expected_fragments=(
                "\033[32m\033[1mVirtual environment checkpoint\033[0m",
                "\033[34mcp_1\033[0m",
                "\033[32mRefs\033[0m",
                "\033[32mSeed refs\033[0m",
                "\033[34m\033[1mmodel_a",
                "\033[34m\033[1mseed_a",
                "\033[2mhash_a\033[0m",
                "\033[2mseed_hash_a\033[0m",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_checkpoint_model_refs_when_formatting_with_color_then_uses_semantic_colors(
    test_case: CheckpointColorOutputTestCase,
) -> None:
    rendered: str = _format_checkpoint_show(
        checkpoint_id="cp_1",
        refs=(
            VirtualEnvironmentCheckpointModelRefRecord(
                checkpoint_id="cp_1", model_name="model_a", version_hash="hash_a"
            ),
        ),
        seed_refs=(
            VirtualEnvironmentCheckpointSeedRefRecord(
                checkpoint_id="cp_1", seed_name="seed_a", version_hash="seed_hash_a"
            ),
        ),
        style=CliStyle(use_color=True),
    )

    for fragment in test_case.expected_fragments:
        assert fragment in rendered
