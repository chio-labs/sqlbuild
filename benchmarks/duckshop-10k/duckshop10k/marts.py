"""The mart layer: per-instance and per-team reports, published facts and dimensions, snapshots."""

from __future__ import annotations

from duckshop10k.core import Column, Model, Project, cte, import_cte, select_list
from duckshop10k.staging import with_query


def _date_column(model: Model) -> str | None:
    return next((c.name for c in model.columns if c.type == "DATE"), None)


_NOT_MEASURES = ("_number", "_index", "_rank", "_sequence", "_year", "priority", "position")


def _measures(model: Model, limit: int = 3, row_count: bool = False) -> list[str]:
    return [
        c.name
        for c in model.columns
        if c.type in ("NUMBER(18, 2)", "NUMBER(38, 0)", "INT")
        and not c.name.endswith(_NOT_MEASURES)
        and "unique" not in c.audits
        and (row_count or c.name != "row_count")
    ][:limit]


def _add(
    project: Project,
    name: str,
    folder: str,
    description: str,
    columns: list[Column],
    ctes: list[str],
    refs: list[str],
    **extra: object,
) -> Model:
    return project.add(
        Model(
            name=name,
            folder=folder,
            layer="marts",
            description=description,
            columns=columns,
            body=with_query(ctes),
            refs=refs,
            **extra,  # type: ignore[arg-type]
        )
    )


def period_rollup(
    project: Project, name: str, folder: str, source: Model, grain: str, subject: str
) -> Model | None:
    day = _date_column(source)
    measures = _measures(source)
    if day is None or not measures:
        return None
    period = f"{grain}_start"
    sums = [f"SUM(s.{m})::{_sum_type(source, m)} AS {m}" for m in measures]
    ctes = [
        import_cte("source_rows", f'__ref("{source.name}")'),
        cte(
            "periods",
            "SELECT\n"
            + select_list([f"DATE_TRUNC('{grain}', s.{day})::DATE AS {period}", *sums])
            + f"\nFROM source_rows AS s\nWHERE\n  s.{day} IS NOT NULL\nGROUP BY\n"
            f"  DATE_TRUNC('{grain}', s.{day})::DATE",
        ),
    ]
    first = measures[0]
    ctes.append(import_cte("calendar", '__ref("dim_date")'))
    final = [f"p.{period}", "d.calendar_year", "d.calendar_month", *(f"p.{m}" for m in measures)]
    final.append(
        f"LAG(p.{first}) OVER (ORDER BY p.{period})::{_sum_type(source, first)} AS previous_{first}"
    )
    final.append(
        f"@sql.percent_of(p.{first} - LAG(p.{first}) OVER (ORDER BY p.{period}),"
        f" LAG(p.{first}) OVER (ORDER BY p.{period})) AS {first}_change_percent"
    )
    ctes.append(
        cte(
            "final",
            f"SELECT\n{select_list(final)}\nFROM periods AS p\nLEFT JOIN calendar AS d\n"
            f"  ON p.{period} = d.calendar_date",
        )
    )
    columns = [Column(period, "DATE", ("not_null", "unique"), nullable=False)]
    columns.extend([Column("calendar_year", "INT"), Column("calendar_month", "INT")])
    columns.extend(Column(m, _sum_type(source, m)) for m in measures)
    columns.append(Column(f"previous_{first}", _sum_type(source, first)))
    columns.append(Column(f"{first}_change_percent", "NUMBER(9, 4)"))
    return _add(
        project,
        name,
        folder,
        f"{subject} by {grain}, with the change on the previous {grain}",
        columns,
        ctes,
        [source.name, "dim_date"],
    )


def _label(dimension: str) -> str:
    """Output name of a dimension published as text; boolean names would imply BOOLEAN."""
    for prefix in ("is_", "has_"):
        if dimension.startswith(prefix):
            return f"{dimension.removeprefix(prefix)}_label"
    return dimension


def _sum_type(model: Model, column: str) -> str:
    column_type = model.column(column).type
    return "INT" if column_type == "INT" else column_type


def share_by(
    project: Project, name: str, folder: str, source: Model, dimension: str, subject: str
) -> Model | None:
    measures = _measures(source, 2)
    if not source.has(dimension) or not measures:
        return None
    first = measures[0]
    out = _label(dimension)
    ctes = [
        import_cte("source_rows", f'__ref("{source.name}")'),
        cte(
            "totals",
            "SELECT\n"
            + select_list(
                [
                    f"COALESCE(s.{dimension}::VARCHAR, 'UNKNOWN') AS {out}",
                    "COUNT(*) AS row_count",
                    *(f"SUM(s.{m}) AS {m}" for m in measures),
                ]
            )
            + f"\nFROM source_rows AS s\nGROUP BY\n  COALESCE(s.{dimension}::VARCHAR, 'UNKNOWN')",
        ),
        cte(
            "final",
            "SELECT\n"
            + select_list(
                [
                    f"t.{out}::VARCHAR AS {out}",
                    "t.row_count::INT AS row_count",
                    *(f"t.{m}::{_sum_type(source, m)} AS {m}" for m in measures),
                    f"ROUND(100 * RATIO_TO_REPORT(t.{first}) OVER (), 2)::NUMBER(9, 4)"
                    f" AS {first}_share_percent",
                    f"RANK() OVER (ORDER BY t.{first} DESC, t.{out})::INT AS {first}_rank",
                ]
            )
            + "\nFROM totals AS t",
        ),
    ]
    columns = [
        Column(out, "VARCHAR", ("not_null", "unique"), nullable=False),
        Column("row_count", "INT"),
    ]
    columns.extend(Column(m, _sum_type(source, m)) for m in measures)
    columns.extend(
        [Column(f"{first}_share_percent", "NUMBER(9, 4)"), Column(f"{first}_rank", "INT")]
    )
    return _add(
        project,
        name,
        folder,
        f"{subject} by {dimension.replace('_', ' ')}, with each one's share of the total",
        columns,
        ctes,
        [source.name],
    )


def top_n(
    project: Project, name: str, folder: str, source: Model, entity: str, limit: int, subject: str
) -> Model | None:
    measures = _measures(source, 2)
    if not source.has(entity) or not measures:
        return None
    first = measures[0]
    ctes = [
        import_cte("source_rows", f'__ref("{source.name}")'),
        cte(
            "totals",
            "SELECT\n"
            + select_list(
                [f"s.{entity}", "COUNT(*) AS row_count", *(f"SUM(s.{m}) AS {m}" for m in measures)]
            )
            + f"\nFROM source_rows AS s\nWHERE\n  s.{entity} IS NOT NULL\nGROUP BY\n  s.{entity}",
        ),
        cte(
            "final",
            "SELECT\n"
            + select_list(
                [
                    f"t.{entity}::VARCHAR AS {entity}",
                    "t.row_count::INT AS row_count",
                    *(f"t.{m}::{_sum_type(source, m)} AS {m}" for m in measures),
                    f"RANK() OVER (ORDER BY t.{first} DESC, t.{entity})::INT AS rank_by_{first}",
                ]
            )
            + f"\nFROM totals AS t\nQUALIFY RANK() OVER (ORDER BY t.{first} DESC,"
            f" t.{entity}) <= {limit}",
        ),
    ]
    columns = [
        Column(entity, "VARCHAR", ("not_null", "unique"), nullable=False),
        Column("row_count", "INT"),
    ]
    columns.extend(Column(m, _sum_type(source, m)) for m in measures)
    columns.append(Column(f"rank_by_{first}", "INT"))
    return _add(
        project,
        name,
        folder,
        f"The top {limit} {entity.replace('_', ' ')}s of {subject} by {first.replace('_', ' ')}",
        columns,
        ctes,
        [source.name],
    )


def breakdown(
    project: Project, name: str, folder: str, source: Model, dimension: str, subject: str
) -> Model | None:
    day = _date_column(source)
    if not source.has(dimension) or day is None:
        return None
    label = f"COALESCE(s.{dimension}::VARCHAR, 'UNKNOWN')"
    out = _label(dimension)
    ctes = [
        import_cte("source_rows", f'__ref("{source.name}")'),
        cte(
            "monthly",
            "SELECT\n"
            + select_list(
                [
                    f"DATE_TRUNC('month', s.{day})::DATE AS month_start",
                    f"{label} AS {out}",
                    "COUNT(*) AS row_count",
                ]
            )
            + f"\nFROM source_rows AS s\nWHERE\n  s.{day} IS NOT NULL\nGROUP BY\n"
            f"  DATE_TRUNC('month', s.{day})::DATE,\n  {label}",
        ),
        cte(
            "final",
            "SELECT\n"
            + select_list(
                [
                    "m.month_start",
                    f"m.{out}::VARCHAR AS {out}",
                    "m.row_count::INT AS row_count",
                    "ROUND(100 * RATIO_TO_REPORT(m.row_count) OVER (PARTITION BY m.month_start), 2)"
                    "::NUMBER(9, 4) AS share_of_month_percent",
                ]
            )
            + "\nFROM monthly AS m",
        ),
    ]
    columns = [
        Column("month_start", "DATE", ("not_null",)),
        Column(out, "VARCHAR", ("not_null",)),
        Column("row_count", "INT"),
        Column("share_of_month_percent", "NUMBER(9, 4)"),
    ]
    return _add(
        project,
        name,
        folder,
        f"Monthly count of {subject} by {dimension.replace('_', ' ')} and its share of the month",
        columns,
        ctes,
        [source.name],
    )


def cohorts(
    project: Project, name: str, folder: str, source: Model, parent: str, moment: str, subject: str
) -> Model | None:
    if not (source.has(parent) and source.has(moment)):
        return None
    ctes = [
        import_cte("source_rows", f'__ref("{source.name}")'),
        cte(
            "firsts",
            "SELECT\n"
            + select_list(
                [
                    f"s.{parent}",
                    f"s.{moment}",
                    f"MIN(s.{moment}) OVER (PARTITION BY s.{parent}) AS first_at",
                ]
            )
            + f"\nFROM source_rows AS s\nWHERE\n  s.{parent} IS NOT NULL",
        ),
        cte(
            "final",
            "SELECT\n"
            + select_list(
                [
                    "DATE_TRUNC('month', f.first_at)::DATE AS cohort_month",
                    f"DATEDIFF('month', f.first_at, f.{moment})::INT AS months_since_first",
                    f"COUNT(DISTINCT f.{parent})::INT AS active_count",
                    "COUNT(*)::INT AS row_count",
                ]
            )
            + "\nFROM firsts AS f\nGROUP BY\n  DATE_TRUNC('month', f.first_at)::DATE,\n"
            f"  DATEDIFF('month', f.first_at, f.{moment})::INT",
        ),
    ]
    columns = [
        Column("cohort_month", "DATE", ("not_null",)),
        Column("months_since_first", "INT", ("non_negative",)),
        Column("active_count", "INT"),
        Column("row_count", "INT"),
    ]
    return _add(
        project,
        name,
        folder,
        f"Monthly cohorts of {subject}: how many are active each month after their first",
        columns,
        ctes,
        [source.name],
    )


REASON_CLASSES: tuple[tuple[str, str], ...] = (
    ("damaged", "(broken|damag|crack|leak)"),
    ("wrong_item", "(wrong|incorrect|not what)"),
    ("size_fit", "(small|large|size|fit)"),
    ("late", "(late|delay|never arrived)"),
    ("changed_mind", "(changed my mind|no longer|not needed)"),
)


def classify_text(
    project: Project, name: str, folder: str, source: Model, text: str, subject: str
) -> Model | None:
    if not source.has(text):
        return None
    cases = "\n".join(
        f"    WHEN REGEXP_LIKE(LOWER(s.{text}), '.*{pattern}.*') THEN '{label}'"
        for label, pattern in REASON_CLASSES
    )
    ctes = [
        import_cte("source_rows", f'__ref("{source.name}")'),
        cte(
            "classified",
            f"SELECT\n  CASE\n{cases}\n    ELSE 'other'\n  END AS reason_class\n"
            "FROM source_rows AS s",
        ),
        cte(
            "final",
            "SELECT\n"
            + select_list(
                [
                    "c.reason_class::VARCHAR AS reason_class",
                    "COUNT(*)::INT AS row_count",
                    "ROUND(100 * RATIO_TO_REPORT(COUNT(*)) OVER (), 2)::NUMBER(9, 4) AS"
                    " share_percent",
                ]
            )
            + "\nFROM classified AS c\nGROUP BY\n  c.reason_class",
        ),
    ]
    labels = ", ".join(f"'{label}'" for label, _ in REASON_CLASSES)
    columns = [
        Column(
            "reason_class",
            "VARCHAR",
            ("not_null", "unique", f"accepted_values (values [{labels}, 'other'])"),
            nullable=False,
        ),
        Column("row_count", "INT"),
        Column("share_percent", "NUMBER(9, 4)"),
    ]
    return _add(
        project,
        name,
        folder,
        f"{subject} classified by keywords in their free-text reason",
        columns,
        ctes,
        [source.name],
    )


def wide_daily(
    project: Project, name: str, folder: str, sources: list[tuple[str, Model]], description: str
) -> Model:
    """One row per day joining the first measure of many daily reports, the wide-mart shape."""
    days: list[str] = []
    ctes: list[str] = []
    for alias, source in sources:
        day = _date_column(source)
        measure = _measures(source, 1, row_count=True)[0]
        ctes.append(
            cte(
                f"{alias}_daily",
                "SELECT\n"
                + select_list(
                    [
                        f"s.{day}" if day == "report_date" else f"s.{day} AS report_date",
                        f"SUM(s.{measure}) AS {alias}_{measure}",
                    ]
                )
                + f'\nFROM __ref("{source.name}") AS s\nGROUP BY\n  s.{day}',
            )
        )
        days.append(f"SELECT d.report_date\nFROM {alias}_daily AS d")
    ctes.append(cte("calendar_rows", "\nUNION ALL\n".join(days)))
    ctes.append(cte("calendar", "SELECT DISTINCT r.report_date\nFROM calendar_rows AS r"))
    items = ["c.report_date"]
    joins = []
    columns = [Column("report_date", "DATE", ("not_null", "unique"), nullable=False)]
    for alias, source in sources:
        measure = _measures(source, 1, row_count=True)[0]
        out = f"{alias}_{measure}"
        items.append(f"COALESCE({alias}.{out}, 0)::{_sum_type(source, measure)} AS {out}")
        joins.append(
            f"LEFT JOIN {alias}_daily AS {alias}\n  ON c.report_date = {alias}.report_date"
        )
        columns.append(Column(out, _sum_type(source, measure)))
    ctes.append(
        cte("final", f"SELECT\n{select_list(items)}\nFROM calendar AS c\n" + "\n".join(joins))
    )
    return _add(project, name, folder, description, columns, ctes, [s.name for _, s in sources])


def publish(
    project: Project,
    name: str,
    folder: str,
    source: Model,
    key: str,
    description: str,
    config: list[str] | None = None,
    factory: bool = True,
) -> Model:
    """A published fct_ or dim_ model: an enforced contract over an intermediate model."""
    items = []
    columns = []
    for column in source.columns:
        items.append(f"s.{column.name}::{column.type} AS {column.name}")
        audits = ("not_null", "unique") if column.name == key else ()
        columns.append(Column(column.name, column.type, audits, column.name != key))
    ctes = [
        import_cte("source_rows", f'__ref("{source.name}")'),
        cte("final", f"SELECT\n{select_list(items)}\nFROM source_rows AS s"),
    ]
    head = list(config or [])
    head.append("contract enforced")
    if factory and name.startswith("fct_"):
        head.append("audit_factories [fact_table_quality]")
    return _add(project, name, folder, description, columns, ctes, [source.name], config=head)
