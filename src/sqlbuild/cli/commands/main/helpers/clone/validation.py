"""Clone command validation helpers."""

from __future__ import annotations

from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import TargetConfig


def validate_clone_request(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    origin_target_name: str,
    destination_target_name: str,
) -> None:
    targets: dict[str, TargetConfig] = discovered_inputs.project_config.targets
    if origin_target_name == destination_target_name:
        raise CliUserError("clone requires different --from and --to targets", code="C401")
    if origin_target_name not in targets:
        raise CliUserError(f"unknown target '{origin_target_name}'", code="C402")
    if destination_target_name not in targets:
        raise CliUserError(f"unknown target '{destination_target_name}'", code="C403")
    if not targets[origin_target_name].clone.allow_as_clone_origin:
        raise CliUserError(
            f"target '{origin_target_name}' is not allowed as a clone origin target",
            code="C404",
        )
    if not targets[destination_target_name].clone.allow_as_clone_destination:
        raise CliUserError(
            f"target '{destination_target_name}' is not allowed as a clone destination target",
            code="C405",
        )
