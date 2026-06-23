"""Effective project settings helper for compile and CLI entrypoints."""

from __future__ import annotations

from sqlbuild.compiler.compile.helpers.attachment.core import build_effective_settings
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import SettingsConfig


def build_effective_settings_config(
    *, discovered_inputs: DiscoveredProjectInputs
) -> SettingsConfig:
    """Build effective settings without compiling resources."""

    return build_effective_settings(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
