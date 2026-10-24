"""The intermediate layer: conformed per-instance models, enrichment, unions and domain logic."""

from __future__ import annotations

from duckshop10k.core import Column, Model, Project, cte, import_cte, select_list
from duckshop10k.specs import Field, staging_name, staging_type
from duckshop10k.staging import StagedTable, with_query
from duckshop10k.world import CURRENCY_EXPONENT, Instance

CLASSIC_STATUS = (
    (10, "PENDING"),
    (20, "PAID"),
    (30, "PACKED"),
    (40, "SHIPPED"),
    (50, "DELIVERED"),
    (80, "RETURNED"),
    (90, "CANCELLED"),
)

INSTANCE_COLUMN = {
    "storefront": "storefront_code",
    "marketplace": "marketplace_code",
    "carrier": "carrier_code",
    "warehouse": "warehouse_code",
    "store": "store_code",
    "supplier": "supplier_code",
    "gateway": "gateway_code",
    "ad_network": "ad_network_code",
    "messaging": "messaging_channel_code",
    "affiliate": "affiliate_network_code",
    "collector": "collector_code",
    "support": "support_tool_code",
    "ledger": "legal_entity_code",
    "wholesale": "wholesale_desk_code",
    "returns": "returns_portal_code",
    "catalogue": "catalogue_code",
}


def instance_column(instance: Instance) -> str:
    return INSTANCE_COLUMN[instance.system]


def canonical_name(item: Field) -> str:
    if item.role == "ts":
        return f"{item.stem}_at_utc"
    if item.role == "amount":
        return f"{item.stem}_amount"
    if item.role == "status":
        return "status"
    if item.role == "array":
        return f"{item.stem}_count"
    return staging_name(item, "nest")


def canonical_type(item: Field) -> str:
    if item.role == "ts":
        return "TIMESTAMP_NTZ"
    if item.role == "amount":
        return "NUMBER(18, 2)"
    if item.role == "status":
        return "VARCHAR"
    if item.role == "array":
        return "INT"
    return staging_type(item, "nest")


def _utc_expression(item: Field, platform: str, timezone: str, alias: str) -> str:
    column = f"{alias}.{staging_name(item, platform)}"
    if staging_type(item, platform) == "TIMESTAMP_TZ":
        return f"@sql.tz_to_utc({column})"
    if platform == "classic" and not item.in_payload:
        return f"@sql.local_to_utc({column}, {timezone})"
    return f"{column}::TIMESTAMP_NTZ"


def _status_expression(platform: str, alias: str, orders: bool) -> str:
    if platform != "classic":
        return f"UPPER({alias}.status)::VARCHAR"
    if orders:
        whens = "\n".join(
            f'  WHEN {code} THEN @enum("order_status").{name}' for code, name in CLASSIC_STATUS
        )
    else:
        whens = "\n".join(f"  WHEN {code} THEN '{name}'" for code, name in CLASSIC_STATUS)
    return f"CASE {alias}.status_code\n{whens}\n  ELSE 'UNKNOWN'\nEND::VARCHAR"


def conform(project: Project, staged: StagedTable, folder: str) -> Model:
    """Instance-specific units and layouts converted to the shared canonical shape."""
    instance, archetype = staged.instance, staged.archetype
    platform = instance.platform
    stg = project.ref(staged.stg)
    amounts = [item for item in archetype.fields if item.role == "amount"]
    currency = next((item for item in archetype.fields if item.role == "currency"), None)
    times = [item for item in archetype.fields if item.role == "ts"]
    normalised: list[str] = [f"s.{archetype.key}"]
    final: list[str] = [f"n.{archetype.key}::VARCHAR AS {archetype.key}"]
    columns = [Column(archetype.key, "VARCHAR", ("not_null", "unique"), nullable=False)]
    code_column = instance_column(instance)
    normalised.extend(["s.instance_code", "i.region_code"])
    if times:
        normalised.append("i.timezone")
    final.append(f"n.instance_code AS {code_column}")
    final.append("n.region_code")
    columns.extend([Column(code_column, "VARCHAR"), Column("region_code", "VARCHAR")])
    needs_currency_join = bool(amounts) and currency is not None and platform != "classic"
    for item in archetype.fields:
        name = canonical_name(item)
        if item.role == "ts":
            normalised.append(f"{_utc_expression(item, platform, 'i.timezone', 's')} AS {name}")
            final.append(f"n.{name}")
        elif item.role == "amount":
            staged_name = staging_name(item, platform)
            if staged_name.endswith("_minor"):
                exponent = (
                    "cur.minor_unit_exponent"
                    if needs_currency_join
                    else str(CURRENCY_EXPONENT[instance.currency])
                )
                normalised.append(
                    f"@sql.money_from_minor(s.{staged_name}, {exponent})::NUMBER(18, 2) AS {name}"
                )
            else:
                normalised.append(f"s.{staged_name}::NUMBER(18, 2) AS {name}")
            final.append(f"n.{name}")
        elif item.role == "status":
            orders = instance.system == "storefront" and archetype.table == "orders"
            normalised.append(f"{_status_expression(platform, 's', orders)} AS {name}")
            final.append(f"n.{name}")
        elif item.role == "array":
            normalised.append(f"ARRAY_SIZE(s.{staging_name(item, platform)})::INT AS {name}")
            final.append(f"n.{name}")
        else:
            normalised.append(f"s.{staging_name(item, platform)}")
            final.append(f"n.{staging_name(item, platform)}")
        audits: tuple[str, ...] = ()
        if item.role == "amount":
            audits = ()
        columns.append(Column(name, canonical_type(item), audits))
    if times:
        first = canonical_name(times[0])
        local = f"{times[0].stem}_date_local"
        final.append(f"@sql.local_business_date(n.{first}, n.timezone) AS {local}")
        columns.append(Column(local, "DATE"))
    normalised.append("s.source_loaded_at")
    final.append("n.source_loaded_at")
    columns.append(Column("source_loaded_at", "TIMESTAMP_NTZ"))
    ctes = [
        import_cte("staged", f'__ref("{stg.name}")'),
        import_cte("instances", '__seed("source_instances")'),
        cte(
            "tagged",
            f"SELECT\n  s.*,\n  '{instance.code.upper()}'::VARCHAR AS instance_code\n"
            "FROM staged AS s",
        ),
    ]
    joins = "\nINNER JOIN instances AS i\n  ON s.instance_code = i.instance_code"
    if needs_currency_join:
        ctes.append(import_cte("currencies", '__seed("currencies")'))
        joins += (
            "\nLEFT JOIN currencies AS cur\n"
            f"  ON s.{staging_name(currency, platform)} = cur.currency_code"
        )
    ctes.append(cte("normalised", f"SELECT\n{select_list(normalised)}\nFROM tagged AS s{joins}"))
    ctes.append(cte("final", f"SELECT\n{select_list(final)}\nFROM normalised AS n"))
    return project.add(
        Model(
            name=f"int_{instance.code}__{archetype.table}",
            folder=folder,
            layer="intermediate",
            description=(
                f"{archetype.description.capitalize()} from {instance.label} in the shared shape: "
                "UTC times, amounts in major units, mapped statuses and the local business date"
            ),
            columns=columns,
            body=with_query(ctes),
            refs=[stg.name],
        )
    )


# --- Generic templates over conformed models --------------------------------------------------


def _numeric(model: Model) -> list[Column]:
    return [
        column
        for column in model.columns
        if column.type.startswith(("NUMBER(18, 2)", "INT"))
        and not column.name.endswith(("_number", "_index", "_seq"))
    ]


def enrich(
    project: Project,
    name: str,
    folder: str,
    header: Model,
    key: str,
    children: list[Model],
    description: str,
) -> Model:
    """A header model joined to an aggregate of each child model that carries its key."""
    ctes = [import_cte("header", f'__ref("{header.name}")')]
    items = [f"h.{column.name}" for column in header.columns]
    columns = [
        Column(c.name, c.type, ("not_null", "unique") if c.name == key else (), c.name != key)
        for c in header.columns
    ]
    joins: list[str] = []
    for index, child in enumerate(children, start=1):
        alias = f"c{index}"
        table = child.name.split("__", 1)[1]
        ctes.append(import_cte(f"{table}_rows", f'__ref("{child.name}")'))
        measures = [column for column in _numeric(child) if column.name != key][:3]
        aggregates = [f"r.{key}", f"COUNT(*) AS {table}_count"]
        aggregates.extend(f"SUM(r.{column.name}) AS {table}_{column.name}" for column in measures)
        ctes.append(
            cte(
                f"{table}_totals",
                f"SELECT\n{select_list(aggregates)}\nFROM {table}_rows AS r\nGROUP BY\n  r.{key}",
            )
        )
        joins.append(f"LEFT JOIN {table}_totals AS {alias}\n  ON h.{key} = {alias}.{key}")
        items.append(f"COALESCE({alias}.{table}_count, 0)::INT AS {table}_count")
        columns.append(Column(f"{table}_count", "INT"))
        for column in measures:
            out = f"{table}_{column.name}"
            out_type = "NUMBER(18, 2)" if column.type.startswith("NUMBER") else "INT"
            items.append(f"COALESCE({alias}.{out}, 0)::{out_type} AS {out}")
            columns.append(Column(out, out_type))
    ctes.append(
        cte("final", f"SELECT\n{select_list(items)}\nFROM header AS h\n" + "\n".join(joins))
    )
    return project.add(
        Model(
            name=name,
            folder=folder,
            layer="intermediate",
            description=description,
            columns=columns,
            body=with_query(ctes),
            refs=[header.name, *(child.name for child in children)],
        )
    )


def sequence(
    project: Project,
    name: str,
    folder: str,
    source: Model,
    key: str,
    parent: str,
    moment: str,
    measure: str | None,
    description: str,
) -> Model:
    """Per-parent ordering: sequence number, gap to the previous row and running totals."""
    items = [
        f"s.{key}",
        f"s.{parent}",
        f"s.{moment}",
        f"ROW_NUMBER() OVER (PARTITION BY s.{parent} ORDER BY s.{moment}, s.{key})::INT"
        f" AS {parent.removesuffix('_id')}_sequence_number",
        f"DATEDIFF(\n    'day',\n    LAG(s.{moment}) OVER (PARTITION BY s.{parent}"
        f" ORDER BY s.{moment}, s.{key}),"
        f"\n    s.{moment}\n  )::INT AS days_since_previous",
        f"(LAG(s.{key}) OVER (PARTITION BY s.{parent} ORDER BY s.{moment}, s.{key}) IS NULL)"
        "::BOOLEAN AS is_first",
    ]
    columns = [
        Column(key, "VARCHAR", ("not_null", "unique"), nullable=False),
        Column(parent, "VARCHAR"),
        Column(moment, "TIMESTAMP_NTZ"),
        Column(f"{parent.removesuffix('_id')}_sequence_number", "INT"),
        Column("days_since_previous", "INT"),
        Column("is_first", "BOOLEAN"),
    ]
    if measure is not None:
        items.extend(
            [
                f"s.{measure}",
                f"SUM(s.{measure}) OVER (\n    PARTITION BY s.{parent}\n    ORDER BY"
                f" s.{moment}, s.{key}"
                "\n    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW\n  )::NUMBER(18, 2)"
                f" AS running_{measure}",
                f"AVG(s.{measure}) OVER (\n    PARTITION BY s.{parent}\n    ORDER BY"
                f" s.{moment}, s.{key}"
                "\n    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW\n  )::NUMBER(18, 2)"
                f" AS trailing_three_{measure}",
            ]
        )
        columns.extend(
            [
                Column(measure, "NUMBER(18, 2)"),
                Column(f"running_{measure}", "NUMBER(18, 2)"),
                Column(f"trailing_three_{measure}", "NUMBER(18, 2)"),
            ]
        )
    ctes = [
        import_cte("rows_in", f'__ref("{source.name}")'),
        cte(
            "final",
            f"SELECT\n{select_list(items)}\nFROM rows_in AS s\nWHERE\n  s.{parent} IS NOT NULL",
        ),
    ]
    return project.add(
        Model(
            name=name,
            folder=folder,
            layer="intermediate",
            description=description,
            columns=columns,
            body=with_query(ctes),
            refs=[source.name],
        )
    )


def daily(
    project: Project,
    name: str,
    folder: str,
    source: Model,
    day: str,
    dimension: str | None,
    description: str,
    layer: str = "intermediate",
) -> Model:
    """Daily rollup of a model's counts and amounts, by an optional dimension."""
    measures = [
        column
        for column in _numeric(source)
        if column.type.startswith("NUMBER(18, 2)") and column.name != day
    ][:4]
    group = [f"s.{day}"] + ([f"s.{dimension}"] if dimension else [])
    items = [*group, "COUNT(*)::INT AS row_count"]
    columns = [Column(day, "DATE", ("not_null",))]
    if dimension:
        columns.append(Column(dimension, source.column(dimension).type))
    columns.append(Column("row_count", "INT"))
    for column in measures:
        items.append(f"SUM(s.{column.name})::NUMBER(18, 2) AS total_{column.name}")
        items.append(f"ROUND(AVG(s.{column.name}), 2)::NUMBER(18, 2) AS average_{column.name}")
        columns.extend(
            [
                Column(f"total_{column.name}", "NUMBER(18, 2)"),
                Column(f"average_{column.name}", "NUMBER(18, 2)"),
            ]
        )
    if len(measures) >= 2:
        first, second = measures[0].name, measures[1].name
        items.append(
            f"@sql.percent_of(SUM(s.{second}), SUM(s.{first})) AS {second}_share_of_{first}"
        )
        columns.append(Column(f"{second}_share_of_{first}", "NUMBER(9, 4)"))
    ctes = [
        import_cte("rows_in", f'__ref("{source.name}")'),
        cte(
            "final",
            f"SELECT\n{select_list(items)}\nFROM rows_in AS s\nWHERE\n  s.{day} IS NOT NULL\n"
            f"GROUP BY\n" + ",\n".join(f"  {item}" for item in group),
        ),
    ]
    return project.add(
        Model(
            name=name,
            folder=folder,
            layer=layer,
            description=description,
            columns=columns,
            body=with_query(ctes),
            refs=[source.name],
        )
    )


def to_usd(
    project: Project,
    name: str,
    folder: str,
    source: Model,
    key_columns: list[str],
    day: str,
    description: str,
) -> Model:
    """Every amount converted to USD at the latest reference rate on or before the row's day."""
    amounts = [c for c in source.columns if c.type == "NUMBER(18, 2)"][:4]
    items = [f"s.{column.name}" for column in source.columns]
    items.append("fx.rate_to_usd::NUMBER(18, 8) AS rate_to_usd")
    columns = [
        Column(c.name, c.type, ("not_null",) if c.name in key_columns[:1] else ())
        for c in source.columns
    ]
    columns.append(Column("rate_to_usd", "NUMBER(18, 8)"))
    converted = [f"w.{column.name}" for column in source.columns] + ["w.rate_to_usd"]
    for column in amounts:
        converted.append(
            f"ROUND(w.{column.name} * w.rate_to_usd, 2)::NUMBER(18, 2) AS {column.name}_usd"
        )
        columns.append(Column(f"{column.name}_usd", "NUMBER(18, 2)"))
    ctes = [
        import_cte("rows_in", f'__ref("{source.name}")'),
        import_cte("fx_rates", '__source("finance__fx_rates")'),
        cte(
            "with_rates",
            f"SELECT\n{select_list(items)}\nFROM rows_in AS s\n"
            f"ASOF JOIN fx_rates AS fx MATCH_CONDITION (s.{day} >= fx.rate_date)\n"
            "  ON s.currency_code = fx.currency_code",
        ),
        cte("final", f"SELECT\n{select_list(converted)}\nFROM with_rates AS w"),
    ]
    return project.add(
        Model(
            name=name,
            folder=folder,
            layer="intermediate",
            description=description,
            config=[
                'audits [\n    match_rate (\n      name "fx_rate_found",\n'
                '      matched "rate_to_usd IS NOT NULL",\n      minimum_samples 50,\n'
                "      thresholds (warn (below 99.5), error (below 95)),\n    ),\n  ]"
            ],
            columns=columns,
            body=with_query(ctes),
            refs=[source.name],
            sources=["finance__fx_rates"],
        )
    )


def union(
    project: Project,
    name: str,
    folder: str,
    members: list[Model],
    description: str,
    key: str | None,
    via_macro: bool,
) -> Model:
    """UNION ALL of models that share one canonical shape."""
    shape = members[0].columns
    names = [column.name for column in shape]
    if via_macro:
        refs = ", ".join(f'__ref("{member.name}")' for member in members)
        listed = ", ".join(f'"{column}"' for column in names)
        ctes = [
            cte("unioned", f"@py.union_relations(\n  [{refs}],\n  [{listed}],\n)"),
            cte(
                "final",
                "SELECT\n"
                + select_list(["u.source_relation", *(f"u.{column}" for column in names)])
                + "\nFROM unioned AS u",
            ),
        ]
        columns = [Column("source_relation", "VARCHAR")]
    else:
        ctes = [
            import_cte(f"part_{index}", f'__ref("{m.name}")') for index, m in enumerate(members, 1)
        ]
        branches = [
            f"SELECT\n{select_list([f'p.{column}' for column in names])}\nFROM part_{index} AS p"
            for index in range(1, len(members) + 1)
        ]
        ctes.append(cte("final", "\nUNION ALL\n".join(branches)))
        columns = []
    for column in shape:
        if column.name == key:
            audits: tuple[str, ...] = ("not_null", "unique")
        else:
            audits = tuple(audit for audit in column.audits if audit != "unique")
        columns.append(Column(column.name, column.type, audits, column.name != key))
    return project.add(
        Model(
            name=name,
            folder=folder,
            layer="intermediate",
            description=description,
            columns=columns,
            body=with_query(ctes),
            refs=[member.name for member in members],
        )
    )


def child_detail(
    project: Project,
    name: str,
    folder: str,
    child: Model,
    parent: Model,
    key: str,
    description: str,
) -> Model:
    """Array elements joined to their conformed parent, with per-parent element ranking."""
    child_columns = [c for c in child.columns if c.name not in (key, "element_index")]
    parent_columns = [
        c
        for c in parent.columns
        if c.name != key
        and c.type in ("TIMESTAMP_NTZ", "DATE", "VARCHAR")
        and not c.name.endswith("_code")
    ][:3]
    items = [f"e.{c.name}" for c in child_columns] + [f"e.{key}", "e.element_index"]
    items.extend(f"p.{c.name} AS parent_{c.name}" for c in parent_columns)
    items.append(f"COUNT(*) OVER (PARTITION BY e.{key})::INT AS elements_on_parent")
    columns = [Column(c.name, c.type, c.audits, c.nullable) for c in child_columns] + [
        Column(key, "VARCHAR"),
        Column("element_index", "INT"),
    ]
    columns.extend(Column(f"parent_{c.name}", c.type) for c in parent_columns)
    columns.append(Column("elements_on_parent", "INT"))
    ctes = [
        import_cte("elements", f'__ref("{child.name}")'),
        import_cte("parents", f'__ref("{parent.name}")'),
        cte(
            "final",
            f"SELECT\n{select_list(items)}\nFROM elements AS e\nINNER JOIN parents AS p\n"
            f"  ON e.{key} = p.{key}",
        ),
    ]
    return project.add(
        Model(
            name=name,
            folder=folder,
            layer="intermediate",
            description=description,
            columns=columns,
            body=with_query(ctes),
            refs=[child.name, parent.name],
        )
    )
