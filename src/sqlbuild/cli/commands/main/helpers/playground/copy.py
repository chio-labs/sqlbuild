"""Copy packaged playground templates to user projects."""

from __future__ import annotations

from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from sqlbuild.cli.commands.main.shared.exceptions import CliUserError

_TEMPLATE_PACKAGE: str = "sqlbuild.playground"
_WAFFLE_SHOP_TEMPLATE: str = "templates/waffle_shop"


def create_playground_project(*, target_dir: Path) -> None:
    """Create a DuckDB-backed waffle shop playground project."""

    if target_dir.exists():
        raise CliUserError(
            f"playground target already exists: {target_dir}",
            code="C701",
            help="choose a new directory or remove the existing one",
        )

    template_root: Traversable = files(_TEMPLATE_PACKAGE).joinpath(_WAFFLE_SHOP_TEMPLATE)
    if not template_root.is_dir():
        raise CliUserError(
            "packaged playground template is missing",
            code="C702",
            help="reinstall SQLBuild or report a packaging issue",
        )
    _copy_tree(source=template_root, target=target_dir)


def _copy_tree(*, source: Traversable, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    child: Traversable
    for child in source.iterdir():
        child_target: Path = target / _generated_name(child.name)
        if child.is_dir():
            _copy_tree(source=child, target=child_target)
            continue
        child_target.write_bytes(child.read_bytes())


def _generated_name(template_name: str) -> str:
    if template_name.endswith(".py.txt"):
        return template_name.removesuffix(".txt")
    return template_name
