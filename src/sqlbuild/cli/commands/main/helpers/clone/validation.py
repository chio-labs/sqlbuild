"""Clone command validation helpers."""

from __future__ import annotations

from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import TargetConfig


def validate_clone_request(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    from_target: str,
    to_target: str,
) -> None:
    environments: dict[str, TargetConfig] = discovered_inputs.project_config.targets
    if from_target == to_target:
        raise CliUserError("clone requires different --from and --to environments", code="C401")
    if from_target not in environments:
        raise CliUserError(f"unknown target '{from_target}'", code="C402")
    if to_target not in environments:
        raise CliUserError(f"unknown target '{to_target}'", code="C403")
    if not environments[from_target].clone.allow_as_source:
        raise CliUserError(
            f"environment '{from_target}' is not allowed as a clone source target",
            code="C404",
        )
    if not environments[to_target].clone.allow_as_target:
        raise CliUserError(
            f"environment '{to_target}' is not allowed as a clone target",
            code="C405",
        )
