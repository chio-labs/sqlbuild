"""Install SQLBuild skill files into agent-specific locations."""

from __future__ import annotations

import tomllib
from importlib.resources import files
from importlib.resources.abc import Traversable
from os import replace
from pathlib import Path
from tempfile import NamedTemporaryFile

from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import (
    SkillInstallTarget,
    SkillMaintenanceResult,
    SkillSettings,
    SkillUpdateResult,
)
from sqlbuild.compiler.discovery.constants import PROJECT_CONFIG_FILENAME

generated_marker: str = "<!-- generated-by: sqlbuild skills -->"
legacy_generated_marker: str = "<!-- generated-by: sqlbuild skills update -->"
generated_markers: tuple[str, ...] = (generated_marker, legacy_generated_marker)
skill_name: str = "sqlbuild"
skill_source_package: str = "sqlbuild"
skill_source_path: str = ".agents/skills/sqlbuild/SKILL.md"
valid_skill_targets: tuple[str, ...] = ("opencode", "claude", "agents")
default_skill_targets: tuple[str, ...] = ("agents", "claude")
opencode_skill_target: str = "opencode"
claude_skill_target: str = "claude"


def update_sqlbuild_skills(
    *,
    project_dir: Path,
    global_install: bool = False,
    requested_targets: tuple[str, ...] = (),
    force: bool = False,
    home_dir: Path | None = None,
) -> SkillUpdateResult:
    """Write packaged SQLBuild skill content to configured agent locations."""

    target_names: tuple[str, ...] = resolve_skill_target_names(
        project_dir=project_dir,
        requested_targets=requested_targets,
    )
    install_targets: tuple[SkillInstallTarget, ...] = build_install_targets(
        project_dir=project_dir,
        target_names=target_names,
        global_install=global_install,
        home_dir=home_dir,
    )
    source_content: str = load_packaged_skill_content()
    generated_content: str = ensure_generated_marker(source_content)
    written_paths: list[Path] = []
    for install_target in install_targets:
        write_skill_file(path=install_target.path, content=generated_content, force=force)
        written_paths.append(install_target.path)

    return SkillUpdateResult(written_paths=tuple(written_paths))


def resolve_skill_target_names(
    *, project_dir: Path, requested_targets: tuple[str, ...] = ()
) -> tuple[str, ...]:
    if requested_targets:
        return normalize_skill_targets(targets=requested_targets, source="--target")

    settings: SkillSettings = load_project_skill_settings(project_dir=project_dir)
    if settings.targets:
        return settings.targets

    return default_skill_targets


def normalize_skill_targets(*, targets: tuple[str, ...], source: str) -> tuple[str, ...]:
    normalized_targets: list[str] = []
    seen_targets: set[str] = set()
    for target in targets:
        normalized_target: str = target.strip().lower()
        if normalized_target not in valid_skill_targets:
            allowed_targets: str = ", ".join(valid_skill_targets)
            raise CliUserError(
                f"{source} contains unsupported skill target '{target}'",
                code="C801",
                help=f"supported targets are: {allowed_targets}",
            )
        if normalized_target in seen_targets:
            continue
        normalized_targets.append(normalized_target)
        seen_targets.add(normalized_target)

    return tuple(normalized_targets)


def load_project_skill_targets(*, project_dir: Path) -> tuple[str, ...]:
    return load_project_skill_settings(project_dir=project_dir).targets


def load_project_skill_settings(*, project_dir: Path) -> SkillSettings:
    config_path: Path = project_dir / PROJECT_CONFIG_FILENAME
    if not config_path.exists():
        return SkillSettings(targets=(), auto_update=False, configured=False)

    try:
        with config_path.open("rb") as config_file:
            payload: object = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as error:
        raise CliUserError(
            f"{config_path} contains invalid TOML: {error}",
            code="C802",
        ) from error
    if not isinstance(payload, dict):
        return SkillSettings(targets=(), auto_update=False, configured=False)

    skills_payload: object = payload.get("skills")
    if skills_payload is None:
        return SkillSettings(targets=(), auto_update=False, configured=False)
    if not isinstance(skills_payload, dict):
        raise CliUserError(
            f"{config_path} [skills] must be a table",
            code="C803",
        )

    targets_payload: object = skills_payload.get("targets")
    if targets_payload is not None and (
        not isinstance(targets_payload, list)
        or not all(isinstance(target, str) for target in targets_payload)
    ):
        raise CliUserError(
            f"{config_path} skills.targets must be a list of strings",
            code="C804",
        )
    auto_update: object = skills_payload.get("auto_update", False)
    if not isinstance(auto_update, bool):
        raise CliUserError(
            f"{config_path} skills.auto_update must be a boolean",
            code="C808",
        )
    targets: tuple[str, ...] = (
        ()
        if targets_payload is None
        else normalize_skill_targets(targets=tuple(targets_payload), source="skills.targets")
    )
    return SkillSettings(
        targets=targets or default_skill_targets,
        auto_update=auto_update,
        configured=True,
    )


def maintain_sqlbuild_skills(*, project_dir: Path) -> SkillMaintenanceResult:
    """Check or refresh generated project skills without changing command success."""

    settings: SkillSettings = load_project_skill_settings(project_dir=project_dir)
    target_names: tuple[str, ...] = settings.targets
    if not settings.configured:
        target_names = tuple(
            target_name
            for target_name in valid_skill_targets
            if _local_install_path(project_dir=project_dir, target_name=target_name).exists()
        )
    if not target_names:
        return SkillMaintenanceResult()

    install_targets: tuple[SkillInstallTarget, ...] = build_install_targets(
        project_dir=project_dir,
        target_names=target_names,
    )
    expected_content: str = ensure_generated_marker(load_packaged_skill_content())
    stale_paths: list[Path] = []
    collision_paths: list[Path] = []
    for install_target in install_targets:
        path: Path = install_target.path
        if not path.exists():
            stale_paths.append(path)
            continue
        existing_content: str = path.read_text(encoding="utf-8")
        if existing_content == expected_content:
            continue
        if not any(marker in existing_content for marker in generated_markers):
            collision_paths.append(path)
            continue
        stale_paths.append(path)

    if settings.auto_update and stale_paths:
        for path in stale_paths:
            write_skill_file(path=path, content=expected_content)
        message: str = "\nUpdated stale SQLBuild skill files:\n" + "".join(
            f"  {path}\n" for path in stale_paths
        )
        if collision_paths:
            message += _stale_skill_message(collision_paths=collision_paths)
        return SkillMaintenanceResult(message=message)
    if stale_paths or collision_paths:
        return SkillMaintenanceResult(message=_stale_skill_message(collision_paths=collision_paths))
    return SkillMaintenanceResult()


def _stale_skill_message(*, collision_paths: list[Path]) -> str:
    collision_detail: str = ""
    if collision_paths:
        collision_detail = "  Custom files were not overwritten:\n" + "".join(
            f"    {path}\n" for path in collision_paths
        )
    return f"\nSQLBuild skill files are out of date\n{collision_detail}  Run: sqb skills\n"


def _local_install_path(*, project_dir: Path, target_name: str) -> Path:
    return build_install_targets(
        project_dir=project_dir,
        target_names=(target_name,),
    )[0].path


def build_install_targets(
    *,
    project_dir: Path,
    target_names: tuple[str, ...],
    global_install: bool = False,
    home_dir: Path | None = None,
) -> tuple[SkillInstallTarget, ...]:
    home_path: Path = home_dir if home_dir is not None else Path.home()
    install_targets: list[SkillInstallTarget] = []
    for target_name in target_names:
        base_path: Path
        if target_name == opencode_skill_target:
            base_path = (
                home_path / ".config/opencode" if global_install else project_dir / ".opencode"
            )
        elif target_name == claude_skill_target:
            base_path = home_path / ".claude" if global_install else project_dir / ".claude"
        else:
            base_path = home_path / ".agents" if global_install else project_dir / ".agents"
        install_targets.append(
            SkillInstallTarget(
                name=target_name,
                path=base_path / "skills" / skill_name / "SKILL.md",
            )
        )
    return tuple(install_targets)


def load_packaged_skill_content() -> str:
    skill_file: Traversable = files(skill_source_package).joinpath(*skill_source_path.split("/"))
    if not skill_file.is_file():
        raise CliUserError(
            "packaged SQLBuild skill is missing",
            code="C805",
            help="reinstall SQLBuild or report a packaging issue",
        )
    return skill_file.read_text(encoding="utf-8")


def ensure_generated_marker(content: str) -> str:
    if generated_marker in content:
        return content
    if legacy_generated_marker in content:
        return content.replace(legacy_generated_marker, generated_marker, 1)
    if content.startswith("---\n"):
        frontmatter_end: int = content.find("\n---\n", 4)
        if frontmatter_end != -1:
            insert_at: int = frontmatter_end + len("\n---\n")
            return f"{content[:insert_at]}\n{generated_marker}\n{content[insert_at:]}"
    return f"{generated_marker}\n{content}"


def write_skill_file(*, path: Path, content: str, force: bool = False) -> None:
    if path.exists():
        existing_content: str = path.read_text(encoding="utf-8")
        if not any(marker in existing_content for marker in generated_markers) and not force:
            raise CliUserError(
                f"refusing to overwrite non-generated skill file: {path}",
                code="C806",
                help="rerun with --force to replace it",
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temporary_file:
        _ = temporary_file.write(content)
        temporary_path: Path = Path(temporary_file.name)
    replace(temporary_path, path)
