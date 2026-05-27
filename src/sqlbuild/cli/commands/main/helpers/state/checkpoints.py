"""State checkpoint command helpers."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.shared.helpers.colors import blue, blue_bold, dim, green, green_bold, supports_color
from sqlbuild.spec.models.environments import resolve_environment_name
from sqlbuild.virtual.state.main.checkpoint_refs import get_virtual_environment_checkpoint_refs
from sqlbuild.virtual.state.main.environment_refs import get_virtual_environment_refs
from sqlbuild.virtual.state.main.list_checkpoints import list_virtual_environment_checkpoints
from sqlbuild.virtual.state.models import (
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointRefRecord,
    VirtualEnvironmentRefRecord,
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
    if command == "diff":
        if checkpoint_id is None:
            raise CliUserError("state checkpoints diff requires checkpoint id", code="C907")
        checkpoint_refs: tuple[VirtualEnvironmentCheckpointRefRecord, ...] = (
            get_virtual_environment_checkpoint_refs(
                project_dir=effective_project_dir,
                discovered_inputs=discovered_inputs,
                checkpoint_id=checkpoint_id,
            )
        )
        if not checkpoint_refs:
            raise CliUserError(f"unknown checkpoint '{checkpoint_id}'", code="C905")
        current_refs: tuple[VirtualEnvironmentRefRecord, ...] = get_virtual_environment_refs(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
            virtual_environment_name=resolved_environment_name,
        )
        print(
            _format_checkpoint_diff(
                virtual_environment_name=resolved_environment_name,
                checkpoint_id=checkpoint_id,
                current_refs=current_refs,
                checkpoint_refs=checkpoint_refs,
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
        checkpoint_label: str = (
            blue(checkpoint.checkpoint_id) if use_color else checkpoint.checkpoint_id
        )
        created_label: str = dim(created_at) if use_color else created_at
        lines.append(f"  {checkpoint_label}  {created_label}")
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
    checkpoint_label: str = blue(checkpoint_id) if use_color else checkpoint_id
    refs_label: str = green("Refs") if use_color else "Refs"
    lines: list[str] = ["", title, "", f"  checkpoint           {checkpoint_label}", "", refs_label]
    ref: VirtualEnvironmentCheckpointRefRecord
    for ref in refs:
        model_label: str = (
            blue_bold(f"{ref.model_name:<24}") if use_color else f"{ref.model_name:<24}"
        )
        hash_label: str = dim(ref.version_hash) if use_color else ref.version_hash
        lines.append(f"  {model_label} {hash_label}")
    lines.append("")
    return "\n".join(lines)


def _format_checkpoint_diff(
    *,
    virtual_environment_name: str,
    checkpoint_id: str,
    current_refs: tuple[VirtualEnvironmentRefRecord, ...],
    checkpoint_refs: tuple[VirtualEnvironmentCheckpointRefRecord, ...],
    use_color: bool,
) -> str:
    title: str = (
        green_bold("Virtual environment checkpoint diff")
        if use_color
        else "Virtual environment checkpoint diff"
    )
    env_label: str = blue_bold(virtual_environment_name) if use_color else virtual_environment_name
    current_ref_map: dict[str, str] = {ref.model_name: ref.version_hash for ref in current_refs}
    checkpoint_ref_map: dict[str, str] = {
        ref.model_name: ref.version_hash for ref in checkpoint_refs
    }
    changed: tuple[str, ...] = tuple(
        sorted(
            model_name
            for model_name, version_hash in current_ref_map.items()
            if model_name in checkpoint_ref_map and checkpoint_ref_map[model_name] != version_hash
        )
    )
    current_only: tuple[str, ...] = tuple(
        sorted(model_name for model_name in current_ref_map if model_name not in checkpoint_ref_map)
    )
    checkpoint_only: tuple[str, ...] = tuple(
        sorted(model_name for model_name in checkpoint_ref_map if model_name not in current_ref_map)
    )
    lines: list[str] = [
        "",
        f"{title}  {env_label}",
        "",
        f"  checkpoint       {_value(checkpoint_id, use_color=use_color)}",
        f"  changed refs     {_value(f'{len(changed):,}', use_color=use_color)}",
        f"  current only     {_value(f'{len(current_only):,}', use_color=use_color)}",
        f"  checkpoint only  {_value(f'{len(checkpoint_only):,}', use_color=use_color)}",
    ]
    _append_ref_diff_lines(
        lines, "Changed refs", changed, current_ref_map, checkpoint_ref_map, use_color
    )
    _append_ref_diff_lines(
        lines, "Current only", current_only, current_ref_map, checkpoint_ref_map, use_color
    )
    _append_ref_diff_lines(
        lines, "Checkpoint only", checkpoint_only, current_ref_map, checkpoint_ref_map, use_color
    )
    lines.append("")
    return "\n".join(lines)


def _append_ref_diff_lines(
    lines: list[str],
    label: str,
    model_names: tuple[str, ...],
    current_ref_map: dict[str, str],
    checkpoint_ref_map: dict[str, str],
    use_color: bool,
) -> None:
    if not model_names:
        return
    lines.append("")
    lines.append(green(label) if use_color else label)
    for model_name in model_names:
        current_hash: str = current_ref_map.get(model_name, "<missing>")
        checkpoint_hash: str = checkpoint_ref_map.get(model_name, "<missing>")
        model_label: str = blue_bold(f"{model_name:<24}") if use_color else f"{model_name:<24}"
        current_label: str = dim(current_hash) if use_color else current_hash
        checkpoint_label: str = dim(checkpoint_hash) if use_color else checkpoint_hash
        lines.append(f"  {model_label} {current_label} -> {checkpoint_label}")


def _value(text: str, *, use_color: bool) -> str:
    return blue(text) if use_color else text
