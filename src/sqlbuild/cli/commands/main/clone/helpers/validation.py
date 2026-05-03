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
        raise CliUserError("clone requires different --from and --to environments")
    if from_environment not in environments:
        raise CliUserError(f"Unknown environment '{from_environment}'")
    if to_environment not in environments:
        raise CliUserError(f"Unknown environment '{to_environment}'")
    if not environments[from_environment].clone.allow_as_source:
        raise CliUserError(f"Environment '{from_environment}' is not allowed as a clone source")
    if not environments[to_environment].clone.allow_as_target:
        raise CliUserError(f"Environment '{to_environment}' is not allowed as a clone target")
