# Target execution limits

Named targets can set optional limits for `sqb build`. Limits are useful for development targets
where an unexpectedly broad selector or long-running command should stop instead of consuming an
unbounded amount of warehouse compute.

```toml
[targets.dev]
connection = "warehouse"
database = "analytics"
schema = "dev_alice"

[targets.dev.execution_limits]
max_models = 125
max_duration = "45m"
remediation = """
Review the expanded plan and confirm that the selected scope is intentional.
Automated tools must request approval before changing this policy.
"""
```

All fields are optional. A target without an `execution_limits` section retains unlimited existing
behavior, so production or orchestrated targets do not need placeholder values.

## Model limit

`max_models` is a positive integer. SQLBuild expands selectors and counts model entries that would
execute. When the count exceeds the target limit, the build exits before clone, load, or model
execution begins. The error reports the target, selected count, configured maximum, configuration
key, and confirms that no warehouse changes were made.

`sqb plan` remains unrestricted and can be used to inspect a broad selection safely.

## Duration limit

`max_duration` is a positive fixed duration such as `30m`, `2h`, or `90s`. It covers planning and
warehouse-mutating build phases after target resolution. SQLBuild stops dispatching work at the
deadline and passes the remaining duration to each warehouse statement so in-flight work is
cancelled by the adapter.

Safe in-flight cancellation is currently supported by the Snowflake adapter, whose maximum accepted
duration is seven days. SQLBuild rejects an unsupported duration or an adapter that cannot guarantee
active statement cancellation rather than presenting a limit that may leave warehouse work running.

A duration failure may occur after earlier models have completed. Its error therefore distinguishes
the timeout from a pre-execution model-limit failure and states that warehouse changes may already
have occurred.

## Custom remediation

`remediation` is optional project-authored text. SQLBuild appends it to model-count, duration, and
unsupported-adapter errors after the factual error details. This lets each project define its own
approval or recovery process without SQLBuild recommending that users weaken local policy.

## Local overrides

The same section is accepted in `sqlbuild_local.toml` and follows normal field-by-field local target
precedence:

```toml
[targets.dev.execution_limits]
max_models = 200
max_duration = "90m"
```

This permits an intentional developer override while keeping the shared target policy visible in
`sqlbuild_project.toml`. Other target fields and any execution-limit fields omitted locally continue
to inherit their project values.
