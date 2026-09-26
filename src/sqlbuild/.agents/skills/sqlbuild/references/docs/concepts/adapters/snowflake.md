<!-- generated-by: sqlbuild skills -->

# Snowflake

> Snowflake adapter configuration for SQLBuild.

Online: https://sqlbuild.com/docs/concepts/adapters/snowflake/

Snowflake requires the optional `snowflake-connector-python` dependency:

```bash
pip install 'sqlbuild[snowflake]'
# or
uv pip install 'sqlbuild[snowflake]'
```

## Connection config

```toml
adapter = "snowflake"
default_target = "dev"

[connections.warehouse]
account = "my_org-my_account"
user = "my_user"
password = "my_password"
role = "TRANSFORM_ROLE"
warehouse = "TRANSFORM_WH"

[targets.dev]
connection = "warehouse"
database = "ANALYTICS"
schema = "RAW"
```

Connection fields are passed directly to `snowflake.connector.connect()`. See the [Snowflake Connector documentation](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect) for all available options, including key-pair authentication, OAuth, and SSO. Put the authoritative database and schema on the target.

## Session initialization

On connect, SQLBuild applies the connection's role and warehouse, then applies the active
target's authoritative database and schema. These ensure the session context is set correctly
regardless of the user's default settings.

## Shared connections across targets

Use multiple targets to reuse one Snowflake connection while selecting different authoritative
databases and schemas:

```toml
adapter = "snowflake"

[connections.warehouse]
account = "my_org-my_account"
user = "my_user"
password = "my_password"
role = "TRANSFORM_ROLE"
warehouse = "TRANSFORM_WH"

[targets.prod]
connection = "warehouse"
database = "PROD_DB"
schema = "prod"

[targets.dev]
connection = "warehouse"
database = "DEV_DB"
schema = "dev"
```

## Cost estimates

Snowflake builds show a compact per-run busy-compute estimate. SQLBuild attributes visible
overlapping query intervals fairly across active queries, converts attributed seconds using the
warehouse-size credit rate, and estimates USD from the configured rate:

```toml
[cost]
usd_per_credit = 3.00
```

The default is `3.00` USD per credit and is visibly marked as a default. Set it to your Snowflake
contract rate. Use `sqb cost`, `sqb cost latest`, `sqb cost <run_id>`, or
`sqb cost history --since 7d` to inspect persisted records. `--json` and `--json-output PATH`
provide a versioned, decimal-safe output contract. Pending detail records are refreshed from
Snowflake when inspected again.

These values are attributed compute credits and estimated cost, not Snowflake-billed credits or
invoice reconciliation. The estimate uses only query history visible to the executing role and does
not reconstruct invisible concurrent work, warehouse resume or idle tail, the 60-second minimum,
cloud-services credits, contract adjustments, or multi-cluster billing. Run metadata and query IDs
are stored under `target/executions/<run_id>/`; that statement ledger stores only an SQL digest,
not SQL text. Executed SQL artifacts are stored separately under the sensitive `target/run/` tree.
