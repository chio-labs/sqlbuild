"""Clone command validation helpers."""

from __future__ import annotations

from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.contracts.main.resolve_target_config import resolve_target_config
from sqlbuild.spec.contracts.models import TargetConfig


def validate_clone_request(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    origin_target_name: str,
    destination_target_name: str,
) -> None:
    project_targets: dict[str, TargetConfig] = discovered_inputs.project_config.targets
    local_target_names: set[str] = set(discovered_inputs.local_config.targets)
    target_names: set[str] = set(project_targets) | local_target_names
    if origin_target_name == destination_target_name:
        raise CliUserError("clone requires different --from and --to targets", code="C401")
    if origin_target_name not in target_names:
        raise CliUserError(f"unknown target '{origin_target_name}'", code="C402")
    if destination_target_name not in target_names:
        raise CliUserError(f"unknown target '{destination_target_name}'", code="C403")
    origin_target: TargetConfig = resolve_target_config(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        target_name=origin_target_name,
    )
    destination_target: TargetConfig = resolve_target_config(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        target_name=destination_target_name,
    )
    if not origin_target.clone.allow_as_clone_origin:
        raise CliUserError(
            (
                f"target '{origin_target_name}' is not allowed as a clone origin target; "
                f"set targets.{origin_target_name}.clone.allow_as_clone_origin = true"
            ),
            code="C404",
        )
    if not destination_target.clone.allow_as_clone_destination:
        raise CliUserError(
            (
                f"target '{destination_target_name}' is not allowed as a clone destination "
                f"target; set targets.{destination_target_name}.clone."
                "allow_as_clone_destination = true"
            ),
            code="C405",
        )
