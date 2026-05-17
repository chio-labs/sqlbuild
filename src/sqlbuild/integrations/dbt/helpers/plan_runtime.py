"""Runtime support helpers for dbt interop planning."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.helpers.builtins import builtin_adapter_classes
from sqlbuild.adapter.strict.strict_adapter import StrictAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError
from sqlbuild.integrations.dbt.helpers.config import resolve_dbt_config
from sqlbuild.integrations.dbt.models import DbtCliConfigOverrides, DbtCliOptions, ResolvedDbtConfig
from sqlbuild.shared.helpers.adapters import discover_project_adapters


def resolve_dbt_plan_options(
    *, project_dir: Path, discovered_inputs: DiscoveredProjectInputs, dbt_args: tuple[str, ...]
) -> DbtCliOptions:
    """Resolve dbt CLI options for `sqb dbt plan`."""

    overrides: DbtCliConfigOverrides = parse_dbt_config_overrides(dbt_args)
    resolved: ResolvedDbtConfig = resolve_dbt_config(
        project_root=project_dir,
        config=discovered_inputs.project_config.dbt,
        overrides=overrides,
        require_project_dir=True,
    )
    return DbtCliOptions(
        project_dir=resolved.project_dir,
        profiles_dir=resolved.profiles_dir,
        target=resolved.target,
        target_path=resolved.target_path,
        vars=parse_value_flag(dbt_args, "--vars"),
        state=parse_optional_path_flag(dbt_args, "--state", project_root=project_dir),
        defer="--defer" in dbt_args,
    )


def parse_dbt_config_overrides(dbt_args: tuple[str, ...]) -> DbtCliConfigOverrides:
    """Parse dbt project/profile/target overrides from routed dbt args."""

    return DbtCliConfigOverrides(
        project_dir=parse_value_flag(dbt_args, "--project-dir"),
        profiles_dir=parse_value_flag(dbt_args, "--profiles-dir"),
        target=parse_value_flag(dbt_args, "--target"),
        target_path=parse_value_flag(dbt_args, "--target-path"),
    )


def parse_value_flag(args: tuple[str, ...], flag: str) -> str | None:
    """Return the value after a flag, if present."""

    if flag not in args:
        return None
    index: int = args.index(flag)
    if index + 1 >= len(args):
        return None
    return args[index + 1]


def parse_optional_path_flag(
    args: tuple[str, ...], flag: str, *, project_root: Path
) -> Path | None:
    """Return a path flag value resolved relative to the SQLBuild project."""

    raw_value: str | None = parse_value_flag(args, flag)
    if raw_value is None:
        return None
    path: Path = Path(raw_value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (project_root.expanduser().resolve() / path).resolve()


def resolve_dbt_manifest_path(*, options: DbtCliOptions) -> Path:
    """Resolve the manifest path produced by dbt compile."""

    if options.project_dir is None:
        raise DbtInteropConfigError("dbt project directory is not configured")
    target_path: Path = options.target_path or (options.project_dir / "target")
    return target_path / "manifest.json"


def resolve_dbt_interop_adapter(
    adapter_name: str, *, project_dir: Path | None = None
) -> BaseAdapter:
    """Resolve an adapter for dbt interop runtime planning."""

    builtin_adapters: dict[str, type[BaseAdapter]] = builtin_adapter_classes()
    adapter_class: type[StrictAdapter] | type[BaseAdapter] | None = None
    if project_dir is not None:
        local_adapters: dict[str, type[StrictAdapter]] = discover_project_adapters(
            project_dir=project_dir,
            reserved_names=frozenset(builtin_adapters),
        )
        adapter_class = local_adapters.get(adapter_name)
    if adapter_class is None:
        adapter_class = builtin_adapters.get(adapter_name)
    if adapter_class is None:
        available: tuple[str, ...] = tuple(sorted(builtin_adapters))
        raise DbtInteropConfigError(
            f"unknown adapter '{adapter_name}'. Available built-in adapters: "
            f"{', '.join(available)}."
        )
    return cast(BaseAdapter, adapter_class())
