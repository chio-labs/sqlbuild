<!-- generated-by: sqlbuild skills -->

# Audits

> Violation and measurement checks that gate data and record quality outcomes.

Online: https://sqlbuild.com/docs/concepts/audits/

## Contents

- How audits work
- Measurement audits
- Audit factories
- Result history
- Built-in audits
- Custom generic audits
- Singular audits
- Source audits
- Seed audits
- Severity
- Run scope
- Running audits standalone

Audits are SQL queries that verify data quality. Violation audits return invalid rows. Measurement
audits return a value that SQLBuild evaluates against authored thresholds and sample policy.
SQLBuild can run audits before table promotion or incremental DML so error-severity failures do not
reach the target.

## How audits work

Violation audits pass when their query returns zero rows. Measurement audits produce one value and
optionally a sample count; their outcome is `pass`, `warn`, `fail`, or `insufficient`.

For `error` severity audits:
- **Full table builds:** SQLBuild materializes into a staging table, runs audits against it, and only promotes to the target if all audits pass. If any fail, the staging table is kept for inspection and the production table is untouched.
- **Incremental models:** Delta-phase audits validate each batch before DML is applied. If an audit fails, the batch is not applied.

For `warn` severity audits, the build continues and the failure is reported in the output.

## Measurement audits

A reusable measurement audit separates the aggregate query from optional bounded evidence:

```sql
-- audits/generic/valid_order_rate.sql
AUDIT (
  evaluation measurement,
  value valid_rate,
  sample_count total_rows,
  sample_unit rows
);

MEASURE (
  SELECT
    COUNT(*) AS total_rows,
    100.0 * AVG(CASE WHEN @condition THEN 1 ELSE 0 END) AS valid_rate
  FROM @relation
);

EVIDENCE (
  SELECT * FROM @relation WHERE NOT (@condition)
);
```

Attach threshold and sample policy where the audit is used:

```sql
MODEL (
  audits [
    valid_order_rate (
      condition "order_id IS NOT NULL",
      minimum_samples 100,
      evidence_limit 20,
      thresholds (warn (below 99.9), error (below 99))
    )
  ]
);
```

`minimum_samples` keeps low-volume measurements distinct as `insufficient` rather than inventing a
pass or failure. Evidence is diagnostic and bounded by `evidence_limit`; the measurement and
threshold determine the outcome.

## Audit factories

Use a Python audit factory when many related audit instances should be generated from one reviewed
declaration:

```python
from sqlbuild.audits import AuditCase, AuditSeverity, audit_factory

@audit_factory
def order_quality():
    return [
        AuditCase(
            name="positive_amount",
            definition="expression_is_true",
            arguments={"expression": "amount > 0"},
            severity=AuditSeverity.ERROR,
        )
    ]
```

Attach it with `MODEL (audit_factories [order_quality])`. Generated cases compile to the same audit
contract as directly authored instances.

## Result history

Native warehouse adapters best-effort append confirmed audit outcomes to
`_sqlbuild_audit_results`. Rows are immutable and use deterministic IDs, so retrying the same result
is idempotent. Projection failure is reported separately and does not change the audit outcome or
command exit code. Lifecycle sinks can also consume the corresponding `audit_completed` fact, which
is published as each audit finishes.

## Built-in audits

SQLBuild includes four generic audits out of the box. You do not need to define these in `audits/generic/` - they are available automatically:

| Audit | Description | Parameters |
|-------|-------------|------------|
| `not_null` | Fails if any row has a NULL value in the column | Column-level only |
| `unique` | Fails if any non-NULL value appears more than once | Column-level only |
| `accepted_values` | Fails if any non-NULL value is not in the allowed list | `values` - list of allowed values |
| `relationships` | Fails if any non-NULL value does not exist in the referenced column | `to` - target relation, `field` - target column |

### Using built-in audits

Attach them in the `MODEL()` header like any generic audit:

```sql
MODEL (
  materialized view,
  tags [staging],
  columns (
    order_id (audits [not_null, unique]),
    customer_id (audits [not_null]),
    status (
      audits [
        accepted_values (values ["placed", "preparing", "ready", "completed", "cancelled"]),
      ],
    ),
    payment_method (
      audits [
        relationships (to "stg_payments", field "method"),
      ],
    ),
  ),
);
```

### Overriding built-in audits

If you define a generic audit with the same name as a built-in (e.g. `audits/generic/not_null.sql`), your definition takes precedence. SQLBuild emits a warning so you're aware of the override:

```
warning[P003]: project audit 'not_null' overrides built-in audit 'not_null'
```

## Custom generic audits

Beyond the built-ins, you can define reusable SQL templates in a generic audit role. They use `@parameter` placeholders that are resolved by the audit engine at compile time.

| Location | Who can attach it |
|----------|-------------------|
| `audits/generic/` | Resources anywhere in the project |
| `<folder>/_sqlbuild/audits/generic/` | Resources in `<folder>` and below |
| `<folder>/_sqlbuild/_audits/generic/` | Resources directly in `<folder>` only |

A generic audit must live under the nearest folder that contains every model, source, seed, or
audit factory that attaches it. A top-level generic audit used only by models under
`models/marts/` fails to compile and names the folder it belongs in:

```
error[P001]: Invalid declaration scope index:
[S024] Declaration 'audit:non_negative' is currently project at 'audits/generic' ...
Move it to 'models/marts/_sqlbuild/_audits/generic/'
```

Attaching a scoped generic audit from a folder that cannot see it fails with `S006`. Built-in
audits are available everywhere and are unaffected. See
[Where to Put Declarations](declaration-scopes/placement.md).

```sql
-- audits/generic/expression_is_true.sql
AUDIT ();

SELECT *
FROM @relation
WHERE NOT (@expression)
```

### Audit parameters

Generic audit SQL uses `@name` for parameter placeholders. These are resolved by the audit engine, not the general SQL interpolation system:

| Parameter | Description |
|-----------|-------------|
| `@column` | The column name (auto-populated for column-level audits) |
| `@relation` | The target relation (auto-populated from the attached model or source) |
| `@'name'` | A quoted parameter passed from the audit declaration (e.g. `@'values'`) |
| `@name` | An unquoted parameter passed from the audit declaration (e.g. `@expression`) |

Generic and singular audit SQL uses macros, constants, and enums available from the folder that owns
the audit, not from a model or source that uses the audit. An audit in
`models/marts/_sqlbuild/_audits/generic/` sees the declarations a model in `models/marts/` sees; an
audit in the top-level `audits/` roles sees only project-wide declarations. Using a declaration
that is not visible from there is a compile error. See
[How Visibility Works](declaration-scopes/visibility.md).

### Attaching custom generic audits

```sql
MODEL (
  materialized table,
  audits [
    expression_is_true (
      name "revenue_is_non_negative",
      expression "total_revenue_cents >= 0",
    ),
  ],
);
```

## Singular audits

Singular audits are standalone SQL files that check a relationship between resources. They must be
cross-resource: a singular audit references two or more models, or at least one model plus a
source, seed, or table function, through `__ref()`, `__source()`, `__seed()`, or `__table_fn()`.

```sql
-- models/marts/_sqlbuild/audits/singular/orders_have_payments.sql
AUDIT (
  name "completed_orders_have_payments",
  severity error
);

SELECT o.order_id
FROM __ref("fact_orders") o
LEFT JOIN __ref("stg_payments") p ON o.order_id = p.order_id
WHERE p.payment_id IS NULL
  AND o.order_status = 'completed'
```

Other shapes fail with `P004`:

| Singular audit references | Use instead |
|---------------------------|-------------|
| One model only, including a self-join of that model | A generic audit attached to the model that selects `FROM @relation` |
| Sources or seeds only | YAML audits on the source or seed |
| No SQLBuild resource, such as hard-coded relation names | Reference resources with `__ref()`, `__source()`, or `__seed()` |

Singular audits live only in a `singular/` role:

| Location | What it may reference |
|----------|-----------------------|
| `audits/singular/` | Resources whose nearest shared folder is the project root, such as models in sibling folders or a model and a source |
| `<folder>/_sqlbuild/audits/singular/` | Resources in `<folder>` and below |

There is no `_audits/singular/` role, because singular audits are never attached by name. A
singular audit must live under the nearest folder containing everything it references. Audit files
directly under `audits/` or in any other `audits/` child are compile errors.

SQLBuild infers where a singular audit runs from its references. When it references exactly one
model, or one referenced model is downstream of every other referenced model, the audit attaches
to that model. Otherwise it runs at the end of the build.

## Source audits

Sources support the same audit system as models. Audits attached to sources run *before* any dependent model is built:

```yaml
sources:
  - name: raw__orders
    columns:
      - name: id
        audits:
          - not_null
          - unique
    audits:
      - expression_is_true:
          name: no_future_orders
          expression: "ordered_at <= CURRENT_TIMESTAMP"
```

If a source audit with `error` severity fails, all downstream models that depend on that source are blocked. This lets you catch data quality issues at the source before any transformations run.

## Seed audits

Seeds use the same YAML audit syntax as sources, at table and column level:

```yaml
seeds:
  - name: waffle_types
    columns:
      - name: waffle_type_id
        type: INTEGER
        audits:
          - not_null
          - unique
    audits:
      - expression_is_true:
          expression: "price_cents >= 0"
          severity: error
```

Seed audits run in `sqb build` after the seed loads. An `error` failure blocks every model that
depends on the seed; a `warn` failure is reported and the build continues.

## Severity

| Severity | Behavior |
|----------|----------|
| `error` | Blocks the build. Staging table is not promoted, DML is not applied. |
| `warn` | Reports a warning but allows the build to continue. |

Set the default severity in `sqlbuild_project.toml`:

```toml
[settings]
default_audit_severity = "warn"
```

Override per audit instance in the `MODEL()` header:

```sql
columns (
  order_id (audits [not_null (severity error)]),
),
```

## Run scope

Audits on incremental models can run at different lifecycle phases:

| Scope | Behavior |
|-------|----------|
| `final` | Run once against the staged table before promotion (default). |
| `delta_and_final` | Run against each delta batch before DML, then again against the target after all batches complete. |

```sql
MODEL (
  materialized incremental,
  ...
  columns (
    activity_hour (audits [not_null (run_scope delta_and_final)]),
  ),
  audits [
    expression_is_true (
      name "orders_placed_is_non_negative",
      expression "orders_placed >= 0",
      run_scope delta_and_final,
    ),
  ],
);
```

Delta-phase audits with `error` severity block DML before the target is updated. This is visible in the build output as `audit (d)` for delta-phase and `audit (f)` for final-phase:

```
  10/13  table     hourly_order_activity  (delete_insert)                OK     0.16s
           audit (d) expression_is_true                                  PASS  4/4
           audit (d) not_null (activity_hour)                            PASS  4/4
           audit (f) expression_is_true                                  PASS
           audit (f) not_null (activity_hour)                            PASS
```

The `4/4` indicates the audit passed for all 4 microbatch batches.

If a model is not incremental, `delta_and_final` degrades to `final` automatically.

## Running audits standalone

```bash
sqb audit
```

This runs all audits without rebuilding any models.

Standalone audits run serially unless concurrency is configured explicitly, through
`SQLBUILD_CONCURRENCY`, or in project settings. For example, `sqb audit --concurrency 8` runs up
to eight selected audits at once, using one warehouse connection per active worker. Increase this
limit deliberately because parallel queries can increase warehouse load and cost. See
[`sqb audit`](../cli/audit.md) for precedence, ordering, and cancellation details.
