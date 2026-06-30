from __future__ import annotations

from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_repo_files,
)


def build_virtual_seed_reconcile_repo_files() -> dict[str, str]:
    return build_virtual_plan_repo_files(
        stg_orders_sql='SELECT id, amount_cents FROM __seed("order_amounts")'
    ) | {
        "seeds/orders.yml": (
            "seeds:\n"
            "  - name: order_amounts\n"
            "    path: order_amounts.csv\n"
            "    columns:\n"
            "      - name: id\n"
            "        type: integer\n"
            "      - name: amount_cents\n"
            "        type: integer\n"
        ),
        "seeds/order_amounts.csv": "id,amount_cents\n1,100\n",
    }
