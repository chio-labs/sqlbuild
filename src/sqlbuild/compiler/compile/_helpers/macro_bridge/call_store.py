"""Resolve the compile target and hand the running macro bridge its call store."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile._helpers.attachment.target import build_compile_target_context
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.macro_bridge.classes.macro_bridge import MacroBridge
from sqlbuild.compiler.macro_bridge.main.active_macro_bridge import active_macro_bridge
from sqlbuild.spec.contracts.models import TargetConfig


def target_context_with_macro_call_store(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None,
    no_cache: bool,
) -> tuple[str | None, TargetConfig | None, Path | None]:
    """Resolve the target and cache directory, loading stored macro calls when a bridge runs."""

    target_context: tuple[str | None, TargetConfig | None, Path | None] = (
        build_compile_target_context(
            discovered_inputs=discovered_inputs,
            selected_target=selected_target,
            no_cache=no_cache,
        )
    )
    bridge: MacroBridge | None = active_macro_bridge()
    project_dir: Path | None = discovered_inputs.project_dir
    compile_cache_dir: Path | None = target_context[2]
    if bridge is not None and compile_cache_dir is not None and project_dir is not None:
        bridge.attach_store(
            cache_dir=compile_cache_dir,
            project_dir=project_dir,
            model_paths=_model_paths(discovered_inputs=discovered_inputs, project_dir=project_dir),
        )
    return target_context


def _model_paths(*, discovered_inputs: DiscoveredProjectInputs, project_dir: Path) -> list[str]:
    paths: list[str] = []
    for model_file in discovered_inputs.model_files:
        try:
            paths.append(model_file.file_path.relative_to(project_dir).as_posix())
        except ValueError:
            continue
    return paths
