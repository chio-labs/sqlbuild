"""Project builders and filesystem changes for project input fingerprint tests."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from sqlbuild.cli.compile_reuse._helpers.project_files import (
    is_racy,
    project_file_digests,
    snapshot_project_files,
)
from sqlbuild.cli.compile_reuse._helpers.runtime_identity import (
    environment_digest,
    invocation_digest,
    tracked_environment_names,
)
from sqlbuild.cli.compile_reuse.constants import RACY_WINDOW_NS
from sqlbuild.cli.compile_reuse.models import (
    CompileReuseRequest,
    SettingsEnvironmentInputs,
    SettingsInputsResult,
    StoredProjectFile,
)
from sqlbuild.cli.compile_reuse.types import FileStamp
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR, STAGE_CAPTURE_DIR_ENV_VAR

_LATER_SNAPSHOT_NS: int = 10 * RACY_WINDOW_NS


def write_file(path: Path, contents: str) -> None:
    """Write one file, creating parent folders."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def write_fingerprint_project(root: Path) -> Path:
    """Create a project with links, excluded folders, and presence-only database files."""

    project_dir: Path = root / "project"
    write_file(project_dir / "sqlbuild_project.toml", 'name = "orders"\nadapter = "duckdb"\n')
    write_file(project_dir / "models/orders.sql", "SELECT 1 AS order_id\n")
    write_file(project_dir / "models/.drafts/returns.sql", "SELECT 2 AS return_id\n")
    write_file(project_dir / "macros/currency.py", "def cents() -> str:\n    return 'cents'\n")
    write_file(project_dir / "macros/__pycache__/currency.cpython-312.pyc", "bytecode")
    write_file(project_dir / "target/compiled/models/orders.sql", "SELECT 1 AS order_id\n")
    write_file(project_dir / "logs/compile.log", "compile log\n")
    write_file(project_dir / ".venv/lib/vendored.py", "VALUE = 1\n")
    write_file(project_dir / ".git/HEAD", "ref: refs/heads/main\n")
    write_file(project_dir / ".vscode/settings.json", "{}\n")
    write_file(project_dir / ".orders_rules/limits.txt", "40\n")
    write_file(project_dir / "warehouse.duckdb", "database pages")
    write_file(root / "shared/customers.sql", "SELECT 3 AS customer_id\n")
    write_file(root / "shared_dir/products.sql", "SELECT 4 AS product_id\n")
    (project_dir / "models/customers.sql").symlink_to(root / "shared/customers.sql")
    (project_dir / "models/shared").symlink_to(root / "shared_dir", target_is_directory=True)
    return project_dir


def stored_project_files(*, project_dir: Path, snapshot_ns: int) -> dict[str, StoredProjectFile]:
    """Record the project as a stored compile would, with digests for every readable file."""

    snapshot: dict[str, FileStamp] = snapshot_project_files(project_dir=str(project_dir))
    digests: list[str | None] = project_file_digests(
        project_dir=str(project_dir), relative_paths=list(snapshot)
    )
    return {
        relative_path: StoredProjectFile(
            stamp=stamp,
            digest=digest,
            racy=is_racy(stamp=stamp, snapshot_ns=snapshot_ns),
        )
        for (relative_path, stamp), digest in zip(snapshot.items(), digests, strict=True)
    }


def later_snapshot_ns() -> int:
    """Return a snapshot time after which no current file counts as racy."""

    return time.time_ns() + _LATER_SNAPSHOT_NS


def touch_without_change(project_dir: Path) -> None:
    """Move a file's mtime forward without changing its content."""

    path: Path = project_dir / "models/orders.sql"
    mtime_ns: int = path.stat().st_mtime_ns + RACY_WINDOW_NS
    os.utime(path, ns=(mtime_ns, mtime_ns))


def rewrite_same_size_keeping_mtime(project_dir: Path) -> None:
    """Change content without changing size, then restore the previous mtime."""

    path: Path = project_dir / "models/orders.sql"
    mtime_ns: int = path.stat().st_mtime_ns
    path.write_text("SELECT 9 AS order_id\n", encoding="utf-8")
    os.utime(path, ns=(mtime_ns, mtime_ns))


def edit_link_target(project_dir: Path) -> None:
    """Edit the file a project link points to, outside the project."""

    (project_dir.parent / "shared/customers.sql").write_text(
        "SELECT 30 AS customer_id\n", encoding="utf-8"
    )


def retarget_link(project_dir: Path) -> None:
    """Point a project link at another file with identical content."""

    link: Path = project_dir / "models/customers.sql"
    replacement: Path = project_dir.parent / "shared/customers_copy.sql"
    replacement.write_text("SELECT 3 AS customer_id\n", encoding="utf-8")
    link.unlink()
    link.symlink_to(replacement)


def add_file_in_linked_directory(project_dir: Path) -> None:
    """Add a file inside a directory the project links to."""

    write_file(project_dir.parent / "shared_dir/suppliers.sql", "SELECT 5 AS supplier_id\n")


def break_link(project_dir: Path) -> None:
    """Delete the target of a project link."""

    (project_dir.parent / "shared/customers.sql").unlink()


def stat_only_project_files(*, project_dir: Path) -> dict[str, StoredProjectFile]:
    """Record the project as a stored compile does by default: stat stamps without digests."""

    return {
        relative_path: StoredProjectFile(stamp=stamp, digest=None, racy=False)
        for relative_path, stamp in snapshot_project_files(project_dir=str(project_dir)).items()
    }


SETTINGS_TOKEN_ENV_VAR: str = "ORDERS_API_TOKEN"
SETTINGS_ENV_FILE_NAME: str = "orders_api.env"
SETTINGS_SECRETS_DIR_NAME: str = "orders_secrets"


class OrdersApiSettings(BaseSettings):
    """Plain provider settings read from one environment variable per field."""

    orders_api_token: str = ""


class PrefixedOrdersSettings(BaseSettings):
    """Provider settings read through an environment prefix."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(env_prefix="ORDERS_")

    token: str = ""


class AliasedOrdersSettings(BaseSettings):
    """Provider settings read through alias choices."""

    token: str = Field(default="", validation_alias=AliasChoices("ORDERS_KEY", "LEGACY_KEY"))


class OrdersEndpoint(BaseModel):
    """Nested endpoint settings."""

    host: str = "localhost"


class NestedOrdersSettings(BaseSettings):
    """Provider settings with nested values split by a delimiter."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(env_nested_delimiter="__")

    endpoint: OrdersEndpoint = OrdersEndpoint()


class CaseSensitiveOrdersSettings(BaseSettings):
    """Provider settings matched case-sensitively."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(case_sensitive=True)

    OrdersToken: str = ""


class FileOrdersSettings(BaseSettings):
    """Provider settings that also read an env file and a secrets directory."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=SETTINGS_ENV_FILE_NAME, secrets_dir=SETTINGS_SECRETS_DIR_NAME
    )

    orders_api_token: str = ""


class CustomSourceOrdersSettings(BaseSettings):
    """Provider settings whose sources cannot be enumerated."""

    orders_api_token: str = ""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Read only the environment."""

        return (env_settings,)


class CommandLineOrdersSettings(BaseSettings):
    """Provider settings that would parse command-line arguments."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(cli_parse_args=False)

    orders_api_token: str = ""


def file_settings_inputs(*, root: Path) -> SettingsEnvironmentInputs:
    """Describe FileOrdersSettings as if read from root, the process working directory."""

    return SettingsEnvironmentInputs(
        case_sensitive=False,
        names=("orders_api_token",),
        prefixes=(),
        env_files=(str(root / SETTINGS_ENV_FILE_NAME),),
        secrets_dirs=(str(root / SETTINGS_SECRETS_DIR_NAME),),
    )


def set_token(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """Set the tracked token variable."""

    monkeypatch.setenv(SETTINGS_TOKEN_ENV_VAR, value)


def write_settings_file(root: Path, relative_path: str, contents: str) -> None:
    """Write one env file or secrets file below root."""

    write_file(root / relative_path, contents)


def described_settings_inputs(
    *, result: SettingsInputsResult
) -> tuple[tuple[bool, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...]:
    """Describe enumerated settings inputs with file and directory paths reduced to names."""

    return tuple(
        (
            item.case_sensitive,
            item.names,
            item.prefixes,
            _path_names(item.env_files),
            _path_names(item.secrets_dirs),
        )
        for item in result.inputs
    )


def _path_names(paths: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(Path(path).name for path in paths)


def orders_reuse_request(project_dir: Path) -> CompileReuseRequest:
    """Return a plain JSON compile reuse request for a project."""

    return CompileReuseRequest(
        project_dir=project_dir,
        selected_target=None,
        json_output=True,
        no_color=True,
        manifest=False,
        dag_path=None,
        defer_to=None,
        no_cache=False,
        no_sql_validation=False,
        lineage_mode="fast",
        select=(),
        exclude=(),
        cli_vars=None,
        profiling=False,
        debug=False,
    )


def engine_reuse_key(
    *, environment: dict[str, str], project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, str]:
    """Return the invocation and environment digests computed under one engine environment."""

    monkeypatch.delenv(COMPILER_ENGINE_ENV_VAR, raising=False)
    monkeypatch.delenv(STAGE_CAPTURE_DIR_ENV_VAR, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    return (
        invocation_digest(
            request=orders_reuse_request(project_dir), project_dir=str(project_dir), use_color=False
        ),
        environment_digest(names=tracked_environment_names(template_names=())),
    )
