<!-- generated-by: sqlbuild skills -->

# Findings and exceptions

> Understand Rule diagnostics and record intentional exceptions safely.

Online: https://sqlbuild.com/docs/concepts/rules/findings-and-exceptions/

A Rule finding identifies an exact code, project-relative path, line, column, message, and
remediation. Error findings make compilation fail and prevent artifact completion.

## Exact exceptions

Use an exact exception for one known finding. Exceptions require a reason and are stale-checked:

```toml
[[rules.rule_exceptions]]
rule = "SQBRSQL004"
path = "models/examples/sample_orders.sql"
reason = "This example intentionally demonstrates one sampled row."
```

An exception refers to one exact Rule code and path. If the finding disappears, SQLBuild reports
the stale exception so obsolete configuration does not accumulate silently.

## Path- and resource-scoped ignores

Use a path ignore when a documented project area intentionally follows a different convention:

```toml
[[rules.rule_ignores]]
rules = ["SQBRSQL"]
paths = ["models/examples/**"]
reason = "Examples retain intentionally minimal SQL."
```

Path ignores accept exact codes and family prefixes. Keep their scope narrow and explain why the
project differs from the selected requirement.

Use `selectors` when the exception follows graph-resource identities or lineage rather than files:

```toml
[[rules.rule_ignores]]
rules = ["SQBRSQL021"]
selectors = ["intermediate_*"]
reason = "These intermediate interfaces intentionally preserve upstream columns."
```

Selectors use the same grammar as SQLBuild commands, including exact names, name globs, tags,
resource paths, and graph expansion such as `+intermediate_*`. Use `paths` for authored-file glob
matching, including SQL tests and audits that are not graph resources:

```toml
[[rules.rule_ignores]]
rules = ["SQBRSQL021"]
paths = ["models/**/intermediate_*.sql"]
reason = "These intermediate SQL files intentionally preserve upstream columns."
```

`paths` and `selectors` may be combined in one scoped ignore. Both forms require a reason.

## Inline suppressions

Suppress one SQL Rule finding on the next SQL line with a reasoned comment:

```sql
-- sqb: ignore SQBRSQL004 because the sample intentionally keeps one row
SELECT customer_id FROM customers LIMIT 1
```

A directive without a reason, or one that no longer matches a finding, is reported as
`SQBRSQL000`.

## Forbidding exceptions

Set `allow_exceptions = false` to require that every selected Rule passes everywhere:

```toml
[rules]
select = ["SQBRSQL", "SQBRMODEL"]
ignore = ["SQBRSQL004"]
allow_exceptions = false   # default true
```

With exceptions forbidden, any `[[rules.rule_exceptions]]` or `[[rules.rule_ignores]]` entry fails
configuration loading with an error that counts the entries and shows the setting to change, so
`sqb compile` and `sqb rules run` stop before evaluating Rules. Each inline `-- sqb: ignore`
directive becomes a `SQBRSQL000` error at the directive and suppresses nothing, so the finding it
was hiding is reported too. The project-wide `ignore` list stays allowed: it is the adoption switch
for a Rule across the whole project, not a scoped escape hatch. `[[rules.graph_edge_exceptions]]`,
`[[rules.select_star_allow]]` and `[[rules.threshold_overrides]]` are not affected.

## Mandatory correctness

Mandatory compiler correctness is not configurable and cannot be suppressed. A project must first
compile into a trustworthy representation before any selected Rule can run.

## Machine-readable findings

Use JSON when another tool consumes findings:

```bash
sqb compile --json
sqb rules --json run SQBRSQL
```

Machine-readable output remains on stdout. Lifecycle progress and terminal status are written to
stderr.
