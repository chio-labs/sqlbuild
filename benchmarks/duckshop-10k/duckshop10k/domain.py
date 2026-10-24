"""Domain-specific intermediate models that do not fit the generic templates."""

from __future__ import annotations

from duckshop10k.core import Column, Model, Project, cte, import_cte, select_list
from duckshop10k.staging import with_query


def customer_profile(
    project: Project,
    name: str,
    folder: str,
    customers: Model,
    addresses: Model,
    consents: Model,
    store: str,
) -> Model:
    ctes = [
        import_cte("customers", f'__ref("{customers.name}")'),
        import_cte("addresses", f'__ref("{addresses.name}")'),
        import_cte("consents", f'__ref("{consents.name}")'),
        cte(
            "default_addresses",
            "SELECT\n  a.customer_id,\n  a.city,\n  a.postcode,\n  a.country_code\n"
            "FROM addresses AS a\nWHERE\n  a.is_default\n"
            "QUALIFY ROW_NUMBER() OVER (\n  PARTITION BY a.customer_id\n"
            "  ORDER BY a.valid_from_at_utc DESC, a.address_id\n) = 1",
        ),
        cte(
            "consent_lists",
            "SELECT\n  c.customer_id,\n"
            "  ARRAY_AGG(DISTINCT c.consent_type) WITHIN GROUP (ORDER BY c.consent_type)"
            " AS consent_types\nFROM consents AS c\nWHERE\n  c.consent_type IS NOT NULL\n"
            "GROUP BY\n  c.customer_id",
        ),
        cte(
            "final",
            "SELECT\n"
            + select_list(
                [
                    "c.customer_id",
                    f"c.{store}",
                    "c.region_code",
                    "c.email",
                    "c.phone",
                    "c.full_name",
                    "c.created_at_utc",
                    "c.loyalty_tier",
                    "c.is_marketing_opt_in",
                    "COALESCE(d.country_code, c.country_code)::VARCHAR AS country_code",
                    "d.city::VARCHAR AS default_city",
                    "d.postcode::VARCHAR AS default_postcode",
                    "COALESCE(l.consent_types, ARRAY_CONSTRUCT())::ARRAY AS consent_types",
                    "ARRAY_CONTAINS('MARKETING'::VARIANT, COALESCE(l.consent_types,"
                    " ARRAY_CONSTRUCT()))"
                    "::BOOLEAN AS has_marketing_consent",
                ]
            )
            + "\nFROM customers AS c\nLEFT JOIN default_addresses AS d\n"
            "  ON c.customer_id = d.customer_id\nLEFT JOIN consent_lists AS l\n"
            "  ON c.customer_id = l.customer_id",
        ),
    ]
    columns = [
        Column("customer_id", "VARCHAR", ("not_null", "unique"), nullable=False),
        Column(store, "VARCHAR"),
        Column("region_code", "VARCHAR"),
        Column("email", "VARCHAR"),
        Column("phone", "VARCHAR"),
        Column("full_name", "VARCHAR"),
        Column("created_at_utc", "TIMESTAMP_NTZ"),
        Column("loyalty_tier", "VARCHAR"),
        Column("is_marketing_opt_in", "BOOLEAN"),
        Column("country_code", "VARCHAR"),
        Column("default_city", "VARCHAR"),
        Column("default_postcode", "VARCHAR"),
        Column("consent_types", "ARRAY"),
        Column("has_marketing_consent", "BOOLEAN"),
    ]
    return project.add(
        Model(
            name=name,
            folder=folder,
            layer="intermediate",
            description=(
                "One row per customer with their current default address and the consents they "
                "have granted"
            ),
            columns=columns,
            body=with_query(ctes),
            refs=[customers.name, addresses.name, consents.name],
        )
    )


def cart_funnel(project: Project, name: str, folder: str, carts_stg: Model, carts: Model) -> Model:
    ctes = [
        import_cte("staged_carts", f'__ref("{carts_stg.name}")'),
        import_cte("carts", f'__ref("{carts.name}")'),
        cte(
            "item_lists",
            "SELECT\n  s.cart_id,\n"
            "  FILTER(s.items, i -> COALESCE(i:quantity::INT, 0) > 0) AS live_items\n"
            "FROM staged_carts AS s",
        ),
        cte(
            "final",
            "SELECT\n"
            + select_list(
                [
                    "c.cart_id",
                    "c.customer_id",
                    "c.anonymous_id",
                    "c.opened_at_utc",
                    "c.last_activity_at_utc",
                    "ARRAY_SIZE(l.live_items)::INT AS live_item_count",
                    "REDUCE(\n    TRANSFORM(l.live_items, i -> COALESCE(i:quantity::INT, 1)),\n"
                    "    0,\n    (acc, q) -> acc + q\n  )::INT AS unit_count",
                    "ARRAY_DISTINCT(TRANSFORM(l.live_items, i -> UPPER(i:sku::VARCHAR)))::ARRAY"
                    " AS distinct_skus",
                    "DATEDIFF('minute', c.opened_at_utc, c.last_activity_at_utc)::INT"
                    " AS active_minutes",
                    "(ARRAY_SIZE(l.live_items) > 0 AND c.customer_id IS NULL)::BOOLEAN"
                    " AS is_anonymous_with_items",
                ]
            )
            + "\nFROM carts AS c\nINNER JOIN item_lists AS l\n  ON c.cart_id = l.cart_id",
        ),
    ]
    columns = [
        Column("cart_id", "VARCHAR", ("not_null", "unique"), nullable=False),
        Column("customer_id", "VARCHAR"),
        Column("anonymous_id", "VARCHAR"),
        Column("opened_at_utc", "TIMESTAMP_NTZ"),
        Column("last_activity_at_utc", "TIMESTAMP_NTZ"),
        Column("live_item_count", "INT"),
        Column("unit_count", "INT"),
        Column("distinct_skus", "ARRAY"),
        Column("active_minutes", "INT"),
        Column("is_anonymous_with_items", "BOOLEAN"),
    ]
    return project.add(
        Model(
            name=name,
            folder=folder,
            layer="intermediate",
            description=(
                "One row per cart with its live items, unit count and distinct SKUs, computed with "
                "array lambdas over the cart payload"
            ),
            columns=columns,
            body=with_query(ctes),
            refs=[carts_stg.name, carts.name],
        )
    )


def stock_ledger(
    project: Project,
    name: str,
    folder: str,
    movements: Model,
    adjustments: Model,
    receipts: Model,
    picks: Model,
    warehouse_column: str,
) -> Model:
    parts = [
        ("movements", movements, "movement_id", "qty_delta", "moved_at_utc", "'movement'"),
        (
            "adjustments",
            adjustments,
            "adjustment_id",
            "qty_delta",
            "adjusted_at_utc",
            "'adjustment'",
        ),
        ("receipts", receipts, "receipt_id", "quantity", "received_at_utc", "'receipt'"),
        ("picks", picks, "pick_id", "-quantity", "picked_at_utc", "'pick'"),
    ]
    ctes = [import_cte(alias, f'__ref("{model.name}")') for alias, model, *_ in parts]
    branches = []
    for alias, _model, key, quantity, moment, kind in parts:
        signed = f"(-r.{quantity[1:]})::INT" if quantity.startswith("-") else f"r.{quantity}::INT"
        branches.append(
            "SELECT\n"
            + select_list(
                [
                    f"({kind} || ':' || r.{key})::VARCHAR AS movement_key",
                    "r.sku",
                    f"r.{moment}::TIMESTAMP_NTZ AS moved_at_utc",
                    f"{signed} AS qty_delta",
                    f"{kind}::VARCHAR AS movement_type",
                ]
            )
            + f"\nFROM {alias} AS r"
        )
    ctes.append(cte("ledger_rows", "\nUNION ALL\n".join(branches)))
    ctes.append(
        cte(
            "final",
            "SELECT\n"
            + select_list(
                [
                    "l.movement_key",
                    "l.sku",
                    "l.moved_at_utc",
                    "l.qty_delta",
                    "l.movement_type",
                    "SUM(l.qty_delta) OVER (\n    PARTITION BY l.sku\n"
                    "    ORDER BY l.moved_at_utc, l.movement_key\n"
                    "    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW\n  )::INT AS"
                    " on_hand_after",
                    "(SUM(l.qty_delta) OVER (\n    PARTITION BY l.sku\n"
                    "    ORDER BY l.moved_at_utc, l.movement_key\n"
                    "    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW\n  ) < 0)::BOOLEAN"
                    " AS is_negative_stock",
                ]
            )
            + "\nFROM ledger_rows AS l\nWHERE\n  l.sku IS NOT NULL",
        )
    )
    columns = [
        Column("movement_key", "VARCHAR", ("not_null", "unique"), nullable=False),
        Column("sku", "VARCHAR", ("not_null",)),
        Column("moved_at_utc", "TIMESTAMP_NTZ"),
        Column("qty_delta", "INT"),
        Column("movement_type", "VARCHAR"),
        Column("on_hand_after", "INT"),
        Column("is_negative_stock", "BOOLEAN"),
    ]
    return project.add(
        Model(
            name=name,
            folder=folder,
            layer="intermediate",
            description=(
                "Signed stock ledger of movements, adjustments, receipts and picks per"
                " SKU, with the "
                "running quantity on hand after each entry"
            ),
            columns=columns,
            body=with_query(ctes),
            refs=[model.name for _alias, model, *_ in parts],
        )
    )


def sessions(project: Project, name: str, folder: str, events: Model) -> Model:
    config = [
        "constants (\n    _read_margin_hours 24,\n  )",
        "materialized incremental",
        "incremental_strategy delete_insert",
        "incremental_mode microbatch",
        "microbatch_strategy watermark",
        "cursor_watermark_mode all",
        "cursor session_day",
        "cursor_type timestamp",
        "cursor_grain day",
        "batch_size 1d",
        "lookback 3d",
        "replay_on_change full",
        f"cursor_inputs (\n    {events.name} (column received_at, roles [watermark]),\n  )",
    ]
    ctes = [
        import_cte("events", f'__ref("{events.name}")'),
        cte(
            "human_events",
            "SELECT\n"
            + select_list(
                [
                    "e.event_id",
                    "e.anonymous_id",
                    "e.customer_id",
                    "e.storefront_code",
                    "e.event_type",
                    "e.event_at_utc",
                    "e.page_path",
                    "e.referrer_host",
                    "e.client_timezone",
                ]
            )
            + "\nFROM events AS e\nWHERE\n"
            "  e.event_at_utc >= DATEADD('hour', -@const(\"_read_margin_hours\"), "
            "__cursor_start())\n"
            "  AND e.event_at_utc < DATEADD('hour', @const(\"_read_margin_hours\"), "
            "__cursor_end())\n"
            "  AND NOT e.is_bot\n  AND e.anonymous_id IS NOT NULL",
        ),
        cte(
            "gaps",
            "SELECT\n"
            + select_list(
                [
                    "h.event_id",
                    "h.anonymous_id",
                    "h.customer_id",
                    "h.storefront_code",
                    "h.event_type",
                    "h.event_at_utc",
                    "h.page_path",
                    "h.referrer_host",
                    "h.client_timezone",
                    "IFF(DATEDIFF(\n    'minute',\n    LAG(h.event_at_utc) OVER (PARTITION BY "
                    "h.anonymous_id ORDER BY h.event_at_utc, h.event_id),\n    h.event_at_utc\n"
                    '  ) <= @const("session_gap_minutes"), 0, 1) AS is_session_start',
                ]
            )
            + "\nFROM human_events AS h",
        ),
        cte(
            "numbered",
            "SELECT\n"
            + select_list(
                [
                    "g.anonymous_id",
                    "g.customer_id",
                    "g.storefront_code",
                    "g.event_type",
                    "g.event_at_utc",
                    "g.page_path",
                    "g.referrer_host",
                    "g.client_timezone",
                    "SUM(g.is_session_start) OVER (\n    PARTITION BY g.anonymous_id\n"
                    "    ORDER BY g.event_at_utc, g.event_id\n"
                    "    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW\n  ) AS session_number",
                ]
            )
            + "\nFROM gaps AS g",
        ),
        cte(
            "grouped",
            "SELECT\n"
            + select_list(
                [
                    "n.anonymous_id",
                    "MAX(n.customer_id) AS customer_id",
                    "MIN_BY(n.storefront_code, n.event_at_utc) AS storefront_code",
                    "MIN(n.event_at_utc) AS session_start_utc",
                    "MAX(n.event_at_utc) AS session_end_utc",
                    "COUNT(*) AS event_count",
                    "COUNT_IF(n.event_type = 'page_view') AS page_view_count",
                    "MIN_BY(n.page_path, n.event_at_utc) AS landing_page_path",
                    "MIN_BY(n.referrer_host, n.event_at_utc) AS referrer_host",
                    "MIN_BY(n.client_timezone, n.event_at_utc) AS client_timezone",
                    "BOOLOR_AGG(n.event_type = 'add_to_cart') AS has_add_to_cart",
                    "BOOLOR_AGG(n.event_type = 'checkout_complete') AS has_order",
                ]
            )
            + "\nFROM numbered AS n\nGROUP BY\n  n.anonymous_id,\n  n.session_number",
        ),
        cte(
            "final",
            "SELECT\n"
            + select_list(
                [
                    "(\n    s.anonymous_id || ':' || TO_CHAR(s.session_start_utc,"
                    " 'YYYYMMDDHH24MISS')"
                    "\n  )::VARCHAR AS session_id",
                    "s.anonymous_id",
                    "s.customer_id::VARCHAR AS customer_id",
                    "s.storefront_code::VARCHAR AS storefront_code",
                    "DATE_TRUNC('day', s.session_start_utc)::TIMESTAMP_NTZ AS session_day",
                    "s.session_start_utc::DATE AS session_date",
                    "s.session_start_utc",
                    "s.session_end_utc",
                    "CONVERT_TIMEZONE(\n    'UTC',\n    COALESCE(s.client_timezone, 'UTC'),\n"
                    "    s.session_start_utc\n  )::TIMESTAMP_NTZ AS session_start_visitor_local",
                    "DATEDIFF('second', s.session_start_utc, s.session_end_utc)::INT"
                    " AS duration_seconds",
                    "s.event_count::INT AS event_count",
                    "s.page_view_count::INT AS page_view_count",
                    "s.landing_page_path::VARCHAR AS landing_page_path",
                    "s.referrer_host::VARCHAR AS referrer_host",
                    "(s.page_view_count <= 1 AND s.event_count <= 1)::BOOLEAN AS is_bounce",
                    "s.has_add_to_cart::BOOLEAN AS has_add_to_cart",
                    "s.has_order::BOOLEAN AS has_order",
                ]
            )
            + "\nFROM grouped AS s\nWHERE\n  s.session_start_utc >= __cursor_start()\n"
            "  AND s.session_start_utc < __cursor_end()",
        ),
    ]
    columns = [
        Column("session_id", "VARCHAR", ("not_null", "unique"), nullable=False),
        Column("anonymous_id", "VARCHAR", ("not_null",)),
        Column("customer_id", "VARCHAR"),
        Column("storefront_code", "VARCHAR"),
        Column("session_day", "TIMESTAMP_NTZ", ("not_null",)),
        Column("session_date", "DATE"),
        Column("session_start_utc", "TIMESTAMP_NTZ"),
        Column("session_end_utc", "TIMESTAMP_NTZ"),
        Column("session_start_visitor_local", "TIMESTAMP_NTZ"),
        Column("duration_seconds", "INT"),
        Column("event_count", "INT"),
        Column("page_view_count", "INT"),
        Column("landing_page_path", "VARCHAR"),
        Column("referrer_host", "VARCHAR"),
        Column("is_bounce", "BOOLEAN"),
        Column("has_add_to_cart", "BOOLEAN"),
        Column("has_order", "BOOLEAN"),
    ]
    return project.add(
        Model(
            name=name,
            folder=folder,
            layer="intermediate",
            description=(
                "One row per visitor session, split wherever 30 minutes pass without activity and "
                "built in daily microbatches. Each batch keeps the sessions that start inside it, "
                "reading a day of events either side so sessions crossing batch edges are whole."
            ),
            config=config,
            columns=columns,
            body=with_query(ctes),
            refs=[events.name],
        )
    )


def ageing(
    project: Project,
    name: str,
    folder: str,
    invoices: Model,
    key: str,
    counterparty: str,
    amount: str,
    entity_column: str,
    description: str,
) -> Model:
    buckets = (
        "CASE\n    WHEN i.days_overdue <= 0 THEN 'current'\n"
        "    WHEN i.days_overdue <= 30 THEN '1_30'\n"
        "    WHEN i.days_overdue <= 60 THEN '31_60'\n"
        "    WHEN i.days_overdue <= 90 THEN '61_90'\n"
        "    ELSE 'over_90'\n  END::VARCHAR AS ageing_bucket"
    )
    ctes = [
        import_cte("invoices_in", f'__ref("{invoices.name}")'),
        cte(
            "open_invoices",
            "SELECT\n"
            + select_list(
                [
                    f"v.{key}",
                    f"v.{counterparty}",
                    f"v.{entity_column}",
                    "v.currency_code",
                    f"v.{amount}",
                    "v.due_date",
                    "DATEDIFF('day', v.due_date, '@@valuation_date'::DATE)::INT AS days_overdue",
                ]
            )
            + "\nFROM invoices_in AS v\nWHERE\n  v.status <> 'PAID'",
        ),
        cte(
            "final",
            "SELECT\n"
            + select_list(
                [
                    f"i.{key}",
                    f"i.{counterparty}",
                    f"i.{entity_column}",
                    "i.currency_code",
                    f"i.{amount}",
                    "i.due_date",
                    "i.days_overdue",
                    buckets,
                    f"SUM(i.{amount}) OVER (PARTITION BY i.{counterparty})::NUMBER(18, 2)"
                    " AS counterparty_open_amount",
                ]
            )
            + "\nFROM open_invoices AS i",
        ),
    ]
    columns = [
        Column(key, "VARCHAR", ("not_null", "unique"), nullable=False),
        Column(counterparty, "VARCHAR"),
        Column(entity_column, "VARCHAR"),
        Column("currency_code", "VARCHAR"),
        Column(amount, "NUMBER(18, 2)"),
        Column("due_date", "DATE"),
        Column("days_overdue", "INT"),
        Column(
            "ageing_bucket",
            "VARCHAR",
            ("accepted_values (values ['current', '1_30', '31_60', '61_90', 'over_90'])",),
        ),
        Column("counterparty_open_amount", "NUMBER(18, 2)"),
    ]
    return project.add(
        Model(
            name=name,
            folder=folder,
            layer="intermediate",
            description=description,
            columns=columns,
            body=with_query(ctes),
            refs=[invoices.name],
        )
    )


def customer_identity(project: Project, name: str, folder: str, customers: Model) -> Model:
    ctes = [
        import_cte("customers", f'__ref("{customers.name}")'),
        cte(
            "keyed",
            "SELECT\n"
            + select_list(
                [
                    "c.customer_id",
                    "c.storefront_code",
                    "c.created_at_utc",
                    "COALESCE(c.email, c.phone, c.customer_id) AS identity_basis",
                ]
            )
            + "\nFROM customers AS c",
        ),
        cte(
            "final",
            "SELECT\n"
            + select_list(
                [
                    "(k.storefront_code || ':' || k.customer_id)::VARCHAR AS"
                    " storefront_customer_key",
                    "k.customer_id",
                    "k.storefront_code",
                    "HASH(k.identity_basis)::NUMBER(38, 0) AS identity_hash",
                    "FIRST_VALUE(k.storefront_code || ':' || k.customer_id) OVER (\n"
                    "    PARTITION BY k.identity_basis\n    ORDER BY k.created_at_utc,"
                    " k.storefront_code, k.customer_id\n"
                    "  )::VARCHAR AS global_customer_key",
                    "COUNT(*) OVER (PARTITION BY k.identity_basis)::INT AS linked_account_count",
                ]
            )
            + "\nFROM keyed AS k",
        ),
    ]
    columns = [
        Column("storefront_customer_key", "VARCHAR", ("not_null", "unique"), nullable=False),
        Column("customer_id", "VARCHAR"),
        Column("storefront_code", "VARCHAR"),
        Column("identity_hash", "NUMBER(38, 0)"),
        Column("global_customer_key", "VARCHAR", ("not_null",)),
        Column("linked_account_count", "INT"),
    ]
    return project.add(
        Model(
            name=name,
            folder=folder,
            layer="intermediate",
            description=(
                "One row per storefront account linked to a global customer by email or phone. The "
                "identity hash uses HASH, whose output is engine-specific, so it is an expected "
                "divergence across engines."
            ),
            tags=["known_divergence"],
            columns=columns,
            body=with_query(ctes),
            refs=[customers.name],
        )
    )


def first_response(
    project: Project,
    name: str,
    folder: str,
    tickets: Model,
    comments: Model,
    local_time: bool,
) -> Model:
    created = "t.created_at_utc"
    response = "MIN(IFF(c.author_type = 'AGENT', c.written_at_utc, NULL))"
    items = [
        "t.ticket_id",
        "t.priority",
        "t.contact_channel",
        created,
        f"{response} AS first_response_at_utc",
        f"DATEDIFF('minute', {created}, {response})::INT AS minutes_to_first_response",
    ]
    columns = [
        Column("ticket_id", "VARCHAR", ("not_null", "unique"), nullable=False),
        Column("priority", "INT"),
        Column("contact_channel", "VARCHAR"),
        Column("created_at_utc", "TIMESTAMP_NTZ"),
        Column("first_response_at_utc", "TIMESTAMP_NTZ"),
        Column("minutes_to_first_response", "INT"),
    ]
    description = "One row per ticket with the time to the first agent response"
    tags: list[str] = []
    if local_time:
        items.append(f"{created}::TIMESTAMP_LTZ AS created_at_session_local")
        columns.append(Column("created_at_session_local", "TIMESTAMP_LTZ"))
        description += (
            ". The creation time is also shown as TIMESTAMP_LTZ, which depends on the session time "
            "zone, so it is an expected divergence across engines"
        )
        tags = ["known_divergence"]
    ctes = [
        import_cte("tickets", f'__ref("{tickets.name}")'),
        import_cte("comments", f'__ref("{comments.name}")'),
        cte(
            "final",
            f"SELECT\n{select_list(items)}\nFROM tickets AS t\nLEFT JOIN comments AS c\n"
            "  ON t.ticket_id = c.ticket_id\nGROUP BY\n  t.ticket_id,\n  t.priority,\n"
            "  t.contact_channel,\n  t.created_at_utc",
        ),
    ]
    return project.add(
        Model(
            name=name,
            folder=folder,
            layer="intermediate",
            description=description,
            tags=tags,
            columns=columns,
            body=with_query(ctes),
            refs=[tickets.name, comments.name],
        )
    )
