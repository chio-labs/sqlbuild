from pathlib import Path

from tests.unit.scripts.native_layering._helpers._test_types import (
    NativeLayeringTestCase,
    NativeVersionTestCase,
)


def write_workspace(root: Path, test_case: NativeLayeringTestCase) -> None:
    """Write a minimal Cargo workspace and lockfile shaped like the native crates."""
    members: str = ", ".join(f'"crates/{name}"' for name in test_case.crate_dependencies)
    order: str = ", ".join(f'"{name}"' for name in test_case.order)
    aliases: str = "".join(
        f'{alias} = {{ path = "crates/{package}", package = "{package}" }}\n'
        for alias, package in test_case.workspace_aliases.items()
    )
    (root / "Cargo.toml").write_text(
        f"[workspace]\nmembers = [{members}]\n\n"
        "[workspace.metadata.native-layers]\n"
        f"order = [{order}]\n"
        'python-boundary = "sqlbuild-python"\n'
        'polyglot-floor = "sqlbuild-analysis"\n\n'
        f"[workspace.dependencies]\n{aliases}",
        encoding="utf-8",
    )
    lock: list[str] = ["version = 4\n"]
    for name, dependencies in test_case.crate_dependencies.items():
        crate: Path = root / "crates" / name
        crate.mkdir(parents=True)
        listed: str = "".join(f"{dependency}.workspace = true\n" for dependency in dependencies)
        (crate / "Cargo.toml").write_text(
            f'[package]\nname = "{name}"\n\n[dependencies]\n{listed}', encoding="utf-8"
        )
        lock.append(_lock_package(name, dependencies))
    for name, dependencies in test_case.external_dependencies.items():
        lock.append(_lock_package(name, dependencies))
    (root / "Cargo.lock").write_text("\n".join(lock), encoding="utf-8")


def _lock_package(name: str, dependencies: tuple[str, ...]) -> str:
    listed: str = ", ".join(f'"{dependency}"' for dependency in dependencies)
    return f'[[package]]\nname = "{name}"\nversion = "0.1.0"\ndependencies = [{listed}]\n'


def write_versions(root: Path, test_case: NativeVersionTestCase) -> None:
    """Write the release version sources and the lockfile entries the version check compares.

    Every crate in `lock_versions` is a workspace member that inherits the workspace version, and
    its Cargo.lock entry carries the mapped version; a registry crate rides along unchanged. The
    uv.lock project entry carries `python_lock_version`, defaulting to the pyproject version.
    """
    members: str = ", ".join(f'"crates/{name}"' for name in test_case.lock_versions)
    (root / "Cargo.toml").write_text(
        f"[workspace]\nmembers = [{members}]\n\n"
        f'[workspace.package]\nversion = "{test_case.workspace_version}"\n',
        encoding="utf-8",
    )
    lock: list[str] = [
        "version = 4\n",
        '[[package]]\nname = "serde"\nversion = "1.0.0"\n'
        'source = "registry+https://github.com/rust-lang/crates.io-index"\n',
    ]
    for name, version in test_case.lock_versions.items():
        crate: Path = root / "crates" / name
        crate.mkdir(parents=True)
        (crate / "Cargo.toml").write_text(
            f'[package]\nname = "{name}"\nversion.workspace = true\n', encoding="utf-8"
        )
        lock.append(f'[[package]]\nname = "{name}"\nversion = "{version}"\n')
    (root / "Cargo.lock").write_text("\n".join(lock), encoding="utf-8")
    python_lock_version: str = test_case.python_lock_version or test_case.pyproject_version
    (root / "uv.lock").write_text(
        "version = 1\n\n"
        '[[package]]\nname = "example"\n'
        f'version = "{python_lock_version}"\nsource = {{ editable = "." }}\n\n'
        '[[package]]\nname = "example-cli"\nsource = { directory = "crates/example-cli" }\n',
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "example"\nversion = "{test_case.pyproject_version}"\n'
        f'dependencies = ["sqlbuild-cli=={test_case.cli_version}"]\n',
        encoding="utf-8",
    )
    (root / ".release-please-manifest.json").write_text(
        f'{{".": "{test_case.release_version}"}}\n', encoding="utf-8"
    )
