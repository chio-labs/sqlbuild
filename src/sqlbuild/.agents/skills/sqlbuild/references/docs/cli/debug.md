<!-- generated-by: sqlbuild skills -->

# debug

> Validate project configuration and test the warehouse connection.

Online: https://sqlbuild.com/docs/cli/debug/

Checks that your project config is valid, the adapter is resolvable, and the warehouse connection works. Useful for diagnosing setup issues.

## Usage

```bash
sqb debug [flags]
```

## What it checks

The command runs three groups of checks:

**Runtime** - SQLBuild version, Python version, Python path, OS info.

**Configuration** - Finds and validates `sqlbuild_project.toml`, loads `sqlbuild_local.toml` if present, resolves the adapter and active target. For Snowflake it also shows the warehouse each [command group](../concepts/project-configuration.md#command-group-warehouses) connects with and where that value came from.

**Connection** - Displays connection settings as `sqb debug` itself uses them, with the `query` warehouse group applied (secrets are masked), attempts to connect to the warehouse, and runs `SELECT 1` to verify query execution.

## Flags

| Flag | Description |
|------|-------------|
| `--no-connection` | Skip the connection and query tests. Useful for validating config without warehouse access. |
| `--json` | Output results as JSON instead of formatted text. |
| `--warehouse <name>` | Snowflake warehouse for this invocation; overrides the target's `query` [warehouse group](../concepts/project-configuration.md#command-group-warehouses) and the connection warehouse |

## Example

```bash
sqb debug
```

```
SQLBuild Diagnostics

Runtime:
  sqlbuild version: 0.2.1
  python version: 3.14.3
  python path: /home/user/.venv/bin/python3
  os info: Linux-6.6.87

Configuration:
  project file: /home/user/waffle_shop/sqlbuild_project.toml [OK found and valid]
  local config: /home/user/waffle_shop/sqlbuild_local.toml [OK found]
  project: waffle_shop [OK loaded]
  adapter: snowflake [OK found]
  target: dev [OK resolved]
  build warehouse: BUILD_WH [OK sqlbuild_project.toml [targets.dev.warehouses] build]
  query warehouse: SQB_WH [OK connection warehouse]

Connection:
  account: FJMQFQV-OJ66172
  authenticator: programmatic_access_token
  database: SQB_DB
  role: role_sqb_test
  schema: TEST
  token: ****
  user: svc_sqb_test
  warehouse: SQB_WH
  connection test: [OK connected]
  query test: [OK SELECT 1]
```

## Exit codes

Returns `0` when all checks pass, `1` when any check fails (e.g. connection refused, invalid config).
