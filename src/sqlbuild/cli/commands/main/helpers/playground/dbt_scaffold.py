"""Scaffold steps for the dbt reuse playground template."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from sqlbuild.cli.commands.main.shared.exceptions import CliUserError

_DEV_MODEL_EDITS: tuple[tuple[str, str], ...] = (
    (
        "models/marts/agg_daily_revenue.sql",
        "with orders as (\n"
        "    select * from {{ ref('fct_orders') }}\n"
        ")\n\n"
        "select\n"
        "    order_date,\n"
        "    count(*) as order_count,\n"
        "    sum(order_amount_cents) as revenue_cents,\n"
        "    sum(order_amount_cents) / 100.0 as revenue_usd,\n"
        "    avg(order_amount_cents) / 100.0 as avg_order_usd\n"
        "from orders\n"
        "where is_completed\n"
        "group by 1\n"
        "order by 1\n",
    ),
    (
        "models/marts/dim_customers.sql",
        "with customers as (\n"
        "    select * from {{ ref('stg_customers') }}\n"
        "),\n\n"
        "customer_orders as (\n"
        "    select * from {{ ref('int_customer_orders') }}\n"
        ")\n\n"
        "select\n"
        "    customers.customer_id,\n"
        "    customers.full_name,\n"
        "    customers.signup_date,\n"
        "    coalesce(customer_orders.order_count, 0) as order_count,\n"
        "    coalesce(customer_orders.lifetime_amount_cents, 0) as lifetime_amount_cents,\n"
        "    coalesce(customer_orders.lifetime_amount_cents, 0) / 100.0 as lifetime_amount_usd,\n"
        "    customer_orders.first_order_date,\n"
        "    customer_orders.most_recent_order_date\n"
        "from customers\n"
        "left join customer_orders on customer_orders.customer_id = customers.customer_id\n",
    ),
)


def scaffold_dbt_reuse_playground(*, target_dir: Path) -> None:
    """Initialize git, build the prod schema, and create a dev branch with edits."""

    _require_executable(name="git")
    _require_executable(name="dbt")
    dbt_project_dir: Path = target_dir / "dbt_project"
    profiles_dir: Path = target_dir / "profiles"
    _write_gitignore(target_dir=target_dir)
    _run_git(args=("init", "--initial-branch=main"), cwd=target_dir)
    _run_git(args=("config", "user.email", "playground@sqlbuild.invalid"), cwd=target_dir)
    _run_git(args=("config", "user.name", "SQLBuild Playground"), cwd=target_dir)
    _run_git(args=("add", "."), cwd=target_dir)
    _run_git(args=("commit", "-m", "dbt reuse playground baseline"), cwd=target_dir)
    _build_prod(dbt_project_dir=dbt_project_dir, profiles_dir=profiles_dir)
    _run_git(args=("checkout", "-b", "dev"), cwd=target_dir)
    _apply_dev_edits(dbt_project_dir=dbt_project_dir)


def _build_prod(*, dbt_project_dir: Path, profiles_dir: Path) -> None:
    _run_dbt(
        args=("seed",),
        dbt_project_dir=dbt_project_dir,
        profiles_dir=profiles_dir,
        target="prod",
    )
    _run_dbt(
        args=("run",),
        dbt_project_dir=dbt_project_dir,
        profiles_dir=profiles_dir,
        target="prod",
    )


def _apply_dev_edits(*, dbt_project_dir: Path) -> None:
    relative_path: str
    contents: str
    for relative_path, contents in _DEV_MODEL_EDITS:
        (dbt_project_dir / relative_path).write_text(contents, encoding="utf-8")


def _write_gitignore(*, target_dir: Path) -> None:
    (target_dir / ".gitignore").write_text(
        "warehouse.duckdb\ndbt_project/target/\ndbt_project/dbt_packages/\nlogs/\n",
        encoding="utf-8",
    )


def _require_executable(*, name: str) -> None:
    if shutil.which(name) is not None:
        return
    raise CliUserError(
        f"the dbt reuse playground requires '{name}' on PATH",
        code="C704",
        help=f"install {name} and re-run sqb playground --template dbt",
    )


def _run_git(*, args: tuple[str, ...], cwd: Path) -> None:
    result: subprocess.CompletedProcess[str] = subprocess.run(
        ("git", *args),
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise CliUserError(
            f"dbt reuse playground git step failed: git {' '.join(args)}",
            code="C705",
            help=(result.stderr or result.stdout).strip() or None,
        )


def _run_dbt(
    *, args: tuple[str, ...], dbt_project_dir: Path, profiles_dir: Path, target: str
) -> None:
    result: subprocess.CompletedProcess[str] = subprocess.run(
        (
            "dbt",
            *args,
            "--project-dir",
            dbt_project_dir.as_posix(),
            "--profiles-dir",
            profiles_dir.as_posix(),
            "--target",
            target,
        ),
        cwd=dbt_project_dir,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise CliUserError(
            f"dbt reuse playground prod build failed: dbt {' '.join(args)}",
            code="C706",
            help=(result.stderr or result.stdout).strip() or None,
        )
