"""Build the first attached compile input snapshot from discovered inputs."""

from __future__ import annotations

from sqlbuild.compiler.compile.helpers.attachment import (
    build_model_inputs,
    build_seed_inputs,
    build_source_inputs,
)
from sqlbuild.compiler.compile.models import (
    CompileModelInput,
    CompileProjectInputs,
    CompileSeedInput,
    CompileSourceInput,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs


def build_compile_inputs(discovered_inputs: DiscoveredProjectInputs) -> CompileProjectInputs:
    """Attach discovered metadata into the first compile input snapshot."""

    model_inputs: tuple[CompileModelInput, ...] = build_model_inputs(discovered_inputs)
    seed_inputs: tuple[CompileSeedInput, ...] = build_seed_inputs(discovered_inputs)
    source_inputs: tuple[CompileSourceInput, ...] = build_source_inputs(discovered_inputs)
    return CompileProjectInputs(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        discovered_inputs=discovered_inputs,
        model_inputs=model_inputs,
        seed_inputs=seed_inputs,
        source_inputs=source_inputs,
    )
