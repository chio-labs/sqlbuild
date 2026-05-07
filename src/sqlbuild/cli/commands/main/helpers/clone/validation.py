"""Clone command validation helpers."""

from __future__ import annotations

from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import EnvironmentConfig


def validate_clone_request(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    from_environment: str,
    to_environment: str,
) -> None:
    environments: dict[str, EnvironmentConfig] = discovered_inputs.project_config.environments
    if from_environment == to_environment:
        raise CliUserError("clone requires different --from and --to environments", code="C401")
    if from_environment not in environments:
        raise CliUserError(f"unknown environment '{from_environment}'", code="C402")
    if to_environment not in environments:
        raise CliUserError(f"unknown environment '{to_environment}'", code="C403")
    if not environments[from_environment].clone.allow_as_source:
        raise CliUserError(
            f"environment '{from_environment}' is not allowed as a clone source",
            code="C404",
        )
    if not environments[to_environment].clone.allow_as_target:
        raise CliUserError(
            f"environment '{to_environment}' is not allowed as a clone target",
            code="C405",
        )
