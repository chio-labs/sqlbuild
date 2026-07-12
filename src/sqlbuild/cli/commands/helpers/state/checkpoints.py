"""State checkpoint command helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.cli.exceptions import CliUserError
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.shared.classes.cli_document import CliDocument
from sqlbuild.shared.helpers.output.cli_style import CliStyle
from sqlbuild.shared.helpers.output.colors import supports_color
from sqlbuild.spec.models.targets import resolve_target_name
from sqlbuild.virtual.state.main.checkpoints.list_checkpoints import (
    list_virtual_environment_checkpoints,
)
from sqlbuild.virtual.state.main.environments.runtime import build_state_runtime
from sqlbuild.virtual.state.models import (
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointSeedRefRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentSeedRefRecord,
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
    resolved_target_name: str | None = virtual_environment_name or resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=None,
    )
    if resolved_target_name is None:
        raise CliUserError(
            "state checkpoints requires --virtual-env or a default target",
            code="C903",
        )
    style: CliStyle = CliStyle(use_color=not no_color and supports_color())
    if command == "list":
        checkpoints: tuple[VirtualEnvironmentCheckpointRecord, ...] = (
            list_virtual_environment_checkpoints(
                project_dir=effective_project_dir,
                discovered_inputs=discovered_inputs,
                virtual_environment_name=resolved_target_name,
            )
        )
        print(
            _format_checkpoint_list(
                virtual_environment_name=resolved_target_name,
                checkpoints=checkpoints,
                style=style,
            )
        )
        return 0
    if command == "show":
        if checkpoint_id is None:
            raise CliUserError("state checkpoints show requires checkpoint id", code="C904")
        refs, seed_refs = _read_checkpoint_refs(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
            checkpoint_id=checkpoint_id,
        )
        if not refs and not seed_refs:
            raise CliUserError(f"unknown checkpoint '{checkpoint_id}'", code="C905")
        print(
            _format_checkpoint_show(
                checkpoint_id=checkpoint_id,
                refs=refs,
                seed_refs=seed_refs,
                style=style,
            )
        )
        return 0
    if command == "diff":
        if checkpoint_id is None:
            raise CliUserError("state checkpoints diff requires checkpoint id", code="C907")
        checkpoint_model_refs, checkpoint_seed_refs = _read_checkpoint_refs(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
            checkpoint_id=checkpoint_id,
        )
        if not checkpoint_model_refs and not checkpoint_seed_refs:
            raise CliUserError(f"unknown checkpoint '{checkpoint_id}'", code="C905")
        current_refs, current_seed_refs = _read_current_refs(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
            virtual_environment_name=resolved_target_name,
        )
        print(
            _format_checkpoint_diff(
                virtual_environment_name=resolved_target_name,
                checkpoint_id=checkpoint_id,
                current_refs=current_refs,
                current_seed_refs=current_seed_refs,
                checkpoint_model_refs=checkpoint_model_refs,
                checkpoint_seed_refs=checkpoint_seed_refs,
                style=style,
            )
        )
        return 0
    raise CliUserError(f"unknown state checkpoints command '{command}'", code="C906")


def _format_checkpoint_list(
    *,
    virtual_environment_name: str,
    checkpoints: tuple[VirtualEnvironmentCheckpointRecord, ...],
    style: CliStyle,
) -> str:
    document: CliDocument = CliDocument(style)
    document.blank()
    document.header(
        text="Virtual environment checkpoints", suffix=style.object_name(virtual_environment_name)
    )
    document.blank()
    if not checkpoints:
        document.line("  no checkpoints")
        document.blank()
        return document.render(trailing_newline=False)
    checkpoint: VirtualEnvironmentCheckpointRecord
    for checkpoint in checkpoints:
        created_at: str = (
            str(checkpoint.created_at) if checkpoint.created_at is not None else "unknown"
        )
        document.line(f"  {style.accent(checkpoint.checkpoint_id)}  {style.muted(created_at)}")
    document.blank()
    return document.render(trailing_newline=False)


def _format_checkpoint_show(
    *,
    checkpoint_id: str,
    refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...],
    seed_refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...],
    style: CliStyle,
) -> str:
    document: CliDocument = CliDocument(style)
    document.blank()
    document.header(text="Virtual environment checkpoint")
    document.blank()
    document.line(f"  checkpoint           {style.accent(checkpoint_id)}")
    document.blank()
    document.line(style.success("Refs"))
    ref: VirtualEnvironmentCheckpointModelRefRecord
    for ref in refs:
        document.line(
            f"  {style.object_name(f'{ref.model_name:<24}')} {style.muted(ref.version_hash)}"
        )
    if seed_refs:
        document.blank()
        document.line(style.success("Seed refs"))
        seed_ref: VirtualEnvironmentCheckpointSeedRefRecord
        for seed_ref in seed_refs:
            document.line(
                f"  {style.object_name(f'{seed_ref.seed_name:<24}')} "
                f"{style.muted(seed_ref.version_hash)}"
            )
    document.blank()
    return document.render(trailing_newline=False)


def _format_checkpoint_diff(
    *,
    virtual_environment_name: str,
    checkpoint_id: str,
    current_refs: tuple[VirtualEnvironmentModelRefRecord, ...],
    current_seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...],
    checkpoint_model_refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...],
    checkpoint_seed_refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...],
    style: CliStyle,
) -> str:
    current_ref_map: dict[str, str] = {ref.model_name: ref.version_hash for ref in current_refs}
    checkpoint_ref_map: dict[str, str] = {
        ref.model_name: ref.version_hash for ref in checkpoint_model_refs
    }
    current_seed_ref_map: dict[str, str] = {
        ref.seed_name: ref.version_hash for ref in current_seed_refs
    }
    checkpoint_seed_ref_map: dict[str, str] = {
        ref.seed_name: ref.version_hash for ref in checkpoint_seed_refs
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
    changed_seed_refs: tuple[str, ...] = tuple(
        sorted(
            seed_name
            for seed_name, version_hash in current_seed_ref_map.items()
            if seed_name in checkpoint_seed_ref_map
            and checkpoint_seed_ref_map[seed_name] != version_hash
        )
    )
    current_only_seed_refs: tuple[str, ...] = tuple(
        sorted(
            seed_name
            for seed_name in current_seed_ref_map
            if seed_name not in checkpoint_seed_ref_map
        )
    )
    checkpoint_only_seed_refs: tuple[str, ...] = tuple(
        sorted(
            seed_name
            for seed_name in checkpoint_seed_ref_map
            if seed_name not in current_seed_ref_map
        )
    )
    document: CliDocument = CliDocument(style)
    document.blank()
    document.header(
        text="Virtual environment checkpoint diff",
        suffix=style.object_name(virtual_environment_name),
    )
    document.blank()
    document.line(f"  {'checkpoint':<16} {style.accent(checkpoint_id)}")
    document.line(f"  {'changed refs':<16} {style.accent(f'{len(changed):,}')}")
    document.line(f"  {'current only':<16} {style.accent(f'{len(current_only):,}')}")
    document.line(f"  {'checkpoint only':<16} {style.accent(f'{len(checkpoint_only):,}')}")
    document.line(f"  {'changed seeds':<16} {style.accent(f'{len(changed_seed_refs):,}')}")
    document.line(f"  {'current seeds':<16} {style.accent(f'{len(current_only_seed_refs):,}')}")
    document.line(
        f"  {'checkpoint seeds':<16} {style.accent(f'{len(checkpoint_only_seed_refs):,}')}"
    )
    _append_ref_diff_lines(
        document=document,
        label="Changed refs",
        model_names=changed,
        current_ref_map=current_ref_map,
        checkpoint_ref_map=checkpoint_ref_map,
        style=style,
    )
    _append_ref_diff_lines(
        document=document,
        label="Current only",
        model_names=current_only,
        current_ref_map=current_ref_map,
        checkpoint_ref_map=checkpoint_ref_map,
        style=style,
    )
    _append_ref_diff_lines(
        document=document,
        label="Checkpoint only",
        model_names=checkpoint_only,
        current_ref_map=current_ref_map,
        checkpoint_ref_map=checkpoint_ref_map,
        style=style,
    )
    _append_ref_diff_lines(
        document=document,
        label="Changed seed refs",
        model_names=changed_seed_refs,
        current_ref_map=current_seed_ref_map,
        checkpoint_ref_map=checkpoint_seed_ref_map,
        style=style,
    )
    _append_ref_diff_lines(
        document=document,
        label="Current only seed refs",
        model_names=current_only_seed_refs,
        current_ref_map=current_seed_ref_map,
        checkpoint_ref_map=checkpoint_seed_ref_map,
        style=style,
    )
    _append_ref_diff_lines(
        document=document,
        label="Checkpoint only seed refs",
        model_names=checkpoint_only_seed_refs,
        current_ref_map=current_seed_ref_map,
        checkpoint_ref_map=checkpoint_seed_ref_map,
        style=style,
    )
    document.blank()
    return document.render(trailing_newline=False)


def _append_ref_diff_lines(
    *,
    document: CliDocument,
    label: str,
    model_names: tuple[str, ...],
    current_ref_map: dict[str, str],
    checkpoint_ref_map: dict[str, str],
    style: CliStyle,
) -> None:
    if not model_names:
        return
    document.blank()
    document.line(style.success(label))
    for model_name in model_names:
        current_hash: str = current_ref_map.get(model_name, "<missing>")
        checkpoint_hash: str = checkpoint_ref_map.get(model_name, "<missing>")
        model_label: str = style.object_name(f"{model_name:<24}")
        current_label: str = style.muted(current_hash)
        checkpoint_label: str = style.muted(checkpoint_hash)
        document.line(f"  {model_label} {current_label} -> {checkpoint_label}")


def _read_checkpoint_refs(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    checkpoint_id: str,
) -> tuple[
    tuple[VirtualEnvironmentCheckpointModelRefRecord, ...],
    tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...],
]:
    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs, project_dir=project_dir
    )
    connection: Any = backend.connect(config.connection)
    try:
        return (
            backend.get_virtual_environment_checkpoint_model_refs(
                connection=connection, schema=config.schema, checkpoint_id=checkpoint_id
            ),
            backend.get_virtual_environment_checkpoint_seed_refs(
                connection=connection, schema=config.schema, checkpoint_id=checkpoint_id
            ),
        )
    finally:
        backend.close(connection)


def _read_current_refs(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    virtual_environment_name: str,
) -> tuple[
    tuple[VirtualEnvironmentModelRefRecord, ...],
    tuple[VirtualEnvironmentSeedRefRecord, ...],
]:
    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs, project_dir=project_dir
    )
    connection: Any = backend.connect(config.connection)
    try:
        return (
            backend.get_virtual_environment_model_refs(
                connection=connection,
                schema=config.schema,
                virtual_environment_name=virtual_environment_name,
            ),
            backend.get_virtual_environment_seed_refs(
                connection=connection,
                schema=config.schema,
                virtual_environment_name=virtual_environment_name,
            ),
        )
    finally:
        backend.close(connection)
