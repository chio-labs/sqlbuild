"""Helpers for source loader e2e tests."""

from __future__ import annotations


def build_schema_behavior_project_files(*, source_yaml: str, loader_py: str) -> dict[str, str]:
    return {
        "sqlbuild_project.toml": (
            'name = "source_loader_schema_behavior"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "source_loader_schema_behavior.duckdb"\n'
        ),
        "sources/raw.yml": source_yaml,
        "loaders/source_rows.py": loader_py,
    }


def build_loader_waffle_shop_project_files(*, project_toml: str | None = None) -> dict[str, str]:
    """Build a compact project that stresses chained source loaders and models."""

    return {
        "sqlbuild_project.toml": project_toml
        or (
            'name = "loader_waffle_shop"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "loader_waffle_shop.duckdb"\n\n'
            "[defaults]\n"
            'materialized = "table"\n'
        ),
        "sources/raw.yml": (
            "sources:\n"
            "  - name: raw_orders\n"
            "    loader: load_raw_orders\n"
            "    write_strategy: table\n"
            "    columns:\n"
            "      - name: order_id\n"
            "        type: INTEGER\n"
            "      - name: customer_id\n"
            "        type: INTEGER\n"
            "      - name: waffle_type\n"
            "        type: VARCHAR\n"
            "      - name: quantity\n"
            "        type: INTEGER\n"
            "      - name: price_cents\n"
            "        type: INTEGER\n"
            "      - name: load_seq\n"
            "        type: INTEGER\n"
            "  - name: raw_customers\n"
            "    loader: load_raw_customers\n"
            "    write_strategy: table\n"
            "    columns:\n"
            "      - name: customer_id\n"
            "        type: INTEGER\n"
            "      - name: plan_name\n"
            "        type: VARCHAR\n"
            "      - name: load_seq\n"
            "        type: INTEGER\n"
        ),
        "loaders/waffle_loaders.py": (
            "from sqlbuild.loaders import loader\n\n"
            "@loader(write_strategy='append', cursor_column='load_seq', columns=[\n"
            "    {'name': 'order_id', 'type': 'INTEGER'},\n"
            "    {'name': 'customer_id', 'type': 'INTEGER'},\n"
            "    {'name': 'waffle_type', 'type': 'VARCHAR'},\n"
            "    {'name': 'quantity', 'type': 'INTEGER'},\n"
            "    {'name': 'load_seq', 'type': 'INTEGER'},\n"
            "])\n"
            "def fetch_order_events(ctx):\n"
            "    if ctx.current_cursor_value is None:\n"
            "        next_seq = 1\n"
            "    else:\n"
            "        next_seq = ctx.current_cursor_value + 1\n"
            "    first_order = (next_seq - 1) * 2 + 1\n"
            "    return [\n"
            "        {\n"
            "            'order_id': first_order,\n"
            "            'customer_id': 1 if next_seq == 1 else 3,\n"
            "            'waffle_type': 'classic',\n"
            "            'quantity': next_seq,\n"
            "            'load_seq': next_seq,\n"
            "        },\n"
            "        {\n"
            "            'order_id': first_order + 1,\n"
            "            'customer_id': 2,\n"
            "            'waffle_type': 'blueberry',\n"
            "            'quantity': next_seq + 1,\n"
            "            'load_seq': next_seq,\n"
            "        },\n"
            "    ]\n\n"
            "@loader(\n"
            "    write_strategy='merge',\n"
            "    unique_key='customer_id',\n"
            "    cursor_column='load_seq',\n"
            "    columns=[\n"
            "    {'name': 'customer_id', 'type': 'INTEGER'},\n"
            "    {'name': 'plan_name', 'type': 'VARCHAR'},\n"
            "    {'name': 'load_seq', 'type': 'INTEGER'},\n"
            "])\n"
            "def fetch_customers(ctx):\n"
            "    if ctx.current_cursor_value is None:\n"
            "        return [\n"
            "            {'customer_id': 1, 'plan_name': 'basic', 'load_seq': 1},\n"
            "            {'customer_id': 2, 'plan_name': 'plus', 'load_seq': 1},\n"
            "        ]\n"
            "    return [\n"
            "        {'customer_id': 1, 'plan_name': 'pro', 'load_seq': 2},\n"
            "        {'customer_id': 3, 'plan_name': 'enterprise', 'load_seq': 2},\n"
            "    ]\n\n"
            "@loader(write_strategy='delete_insert', cursor_column='load_seq', columns=[\n"
            "    {'name': 'waffle_type', 'type': 'VARCHAR'},\n"
            "    {'name': 'price_cents', 'type': 'INTEGER'},\n"
            "    {'name': 'load_seq', 'type': 'INTEGER'},\n"
            "])\n"
            "def fetch_prices(ctx):\n"
            "    classic_price = 600 if ctx.current_cursor_value is None else 650\n"
            "    return [\n"
            "        {'waffle_type': 'classic', 'price_cents': classic_price, 'load_seq': 1},\n"
            "        {'waffle_type': 'blueberry', 'price_cents': 750, 'load_seq': 1},\n"
            "    ]\n\n"
            "@loader(depends_on=[fetch_order_events, fetch_prices])\n"
            "def load_raw_orders(ctx):\n"
            "    events = ctx.loader(fetch_order_events)\n"
            "    prices = ctx.loader(fetch_prices)\n"
            "    cursor = ctx.query(\n"
            "        f'SELECT e.order_id, e.customer_id, e.waffle_type, e.quantity, '\n"
            "        f'p.price_cents, e.load_seq FROM {events.target} e '\n"
            "        f'JOIN {prices.target} p ON e.waffle_type = p.waffle_type '\n"
            "        f'ORDER BY e.order_id'\n"
            "    )\n"
            "    return [\n"
            "        {\n"
            "            'order_id': row[0],\n"
            "            'customer_id': row[1],\n"
            "            'waffle_type': row[2],\n"
            "            'quantity': row[3],\n"
            "            'price_cents': row[4],\n"
            "            'load_seq': row[5],\n"
            "        }\n"
            "        for row in cursor.fetchall()\n"
            "    ]\n\n"
            "@loader(depends_on=[fetch_customers])\n"
            "def load_raw_customers(ctx):\n"
            "    customers = ctx.loader(fetch_customers)\n"
            "    cursor = ctx.query(\n"
            "        f'SELECT customer_id, plan_name, load_seq FROM {customers.target} '\n"
            "        f'ORDER BY customer_id'\n"
            "    )\n"
            "    return [\n"
            "        {'customer_id': row[0], 'plan_name': row[1], 'load_seq': row[2]}\n"
            "        for row in cursor.fetchall()\n"
            "    ]\n"
        ),
        "models/fact_waffle_orders.sql": (
            "MODEL (materialized table);\n\n"
            "SELECT\n"
            "  o.order_id,\n"
            "  o.customer_id,\n"
            "  c.plan_name,\n"
            "  o.waffle_type,\n"
            "  o.quantity,\n"
            "  o.price_cents,\n"
            "  o.quantity * o.price_cents AS revenue_cents,\n"
            "  o.load_seq\n"
            'FROM __source("raw_orders") o\n'
            'LEFT JOIN __source("raw_customers") c ON o.customer_id = c.customer_id\n'
        ),
        "models/customer_revenue.sql": (
            "MODEL (materialized table);\n\n"
            "SELECT\n"
            "  customer_id,\n"
            "  COALESCE(plan_name, 'unknown') AS plan_name,\n"
            "  SUM(revenue_cents) AS revenue_cents,\n"
            "  COUNT(*) AS order_count\n"
            'FROM __ref("fact_waffle_orders")\n'
            "GROUP BY customer_id, COALESCE(plan_name, 'unknown')\n"
        ),
    }
