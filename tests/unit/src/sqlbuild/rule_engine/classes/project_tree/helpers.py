from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.rule_engine.classes.project_tree import ProjectTree
from tests.unit.src.sqlbuild.rule_engine.main.evaluate.helpers import build_project

ORDERS_SQL: str = "SELECT 1 AS order_id\n"
LIMITS_YAML: str = "max_orders: 3\n"


def linked_project_tree(tmp_path: Path) -> ProjectTree:
    """Return a project tree with regular files and symlinks inside and outside the project."""

    root: Path = tmp_path / "orders"
    outside: Path = tmp_path / "outside"
    (root / "models").mkdir(parents=True)
    (root / "rules" / "inputs").mkdir(parents=True)
    outside.mkdir()
    (root / "models" / "orders.sql").write_text(ORDERS_SQL, encoding="utf-8")
    (root / "models" / "notes.txt").write_text("notes\n", encoding="utf-8")
    (root / "rules" / "inputs" / "limits.yaml").write_text(LIMITS_YAML, encoding="utf-8")
    (outside / "customers.sql").write_text("SELECT 1 AS customer_id\n", encoding="utf-8")
    (root / "models" / "orders_alias.sql").symlink_to(root / "models" / "orders.sql")
    (root / "models" / "customers.sql").symlink_to(outside / "customers.sql")
    (root / "linked_models").symlink_to(root / "models", target_is_directory=True)
    (root / "outside_models").symlink_to(outside, target_is_directory=True)
    project: CompiledProject = build_project(
        name="orders", relative_path="models/orders.sql", sql=ORDERS_SQL, config_values={}
    )
    return ProjectTree(project_dir=root, project=project)
