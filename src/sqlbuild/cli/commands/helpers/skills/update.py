"""Install SQLBuild skill files into agent-specific locations."""

from __future__ import annotations

import tomllib
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from sqlbuild.cli.commands.helpers.skills.models import SkillInstallTarget, SkillUpdateResult
from sqlbuild.cli.commands.shared.exceptions import CliUserError
from sqlbuild.compiler.discovery.constants import PROJECT_CONFIG_FILENAME

generated_marker: str = "<!-- generated-by: sqlbuild skills update -->"
skill_name: str = "sqlbuild"
skill_source_package: str = "sqlbuild"
skill_source_path: str = ".agents/skills/sqlbuild/SKILL.md"
valid_skill_targets: tuple[str, ...] = ("opencode", "claude", "agents")


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

    configured_targets: tuple[str, ...] = load_project_skill_targets(project_dir=project_dir)
    if configured_targets:
        return configured_targets

    return valid_skill_targets


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
    config_path: Path = project_dir / PROJECT_CONFIG_FILENAME
    if not config_path.exists():
        return ()

    try:
        with config_path.open("rb") as config_file:
            payload: object = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as error:
        raise CliUserError(
            f"{config_path} contains invalid TOML: {error}",
            code="C802",
        ) from error
    if not isinstance(payload, dict):
        return ()

    skills_payload: object = payload.get("skills")
    if skills_payload is None:
        return ()
    if not isinstance(skills_payload, dict):
        raise CliUserError(
            f"{config_path} [skills] must be a table",
            code="C803",
        )

    targets_payload: object = skills_payload.get("targets")
    if targets_payload is None:
        return ()
    if not isinstance(targets_payload, list) or not all(
        isinstance(target, str) for target in targets_payload
    ):
        raise CliUserError(
            f"{config_path} skills.targets must be a list of strings",
            code="C804",
        )
    return normalize_skill_targets(targets=tuple(targets_payload), source="skills.targets")


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
        if target_name == "opencode":
            base_path = (
                home_path / ".config/opencode" if global_install else project_dir / ".opencode"
            )
        elif target_name == "claude":
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
    if content.startswith("---\n"):
        frontmatter_end: int = content.find("\n---\n", 4)
        if frontmatter_end != -1:
            insert_at: int = frontmatter_end + len("\n---\n")
            return f"{content[:insert_at]}\n{generated_marker}\n{content[insert_at:]}"
    return f"{generated_marker}\n{content}"


def write_skill_file(*, path: Path, content: str, force: bool = False) -> None:
    if path.exists():
        existing_content: str = path.read_text(encoding="utf-8")
        if generated_marker not in existing_content and not force:
            raise CliUserError(
                f"refusing to overwrite non-generated skill file: {path}",
                code="C806",
                help="rerun with --force to replace it",
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
