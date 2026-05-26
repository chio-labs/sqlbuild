"""State checkpoint command helpers."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.shared.helpers.colors import blue_bold, green, green_bold, supports_color
from sqlbuild.spec.models.environments import resolve_environment_name
from sqlbuild.virtual.state.main.checkpoint_refs import get_virtual_environment_checkpoint_refs
from sqlbuild.virtual.state.main.list_checkpoints import list_virtual_environment_checkpoints
from sqlbuild.virtual.state.models import (
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointRefRecord,
)


def run_state_checkpoints(
    *,
    project_dir: Path | None,
    command: str | None,
    checkpoint_id: str | None = None,
    virtual_environment_name: str | None = None,
    no_color: bool = False,
) -> int:
    """Run state checkpoint inspection commands."""

    if command is None:
        raise CliUserError("state checkpoints requires a subcommand such as 'list'", code="C902")
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    resolved_environment_name: str | None = virtual_environment_name or resolve_environment_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_environment=None,
    )
    if resolved_environment_name is None:
        raise CliUserError(
            "state checkpoints requires --virtual-env or a default environment",
            code="C903",
        )
    use_color: bool = not no_color and supports_color()
    if command == "list":
        checkpoints: tuple[VirtualEnvironmentCheckpointRecord, ...] = (
            list_virtual_environment_checkpoints(
                project_dir=effective_project_dir,
                discovered_inputs=discovered_inputs,
                virtual_environment_name=resolved_environment_name,
            )
        )
        print(
            _format_checkpoint_list(
                virtual_environment_name=resolved_environment_name,
                checkpoints=checkpoints,
                use_color=use_color,
            )
        )
        return 0
    if command == "show":
        if checkpoint_id is None:
            raise CliUserError("state checkpoints show requires checkpoint id", code="C904")
        refs: tuple[VirtualEnvironmentCheckpointRefRecord, ...] = (
            get_virtual_environment_checkpoint_refs(
                project_dir=effective_project_dir,
                discovered_inputs=discovered_inputs,
                checkpoint_id=checkpoint_id,
            )
        )
        if not refs:
            raise CliUserError(f"unknown checkpoint '{checkpoint_id}'", code="C905")
        print(
            _format_checkpoint_show(
                checkpoint_id=checkpoint_id,
                refs=refs,
                use_color=use_color,
            )
        )
        return 0
    raise CliUserError(f"unknown state checkpoints command '{command}'", code="C906")


def _format_checkpoint_list(
    *,
    virtual_environment_name: str,
    checkpoints: tuple[VirtualEnvironmentCheckpointRecord, ...],
    use_color: bool,
) -> str:
    title: str = (
        green_bold("Virtual environment checkpoints")
        if use_color
        else "Virtual environment checkpoints"
    )
    env_label: str = blue_bold(virtual_environment_name) if use_color else virtual_environment_name
    lines: list[str] = ["", f"{title}  {env_label}", ""]
    if not checkpoints:
        lines.append("  no checkpoints")
        lines.append("")
        return "\n".join(lines)
    checkpoint: VirtualEnvironmentCheckpointRecord
    for checkpoint in checkpoints:
        created_at: str = (
            str(checkpoint.created_at) if checkpoint.created_at is not None else "unknown"
        )
        lines.append(f"  {checkpoint.checkpoint_id}  {created_at}")
    lines.append("")
    return "\n".join(lines)


def _format_checkpoint_show(
    *,
    checkpoint_id: str,
    refs: tuple[VirtualEnvironmentCheckpointRefRecord, ...],
    use_color: bool,
) -> str:
    title: str = (
        green_bold("Virtual environment checkpoint")
        if use_color
        else "Virtual environment checkpoint"
    )
    refs_label: str = green("Refs:") if use_color else "Refs:"
    lines: list[str] = ["", title, "", f"  checkpoint: {checkpoint_id}", "", refs_label]
    ref: VirtualEnvironmentCheckpointRefRecord
    for ref in refs:
        lines.append(f"  {ref.model_name:<24} {ref.version_hash}")
    lines.append("")
    return "\n".join(lines)
