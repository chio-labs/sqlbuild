<!-- generated-by: sqlbuild skills -->

# sqb query

> Run ad hoc SQL queries against the project database.

Online: https://sqlbuild.com/docs/cli/query/

Execute ad hoc SQL against the active project connection. Useful for inspecting data, debugging models, or running one-off queries without leaving the SQLBuild CLI.

## Usage

```bash
sqb --project-dir <path> query "SELECT * FROM dev.fact_orders LIMIT 5"
```

Or from a file:

```bash
sqb --project-dir <path> query --file my_query.sql
```

File paths are resolved from the current working directory.

## Flags

| Flag | Description |
|------|-------------|
| `sql` | SQL to execute (positional argument) |
| `--file` | Read SQL from a file instead of the command line |
| `--format` | Output format: `long` (default), `table`, `json`, or `csv` |
| `--limit` | Maximum rows to return (default: 20) |
| `--no-limit` | Disable the row limit |

## Output formats

### long (default)

Vertical record format, one field per line:

```
-[ RECORD 1 ]---------------------------+
order_id | 1
customer_id | 100
status   | completed

-[ RECORD 2 ]---------------------------+
order_id | 2
customer_id | 200
status   | completed

2 rows
```

### table

Horizontal table format:

```
order_id | customer_id | status
-------- | ----------- | ---------
1        | 100         | completed
2        | 200         | completed

2 rows
```

### json

JSON array of objects:

```json
[{"order_id": 1, "customer_id": 100, "status": "completed"}]
```

### csv

Standard CSV with headers:

```csv
order_id,customer_id,status
1,100,completed
2,200,completed
```

## Examples

```bash
# Quick inspection with default format
sqb query "SELECT * FROM dev.fact_orders"

# Table format with higher limit
sqb query "SELECT * FROM dev.dim_customers" --format table --limit 50

# Export to JSON
sqb query "SELECT * FROM dev.daily_revenue" --format json --no-limit

# Run SQL from a file
sqb query --file debug_query.sql
```
