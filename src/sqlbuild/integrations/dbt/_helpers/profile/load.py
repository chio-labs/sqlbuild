"""Load dbt project and profile YAML files."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml
from yaml import YAMLError

from sqlbuild.integrations.dbt.exceptions import DbtProfileError
from sqlbuild.integrations.dbt.models import (
    DbtProjectProfileMetadata,
    RawDbtProfile,
    SelectedDbtProfileOutput,
)


def load_dbt_project_metadata(*, project_dir: Path) -> DbtProjectProfileMetadata:
    """Load dbt project metadata required for profile resolution."""

    project_file: Path = project_dir / "dbt_project.yml"
    payload: dict[str, object] = _load_yaml_mapping(file_path=project_file)
    project_name: str = _required_string(payload=payload, key="name", file_path=project_file)
    profile_name: str = _required_string(payload=payload, key="profile", file_path=project_file)
    target_path_value: object | None = payload.get("target-path")
    target_path: str = "target"
    if target_path_value is not None:
        if not isinstance(target_path_value, str) or not target_path_value.strip():
            raise DbtProfileError(f"{project_file} target-path must be a non-empty string")
        target_path = target_path_value.strip()
    return DbtProjectProfileMetadata(
        project_name=project_name,
        profile_name=profile_name,
        target_path=target_path,
    )


def load_raw_dbt_profile(*, profiles_dir: Path, profile_name: str) -> RawDbtProfile:
    """Load one dbt profile from profiles.yml."""

    profiles_file: Path = profiles_dir / "profiles.yml"
    payload: dict[str, object] = _load_yaml_mapping(file_path=profiles_file)
    profile_payload: object | None = payload.get(profile_name)
    if not isinstance(profile_payload, dict):
        raise DbtProfileError(f"{profiles_file} does not define dbt profile '{profile_name}'")
    profile_mapping: dict[str, object] = cast(dict[str, object], profile_payload)
    raw_outputs: object | None = profile_mapping.get("outputs")
    if not isinstance(raw_outputs, dict) or not raw_outputs:
        raise DbtProfileError(f"dbt profile '{profile_name}' must define non-empty outputs")
    outputs: dict[str, dict[str, object]] = {}
    output_name: object
    output_value: object
    for output_name, output_value in raw_outputs.items():
        if not isinstance(output_name, str) or not output_name.strip():
            raise DbtProfileError(f"dbt profile '{profile_name}' contains an invalid output name")
        if not isinstance(output_value, dict):
            raise DbtProfileError(
                f"dbt profile '{profile_name}' output '{output_name}' must be a mapping"
            )
        outputs[output_name.strip()] = cast(dict[str, object], output_value)
    default_target_value: object | None = profile_mapping.get("target")
    default_target: str | None = None
    if default_target_value is not None:
        if not isinstance(default_target_value, str) or not default_target_value.strip():
            raise DbtProfileError(f"dbt profile '{profile_name}' target must be a non-empty string")
        default_target = default_target_value.strip()
    return RawDbtProfile(name=profile_name, default_target=default_target, outputs=outputs)


def select_dbt_profile_output(
    *, profile: RawDbtProfile, target_name: str | None
) -> SelectedDbtProfileOutput:
    """Select one dbt profile output target without rendering other outputs."""

    selected_target: str | None = target_name or profile.default_target
    if selected_target is None:
        raise DbtProfileError(
            f"dbt profile '{profile.name}' does not define a default target; pass --target"
        )
    output: dict[str, object] | None = profile.outputs.get(selected_target)
    if output is None:
        available: str = ", ".join(sorted(profile.outputs))
        raise DbtProfileError(
            f"dbt profile '{profile.name}' does not define target '{selected_target}'. "
            f"Available targets: {available}"
        )
    return SelectedDbtProfileOutput(
        profile_name=profile.name,
        target_name=selected_target,
        output=output,
    )


def default_profiles_dir() -> Path:
    """Return dbt's default profiles directory."""

    return Path("~/.dbt").expanduser()


def _load_yaml_mapping(*, file_path: Path) -> dict[str, object]:
    if not file_path.exists():
        raise DbtProfileError(f"dbt config file not found: {file_path}")
    try:
        payload: object = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except YAMLError as error:
        raise DbtProfileError(f"{file_path} contains invalid YAML: {error}") from error
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise DbtProfileError(f"{file_path} must contain a top-level mapping")
    return cast(dict[str, object], payload)


def _required_string(*, payload: dict[str, object], key: str, file_path: Path) -> str:
    value: object | None = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DbtProfileError(f"{file_path} must define non-empty string '{key}'")
    return value.strip()
