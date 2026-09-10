---
name: "fensu-sqlbuild"
description: "Use when modifying the sqlbuild project governed by fensu.toml. Includes aggregate Fensu guidance for analyzers: python, rust."
---

<!-- generated-by: fensu skills -->
<!-- fensu-skill-owner: {"content_fingerprint":"530dc833b5863c62b2f67c62c2fef188e49a34b6cd44914d1a12337224b99c7a","identity":"fensu-sqlbuild","input_fingerprint":"cea8d18da2326843e34073d0feb0e83d72dde3c29f071b7fa7f463572faf0c14","owner":"64fe107e0d1d3ae11b423fb02628dc8154b515f5897e3abf4df4a5345de92b5a","schema":2} -->

# Fensu

Fensu checks code ownership, dependency boundaries, module roles, function shape, and test conventions. This skill aggregates the active policy for every configured analyzer target.
Load this guidance before running any `fensu` command or changing Fensu configuration.

## Commands

- Run `fensu check` after architecture-relevant changes.
- Run `fensu rule <CODE>` to inspect a diagnostic and its remediation.
- Run `fensu skills` after changing any target's rule selection or custom rules.
- Run `fensu map <SYMBOL>` for Python call-flow navigation.

## Analyzer Targets

### `python` (python)

- Analyzer: `python`
- Parser provenance: `python-ruff-py312-v1`; cache contract: `python-ruff-py312-v1`
- Target policy fingerprint: `06925d63468b83f97076688a936c16ff379a8792cc0488013fcd58af7a48b48b`

#### Navigation And Work Handoffs

For any non-trivial change that crosses module or package boundaries, run `fensu map <symbol> --depth 4` before editing. Rerun the same map after implementation to explain the changed flow. Skip only isolated single-file edits.

Treat the map as a deterministic call skeleton whose primary benefit is helping the user understand the system, not proving that the agent explored it. Do not paste a raw map as the handoff. Read the relevant source to explain purpose and branches, use the diff to identify what changed and why, and use checks and tests to state what was verified. Never guess through unresolved calls. If the map cannot resolve the flow, state that and continue with direct source inspection.

After a substantial chunk of work, rerun `fensu check` and the same map. Include a user-facing walkthrough only when it materially clarifies a multi-module change. Default to the smallest affected branch, normally three to eight lines:

```text
build_result(...)                           domain/main/build.py:24
└── assemble_result(...)                    domain/_helpers/assemble.py:41
    CHANGED: state the behavioral difference and why it was made.
VERIFIED: name the check that proves the changed boundary.
```

Replace the template with facts from the repository. Preserve enough parent context to orient the user, but omit unchanged branches that do not aid understanding. Use a full before/after walkthrough only when ownership or phase boundaries changed substantially. `DONE`, `PENDING`, and `WE ARE HERE` are agent-authored work-state annotations, not Fensu output.

Every displayed function must include its repository-relative path and line when available. Mark changed nodes with `CHANGED` and explain the behavioral difference and reason, not merely that a file changed. Mark supporting evidence with `VERIFIED`. When static mapping omits protocol or dynamic dispatch, stitch in the continuation only after confirming it from source and label it `SOURCE-RESOLVED DYNAMIC BOUNDARY` so the user can distinguish map output from inspected runtime wiring.

Do not force a graph into a handoff when one sentence with a clickable `path:line` communicates the change more clearly.

#### Working With Existing Drift

The user request defines the scope of remediation. A large fault count is an architectural baseline, not authorization to fix unrelated code.

- If the user requests one change, do not expand into unrelated fault remediation.
- If the user explicitly requests a broader refactor, particular fault families, or zero faults, treat that broader target as authorized scope.
- Satisfy faults by improving code under the current policy. Do not weaken selection, thresholds, exceptions, or custom rules unless the user explicitly requests a policy change.
- Before moving or splitting behavior, map the affected call flow and run the existing tests.
- When coverage around changed behavior is weak or unknown, add focused characterization tests before refactoring.
- Preserve behavior first and improve structure in verifiable slices.
- Distinguish pre-existing faults from regressions introduced by the current work.

For an explicitly authorized broad refactor, capture the baseline, map affected flows, establish characterization coverage, work in coherent slices, verify each slice, and run full final verification. A request to make `fensu check` pass means fix the code under the current policy, not edit configuration until findings disappear.

#### Testing Refactors Safely

Before materially restructuring behavior, inspect the existing tests. When the affected behavior is weakly covered or its coverage is uncertain, add focused characterization tests before moving code.

Use the cheapest test that faithfully exercises the risk:

- Unit tests for isolated decisions, transformations, and error handling.
- Integration tests for storage, messaging, process, and adapter boundaries.
- End-to-end tests for user-visible commands and workflows.
- Real local dependencies when they are deterministic and reasonably inexpensive.

Prefer faithful local infrastructure over mocks when behavior depends on the real system. Useful options include PostgreSQL, Redis, Kafka or Redpanda, RabbitMQ, NATS, MinIO, OpenSearch, and similar services available through testcontainers.

Before using testcontainers, check whether a functioning container runtime is available. Prefer `docker info`; if Docker is unavailable, check `podman info` and whether a compatible Docker API socket is configured. Finding the executable alone is not enough: verify the runtime can actually start containers. When a functioning runtime is available, testcontainers is an appropriate default for integration behavior that mocks cannot faithfully represent. Record the container-runtime requirement in the test documentation or final change summary.

Use SQLite or DuckDB when they faithfully represent the tested contract. Do not use SQLite as evidence for PostgreSQL-specific SQL, transactions, locking, concurrency, extensions, or type behavior.

Tests requiring real remote credentials or services such as external APIs or data warehouses remain a user and project decision.

When concurrency, retries, duplicate delivery, locking, or shared mutable state are real risks, add deterministic race-oriented tests where practical. Force relevant interleavings with barriers, events, controlled workers, or transactional locks rather than relying on sleeps. Assert atomicity, idempotency, ordering, uniqueness, and retry behavior as appropriate.

Do not duplicate every assertion at unit, integration, and end-to-end levels. Each layer should prove a boundary that cheaper tests cannot prove faithfully.

#### Test Execution And Isolation

Use the repository's established verification commands first. When pytest-xdist is installed and the relevant suite supports parallel execution, prefer:

```bash
pytest -n auto
```

Write new tests so they can execute independently whenever practical:

- Use unique temporary paths, databases, schemas, ports, and resource names.
- Do not depend on test execution order.
- Isolate environment changes with fixtures such as monkeypatch.
- Avoid shared process-global mutation.
- Give each worker independent external state where concurrent access would alter the result.
- Make cleanup safe after both success and failure.

When some tests genuinely require sequential execution, separate them from the parallel-safe suite. Run independent batches concurrently only when they do not share mutable resources. Otherwise run the required batches in sequence, while still using xdist inside each parallel-safe batch.

If failures suggest broken isolation, rerun the failing tests sequentially and then rerun the relevant suite sequentially. A sequential pass does not make the problem acceptable: identify and correct the shared state, ordering dependency, port collision, database collision, or timing assumption where reasonable.

#### Repository Structure

Only structures established by this repository's active core rules are shown. Omitted structures are not implied.

##### Runtime

Leaf domain:

```text
src/sqlbuild/
└── <domain>/
    ├── main/
    ├── _helpers/
    ├── classes/
    ├── models.py
    ├── types.py
    ├── constants.py
    └── exceptions.py
```

Branch domain:

```text
src/sqlbuild/
└── <domain>/
    └── <subdomain>/
        ├── main/
        ├── _helpers/
        ├── classes/
        ├── models.py
        ├── types.py
        ├── constants.py
        └── exceptions.py
```

##### Domain Shape

Enforced by FFR306: Domains may be leaves with role content directly beneath `<domain>/`, or branches containing named subdomains. Do not mix the two shapes.

Advisory: For a singleton capability, prefer a leaf instead of creating a placeholder `core` subdomain.

Advisory: Promote a leaf to a branch only when multiple real capabilities exist.

Enforced by FFR309: Every leaf domain or subdomain must contain a direct `main/` boundary with at least one non-`__init__.py` Python entry module. Branch-domain parents do not need their own `main/`; their leaf subdomains do.

Advisory: Do not add placeholder `main/` packages. If a package owns only passive models, types, constants, exceptions, or classes, move them into the closest domain or subdomain whose `main/` behavior owns and uses them.

Enforced by FFR204: Generic package names are banned: `base`, `common`, `helpers`, `lib`, `misc`, `shared`, `util`, `utils`. Name the business domain or technical capability owner instead.

##### Role Containers

###### `_helpers/`: Flat Or Grouped

Enforced by FFR301: Each `_helpers/` container has an effective module limit; its configured role base is 10.

```text
_helpers/
├── first_helper.py
└── second_helper.py
```

Enforced by FFR301: Alternatively, group every module:

```text
_helpers/
├── reading/
│   └── read_helper.py
└── writing/
    └── write_helper.py
```

###### `main/`: Flat Or Grouped

Enforced by FFR302: Each `main/` container has an effective module limit; its configured role base is 20.

```text
main/
├── first_entry.py
└── second_entry.py
```

Enforced by FFR302: Alternatively, group every module:

```text
main/
├── reading/
│   └── read_entry.py
└── writing/
    └── write_entry.py
```

Enforced by FFR301 and FFR302: Every container holds direct Python modules or Python-containing buckets, never both. Empty and asset-only directories do not count as buckets.

Enforced by FFR301 and FFR302: Configured base `max_role_depth` is 1. Role tables and matching path overrides can provide the effective per-path value.

Enforced by FFR301 and FFR302: Runtime role names are banned as buckets: `main`, `_helpers`, `classes`, `models`, `types`, `constants`, and `exceptions`.

Enforced by FFR204: Generic bucket names receive one ownership fault rather than a second container-layout fault.

Enforced by FFR303: Fixed role filenames such as `models.py`, `types.py`, `constants.py`, and `exceptions.py` are sibling roles and must never be nested beneath `_helpers/`.

Enforced by FFR301, FFR302, and FFR401: Every non-`__init__.py` module whose first structural role is `main` is an entry module, including grouped main modules. Entry shape and container depth are orthogonal, so an over-depth main path may independently receive both layout and entry-shape diagnostics. A `main` bucket below another role is not an entry boundary.

##### Role Examples

###### `main/read_invoice.py`

Enforced by FFR401: Expose exactly one public entry function and keep phase work in _helpers/. Use up to two private functions only when entry-specific glue is genuinely needed:

```python
from sqlbuild.invoices._helpers.loading import load_invoice
from sqlbuild.invoices._helpers.normalization import normalize_invoice
from sqlbuild.invoices.models import Invoice

def read_invoice(invoice_id: str) -> Invoice:
    loaded: Invoice = load_invoice(invoice_id)
    return normalize_invoice(loaded)
```

###### `models.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Invoice:
    identifier: str
    total_cents: int
```

Enforced by FFR001: When Pydantic is already in use, its structured models belong in the same role:

```python
from pydantic import BaseModel

class InvoiceQuery(BaseModel):
    customer_id: str
    include_paid: bool = False
```

###### `_helpers/normalization.py`

Enforced by FFR503: Private constants and support dataclasses precede helper functions:

```python
from dataclasses import dataclass

_DEFAULT_CURRENCY: str = "USD"

@dataclass(frozen=True, slots=True)
class _NormalizedAmount:
    cents: int
    currency: str

def normalize_amount(cents: int) -> _NormalizedAmount:
    return _NormalizedAmount(cents=max(cents, 0), currency=_DEFAULT_CURRENCY)
```

###### `classes/invoice_repository.py`

Enforced by FFR501: Each module under `classes/` defines exactly one top-level class:

```python
from sqlbuild.invoices.models import Invoice

class InvoiceRepository:
    def __init__(self, invoices: dict[str, Invoice]) -> None:
        self._invoices = invoices

    def read(self, invoice_id: str) -> Invoice:
        return self._invoices[invoice_id]
```

###### `types.py`

```python
from enum import StrEnum
from typing import NewType, TypeAlias

InvoiceId = NewType("InvoiceId", str)
InvoiceLine: TypeAlias = tuple[str, int]

class InvoiceState(StrEnum):
    DRAFT = "draft"
    PAID = "paid"
```

###### `constants.py`

```python
DEFAULT_PAGE_SIZE: int = 100
MAX_RETRY_ATTEMPTS: int = 3
```

###### `exceptions.py`

```python
class InvoiceNotFoundError(LookupError):
    """Raised when an invoice identifier is unknown."""
```

##### Tests

```text
tests/
└── <scope>/
    └── src/sqlbuild/<domain>[/<subdomain>]/
        ├── _test_types.py
        └── test_feature.py
```

Tooling-backed tests mirror under `tests/<scope>/scripts/<area>/`.

`_test_types.py`:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ReadInvoiceTestCase:
    description: str
    invoice_id: str
    expected_identifier: str
```

`test_feature.py`:

```python
import pytest

from sqlbuild.invoices.main.read_invoice import read_invoice
from sqlbuild.invoices.models import Invoice
from tests.unit.src.sqlbuild.invoices._test_types import ReadInvoiceTestCase

@pytest.mark.parametrize(
    "test_case",
    [
        ReadInvoiceTestCase(
            description="returns the requested invoice",
            invoice_id="invoice-1",
            expected_identifier="invoice-1",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_invoice_id_when_reading_invoice_then_returns_expected_invoice(
    test_case: ReadInvoiceTestCase,
) -> None:
    result: Invoice = read_invoice(test_case.invoice_id)

    assert result.identifier == test_case.expected_identifier
```

##### Tooling

Enforced by FFR705: Tool packages use the canonical role directories and files shown below.

```text
scripts/
├── run_tool.py
└── <tool>/
    ├── main/
    ├── _helpers/
    ├── classes/
    ├── rules/
    ├── models.py
    ├── types.py
    ├── constants.py
    └── exceptions.py
```

#### Effective Project Configuration

This is the loaded effective configuration, not a template. Lists and mappings are rendered deterministically; path-threshold declarations retain declaration order because that order breaks equally specific matches.

- Configuration source: "fensu.toml"
- Project root from installation root: "."
- Installation root: "."
- Current skill identity: "fensu-sqlbuild"
- Analyzer: `python`
- Complete loaded catalogue size: 139

##### Scopes

- Product roots: ["src/sqlbuild"]
- Test roots: ["tests"]
- Tooling roots: ["scripts"]

- Generated source patterns: []

- UI-kit root: null

- shadcn config: null
- OpenAPI document: null

##### Configured Rule Selectors

- Blocking selectors (`select`): ["FF", "XSB"]
- Warning selectors (`warn`): []
- Ignore selectors (`ignore`): []

##### Resolved Rule Sets

- Blocking rule codes: ["FFA001", "FFA002", "FFA101", "FFA102", "FFA103", "FFH001", "FFH002", "FFH003", "FFH004", "FFH005", "FFH006", "FFH007", "FFH008", "FFH009", "FFL001", "FFL002", "FFL101", "FFL102", "FFL103", "FFL104", "FFL105", "FFL110", "FFL301", "FFN001", "FFN002", "FFN003", "FFN004", "FFR001", "FFR002", "FFR003", "FFR004", "FFR101", "FFR102", "FFR103", "FFR104", "FFR201", "FFR202", "FFR203", "FFR204", "FFR205", "FFR301", "FFR302", "FFR303", "FFR304", "FFR305", "FFR306", "FFR307", "FFR308", "FFR309", "FFR401", "FFR402", "FFR403", "FFR404", "FFR405", "FFR406", "FFR501", "FFR502", "FFR503", "FFR504", "FFR601", "FFR701", "FFR702", "FFR703", "FFR704", "FFR705", "FFR706", "FFR707", "FFS001", "FFS002", "FFS003", "FFS010", "FFS011", "FFS101", "FFS110", "FFS120", "FFS130", "FFS131", "FFS201", "FFT001", "FFT002", "FFT003", "FFT004", "FFT005", "FFT006", "FFT007", "FFT008", "FFT101", "FFT102", "FFT103", "FFT104", "FFT105", "FFT106", "FFT201", "FFT202", "FFT203", "FFT204", "FFT205", "FFT301", "FFT302", "FFT401", "FFT402", "FFT403", "FFT404", "FFT405", "FFT406", "FFT407", "FFT408", "FFT411", "FFT412", "FFT413", "FFT414", "XSB002", "XSB003", "XSB023", "XSB024", "XSB025", "XSB031", "XSB032", "XSB037", "XSB038", "XSB041", "XSB042", "XSB045", "XSB051", "XSB052", "XSB053", "XSB054", "XSB056", "XSB057", "XSB058", "XSB061", "XSB062", "XSB066", "XSB067", "XSB068", "XSB069", "XSB070", "XSB071"]
- Warning rule codes: []
- Ignored matched rule codes: []

Normal work must satisfy blocking policy. Warnings are review signals, not scope authorization. Run `fensu check --warn` after substantial changes when practical, and never delete code or change architecture solely because of an advisory warning without verifying the actual contract.

##### Custom Rule Sources

- `rule_paths`: []
- `rule_modules`: ["scripts.fensu_policy.rules.adapter_ownership", "scripts.fensu_policy.rules.canonical_operations", "scripts.fensu_policy.rules.execution_observability", "scripts.fensu_policy.rules.module_boundaries", "scripts.fensu_policy.rules.orchestration_dataflow", "scripts.fensu_policy.rules.source_hygiene"]

- `rule_packs`: []

##### Cache And Evaluation

- Cache enabled: `true`
- Cache requires cacheable rules: `true`
- Evaluation include boundaries: []
- Evaluation exclude boundaries: ["tests/e2e/fixtures/**"]

##### Effective Global Thresholds

- `max_api_exports` = 3
- `max_api_lines` = 200
- `max_arguments` = 10
- `max_component_script_lines` = 250
- `max_distinct_calls` = 20
- `max_file_lines` = 2000
- `max_helpers_container_modules` = 10
- `max_imported_bindings` = 20
- `max_locals` = 20
- `max_main_container_modules` = 20
- `max_positional_args` = 1
- `max_public_exports` = 20
- `max_resource_families` = 1
- `max_role_depth` = 1
- `max_route_script_lines` = 200
- `max_script_entrypoint_lines` = 80
- `max_state_cells` = 15
- `max_state_functions` = 15
- `max_state_lines` = 300
- `max_state_public_members` = 20
- `max_statements` = 40
- `max_statements_global` = 70
- `max_total_runes` = 20
- `min_custom_rule_test_cases` = 1
- `min_shared_domain_prefix_packages` = 2

##### Configured Role Threshold Overrides

- None.

##### Configured Path Threshold Overrides

- Match basis: target-relative analyzer paths; reported repository paths use the same paths for this target.

- None.

##### Effective Naming Contracts

- "as_*" = "returns-value"
- "can_*" = "returns-bool"
- "enforce_*" = "no-return"
- "get_*" = "returns-value"
- "has_*" = "returns-bool"
- "is_*" = "returns-bool"
- "iter_*" = "returns-iterator"
- "supports_*" = "returns-bool"
- "to_*" = "returns-value"
- "validate_*" = "no-return"

##### Configured Rule Exceptions

- Rule "FFL101"; path="scripts/fensu_policy/rules/adapter_ownership.py"; scope="file-level"; reason="Fensu does not classify tooling rules/ as a role for sibling _helpers imports, despite FFR704 requiring that layout."
- Rule "FFL101"; path="scripts/fensu_policy/rules/canonical_operations.py"; scope="file-level"; reason="Fensu does not classify tooling rules/ as a role for sibling _helpers imports, despite FFR704 requiring that layout."
- Rule "FFL101"; path="scripts/fensu_policy/rules/execution_observability.py"; scope="file-level"; reason="Fensu does not classify tooling rules/ as a role for sibling _helpers imports, despite FFR704 requiring that layout."
- Rule "FFL101"; path="scripts/fensu_policy/rules/module_boundaries.py"; scope="file-level"; reason="Fensu does not classify tooling rules/ as a role for sibling _helpers imports, despite FFR704 requiring that layout."
- Rule "FFL101"; path="scripts/fensu_policy/rules/orchestration_dataflow.py"; scope="file-level"; reason="Fensu does not classify tooling rules/ as a role for sibling _helpers imports, despite FFR704 requiring that layout."
- Rule "FFL102"; path="src/sqlbuild/lint/_helpers/native.py"; scope="file-level"; reason="The lint layer reuses the compiler's MODEL() header parser; the compiler exposes no public facade for it."
- Rule "FFR307"; path="src/sqlbuild/rules/testing.py"; scope="file-level"; reason="sqlbuild.rules.testing is the documented public custom-rule harness module."
- Rule "FFR309"; path="src/sqlbuild/adapters/bigquery/__init__.py"; scope="file-level"; reason="The BigQuery backend intentionally owns behavior through its adapter class rather than function entrypoints."
- Rule "FFR309"; path="src/sqlbuild/adapters/databricks/constants.py"; scope="file-level"; reason="The Databricks backend intentionally owns behavior through its adapter class rather than function entrypoints."
- Rule "FFR309"; path="src/sqlbuild/adapters/duckdb/__init__.py"; scope="file-level"; reason="The DuckDB backend intentionally owns behavior through its adapter class rather than function entrypoints."
- Rule "FFR309"; path="src/sqlbuild/adapters/motherduck/__init__.py"; scope="file-level"; reason="The MotherDuck backend intentionally owns behavior through its adapter class rather than function entrypoints."
- Rule "FFR309"; path="src/sqlbuild/adapters/postgres/__init__.py"; scope="file-level"; reason="The Postgres backend intentionally owns behavior through its adapter class rather than function entrypoints."
- Rule "FFR309"; path="src/sqlbuild/adapters/snowflake/__init__.py"; scope="file-level"; reason="The Snowflake backend intentionally owns behavior through its adapter class rather than function entrypoints."
- Rule "FFR309"; path="src/sqlbuild/adapters/sqlserver/__init__.py"; scope="file-level"; reason="The SQL Server backend intentionally owns behavior through its adapter class rather than function entrypoints."
- Rule "FFR309"; path="src/sqlbuild/rules/__init__.py"; scope="file-level"; reason="The Rules package is the documented custom-rule authoring API, not an internal runtime leaf."
- Rule "FFR402"; path="src/sqlbuild/integrations/dagster/__init__.py"; scope="file-level"; reason="These imports preserve Dagster's documented external package-root APIs."
- Rule "FFR402"; path="src/sqlbuild/integrations/rivers/__init__.py"; scope="file-level"; reason="These imports preserve Rivers' documented external package-root APIs."
- Rule "FFR402"; path="src/sqlbuild/rules/__init__.py"; scope="file-level"; reason="These imports provide the documented sqlbuild.rules package-root authoring API."
- Rule "FFR403"; path="src/sqlbuild/rules/testing.py"; scope="file-level"; reason="This deliberate public shim keeps test-harness internals outside the stable authoring API."
- Rule "FFR601"; path="src/sqlbuild/adapter/contract/classes/base_adapter.py"; scope="file-level"; reason="The adapter contract intentionally keeps its overrideable methods on one class."
- Rule "FFR601"; path="src/sqlbuild/adapter/contract/classes/duckdb_backed_adapter.py"; scope="file-level"; reason="The shared DuckDB-backed adapter intentionally keeps overrideable methods on one class."
- Rule "FFR601"; path="src/sqlbuild/adapters/bigquery/classes/bigquery_adapter.py"; scope="file-level"; reason="The BigQuery adapter intentionally keeps overrideable backend behavior on one class."
- Rule "FFR601"; path="src/sqlbuild/adapters/databricks/classes/databricks_adapter.py"; scope="file-level"; reason="The Databricks adapter intentionally keeps overrideable backend behavior on one class."
- Rule "FFR601"; path="src/sqlbuild/adapters/postgres/classes/postgres_adapter.py"; scope="file-level"; reason="The Postgres adapter intentionally keeps overrideable backend behavior on one class."
- Rule "FFR601"; path="src/sqlbuild/adapters/snowflake/classes/snowflake_adapter.py"; scope="file-level"; reason="The Snowflake adapter intentionally keeps overrideable backend behavior on one class."
- Rule "FFR601"; path="src/sqlbuild/adapters/sqlserver/classes/sqlserver_adapter.py"; scope="file-level"; reason="The SQL Server adapter intentionally keeps overrideable backend behavior on one class."
- Rule "FFR601"; path="src/sqlbuild/executor/run/_helpers/materializations/microbatch.py"; scope="file-level"; reason="Microbatch execution is one ordered failure-sensitive lifecycle; splitting reconciliation, DML, completion publication, and aggregate gates would hide the required phase ordering across module boundaries."
- Rule "FFR601"; path="src/sqlbuild/virtual/executor/_helpers/build.py"; scope="file-level"; reason="Virtual build orchestration intentionally keeps resolution, immutable physical-version execution, lease fencing, and state publication in one auditable lifecycle module."
- Rule "FFR601"; path="src/sqlbuild/virtual/state/classes/postgres.py"; scope="file-level"; reason="The Postgres state backend intentionally keeps its transactional storage contract on one class."
- Rule "FFS120"; path="scripts/cli_preview/_helpers/workflow.py"; scope=["_run_process._forward_signal"]; reason="This callback preserves signal.signal's required positional handler protocol."
- Rule "FFS120"; path="src/sqlbuild/adapter/contract/classes/observed_connection.py"; scope=["ObservedConnection.execute", "ObservedConnection.executemany"]; reason="This proxy preserves DuckDB's positional connection execution protocol."
- Rule "FFS120"; path="src/sqlbuild/adapter/contract/classes/observed_cursor.py"; scope=["ObservedCursor.execute", "ObservedCursor.executemany"]; reason="This proxy preserves the external DB-API cursor positional execution protocol."
- Rule "FFS120"; path="src/sqlbuild/adapters/snowflake/classes/snowflake_connection.py"; scope=["_SnowflakeConnection.execute"]; reason="This wrapper preserves the connection.execute(sql) protocol shared by adapter helpers."
- Rule "FFS120"; path="src/sqlbuild/adapters/snowflake/classes/snowflake_cursor.py"; scope=["_SnowflakeCursor.execute", "_SnowflakeCursor.executemany"]; reason="This proxy preserves Snowflake's DB-API cursor positional execution protocol."
- Rule "FFS120"; path="src/sqlbuild/assets.py"; scope=["asset"]; reason="Bare @asset is evaluated by Python as asset(function), requiring positional function calling."
- Rule "FFS120"; path="src/sqlbuild/hooks.py"; scope=["hook"]; reason="Bare @hook is evaluated by Python as hook(function), requiring positional function calling."
- Rule "FFS120"; path="src/sqlbuild/integrations/dagster/classes/sqlbuild_cli_resource.py"; scope=["SqlBuildCliResource.cli"]; reason="This method follows Dagster's public cli(args, *, ...) positional convention."
- Rule "FFS120"; path="src/sqlbuild/integrations/dbt/_helpers/profile/render.py"; scope=["_render_string.env_var", "_render_string.var"]; reason="These Jinja globals preserve dbt's external positional call protocol."
- Rule "FFS120"; path="src/sqlbuild/integrations/dlt/classes/sqlbuild_dlt_progress_collector.py"; scope=["SqlbuildDltProgressCollector.on_end_trace", "SqlbuildDltProgressCollector.on_end_trace_step", "SqlbuildDltProgressCollector.on_start_trace", "SqlbuildDltProgressCollector.on_start_trace_step", "SqlbuildDltProgressCollector.update"]; reason="These collector methods preserve dlt's external positional progress protocol."
- Rule "FFS120"; path="src/sqlbuild/loaders.py"; scope=["loader"]; reason="Bare @loader is evaluated by Python as loader(function), requiring positional function calling."
- Rule "FFS120"; path="src/sqlbuild/sinks.py"; scope=["command_output_sink", "lifecycle_event_sink"]; reason="Bare sink decorators are evaluated by Python as decorator(function), requiring positional function calling."
- Rule "FFS120"; path="src/sqlbuild/tasks.py"; scope=["task"]; reason="Bare @task is evaluated by Python as task(function), requiring positional function calling."

##### Configured Path-Scoped Rule Ignores

- None.

#### Custom Rule Authority

Never create, configure, enable, disable, or materially change a custom rule unless the user explicitly requested it or explicitly approved your proposal.

An explicit request such as "create a custom rule preventing this" or "make Fensu enforce this convention" is already sufficient authorization. Do not ask for a redundant second confirmation.

When work reveals a recurring enforceable convention:

1. Complete the requested change under the existing policy.
2. Explain the recurring pattern or risk.
3. Suggest a possible custom rule and its intended boundaries.
4. Wait for explicit user approval before implementing it.

Never add or change policy merely because the current task exposed a possible convention, similar code appears more than once, a stricter architecture seems preferable, a core rule is inconvenient, or changing policy would make `fensu check` pass. Fix code under current policy rather than weakening or rewriting policy to avoid the work.

#### RuleContext Public API

Approved custom rules receive `ctx: RuleContext`. Import authoring APIs only from the top-level `fensu` package. The five public analysis zones are:

- `ctx.facts`: `annotations()`, `assignment_references()`, `class_declarations()`, `comments()`, `comparisons()`, `complex_comprehensions()`, `dataclasses()`, `function_conditionals()`, `functions()`, `function_contracts()`, `hygiene()`, `meaningful_returns(name_patterns=())`, `local_call_edges()`, `module_declarations()`, `named_calls()`, `outer_state_mutations()`, `parameter_mutations()`, `parameter_mutation_occurrences()`, `project_calls()`, `project_functions()`, `references()`, `test_functions()`, `top_level_definition_conditionals()`, and `test_module()`.
- `ctx.text`: `source`, `line(line_number)`, and `slice(source_range)`.
- `ctx.syntax`: `handles(kind=None)`, `kind(handle)`, and `range(handle)`.
- `ctx.relations`: `parent(handle)`, `children(handle)`, and `ancestors(handle)`.
- `ctx.project`: dependency-recording cross-file and filesystem queries. Use `analysis(requester=ctx.path, path=path)`, `dataclasses(requester=ctx.path, path=path)`, `directory_entries(requester=ctx.path, path=path)`, `entrypoint_modules(requester=ctx.path)`, `module_function(requester=ctx.path, module_name=name, function_name=name)`, `python_anchor(requester=ctx.path, path=path)`, `exists(requester=ctx.path, path=path)`, `is_dir(requester=ctx.path, path=path)`, `is_file(requester=ctx.path, path=path)`, and `glob(requester=ctx.path, path=path, pattern=pattern, recursive=False)`. Inspect recorded observations with `dependencies()` or `dependencies_for(requester=ctx.path)`.

Position and ownership helpers: `ctx.path`, `ctx.repo_root`, `ctx.source`, `relative_parts()`, `repo_relative_parts()`, `scope_root()`, `scope_roots(scope), test_scopes()`, `module_parts()`, `scope()`, `role_of()`, `in_role(role)`, `is_entry_module()`, `is_main_module()`, `domain()`, and `subdomain()`. `role_of()` describes the current file here; use project facts rather than assuming arbitrary paths share its position.

AST helpers: `nodes(node_type)`, `call_name(node)`, `base_name(node)`, `top_level_functions(module)`, `non_docstring_body(module)`, `distinct_callees(fn)`, `assigned_locals(fn)`, `complex_comprehensions()`, `parameter_names(fn)`, and `inside_loop(node)`.

Policy helpers: `threshold(name=..., path=None)` and `contracts()`. Fault constructors: `fault(node=..., message=None, remediation=None)`, `fault_at(location=..., message=None, remediation=None)`, `fault_for(path=..., line=..., column=..., message=None, remediation=None)`, and `path_fault(path=None, message=None, remediation=None)`.

#### Approved Custom Rule Authoring Lookup

When authoring an approved custom rule, use the generated RuleContext summary first. If exact signatures or returned public models are unclear, inspect existing repository custom rules, then the public Fensu exports and type definitions from the project's active Python environment. This targets the installed Fensu version rather than remembered or generic API knowledge.

It is acceptable to locate the active installation through `fensu.__file__` or the project's `.venv` and read definitions behind public exports such as `RuleContext`, semantic fact protocols, project-query protocols, and public result models. Consult public documentation after those installed public definitions. Read private implementation only to diagnose a suspected Fensu defect.

Only import authoring APIs from top-level `fensu`. Reading installed implementation for understanding does not make private `_helpers/` modules a supported dependency. Do not import from or couple custom rules to Fensu's private modules.

#### Testing Custom Rules

Test approved custom rules through Fensu's real discovery and evaluation pipeline. Import the harness only from the top-level package and pass the decorated rule function as `rule=`. `RuleFile` support sources are available to `ctx.project` but are not direct evaluation targets.
The effective minimum is `1` statically declared `RuleCase` value(s) per configured custom rule, including rules not selected for blocking or warning evaluation. A value of `0` disables this requirement.

When FFT413 is active, do not parametrize directly with `RuleCase`. Parametrize with a dataclass imported from local `_test_types.py`, then construct `RuleCase` inside the test. A pair of apparently conflicting diagnostics should only be described as a policy gap after checking whether an adapter or wrapper pattern satisfies both rules.

`_test_types.py`:

```python
from dataclasses import dataclass

from fensu import RuleFile


@dataclass(frozen=True)
class CustomRuleTestCase:
    description: str
    path: str
    source: str
    expected_fault_count: int
    files: tuple[RuleFile, ...] = ()
    scope: str = "root"
    scope_root: str | None = None
```

`test_client_ownership.py`:

```python
import pytest

from fensu import RuleCase, RuleResult, evaluate_rule
from scripts.fensu_policy.rules.client_ownership import no_global_client
from tests.unit.scripts.fensu_policy.rules._test_types import CustomRuleTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CustomRuleTestCase(
            description="reports a forbidden global client",
            path="package/example.py",
            source="GLOBAL_CLIENT = build_client()\n",
            expected_fault_count=1,
        ),
        CustomRuleTestCase(
            description="allows a function-local client",
            path="package/example.py",
            source="def run() -> None:\n    client = build_client()\n",
            expected_fault_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_source_when_checking_rule_then_returns_expected_faults(
    test_case: CustomRuleTestCase,
) -> None:
    result: RuleResult = evaluate_rule(
        rule=no_global_client,
        test_case=RuleCase(
            description=test_case.description,
            path=test_case.path,
            source=test_case.source,
            expected_fault_count=test_case.expected_fault_count,
            files=test_case.files,
            scope=test_case.scope,
            scope_root=test_case.scope_root,
        ),
    )

    assert result.fault_count == test_case.expected_fault_count
```

Cover a failing example, a passing example, near misses, scope exclusions, deterministic ordering, and cross-file invalidation when the rule uses `ctx.project`. Verify cold and warm cache behavior. Dynamic case generators cannot prove the configured static minimum.

#### Cacheability

Configured cache enabled: `true`. Configured `require_cacheable`: `true`.

Because `require_cacheable = true`, every selected custom rule must satisfy the cacheability contract.

Cacheable custom rules use only allowlisted pure imports; never call `open`, `eval`, `exec`, `input`, or `__import__`; perform no direct filesystem access; make every cross-file query through `ctx.project` with `requester=ctx.path`; and emit deterministic diagnostics. Configure concrete `rule_modules`. Keep decorated declarations in `rules/`, shared implementation in the sibling `_helpers/`, and constants in the policy package's sibling `constants.py`. A configured rule package does not mean helpers belong beneath `rules/`; that layout violates FFR704.

Verify cache behavior with separate commands so a deliberate baseline fault does not prevent later observations:

```bash
fensu check --no-cache
fensu check --cache-stats
fensu check --cache-stats
```

For a cacheable ruleset, the second cached run must report all hits, zero misses, `non_cacheable=0`, and diagnostics byte-identical to the uncached run.

#### Blocking Rules

##### FFA001: parameter-annotation

Family: `annotations`
Analyzers: `python`

function parameters must define type annotations

Remediation: Annotate every parameter with the value type accepted by the function.

##### FFA002: return-annotation

Family: `annotations`
Analyzers: `python`

functions must define return type annotations

Remediation: Declare the returned value type, using None when the function returns no value.

##### FFA101: module-variable-annotation

Family: `annotations`
Analyzers: `python`

module-level variables must define type annotations

Remediation: Add an explicit annotation to the first module-level assignment.

##### FFA102: class-attribute-annotation

Family: `annotations`
Analyzers: `python`

class attributes must define type annotations

Remediation: Annotate the class attribute where it is first assigned.

##### FFA103: local-variable-annotation

Family: `annotations`
Analyzers: `python`

local variables must define type annotations on first binding unless assigned a scalar literal

Remediation: Annotate first bindings whose type is not evident from a number, string, bool, bytes, or f-string literal.

##### FFH001: single-line-docstrings

Family: `hygiene`
Analyzers: `python`

docstrings must be a single line; move extended explanation into docs or tests

Remediation: Keep one concise summary line and move extended rationale into documentation or tests.

##### FFH002: no-standalone-comments

Family: `hygiene`
Analyzers: `python`

standalone comments are not allowed; prefer clear names or docs/tests

Remediation: Replace the comment with clearer names or move lasting explanation into documentation or tests. Tooling directives beginning with these prefixes are allowed: #!, # -*-, # coding:, # noqa, # type:, # pyright:, # pylint:, # pragma:.

Constraints:

- Allowed standalone comment prefixes: `#!`, `# -*-`, `# coding:`, `# noqa`, `# type:`, `# pyright:`, `# pylint:`, `# pragma:`

##### FFH003: no-raw-builtin-raise

Family: `hygiene`
Analyzers: `python`

runtime code must raise structured errors instead of raw built-in exceptions

Remediation: Raise a domain-specific exception from exceptions.py with a stable actionable message.

##### FFH004: no-assert-in-runtime

Family: `hygiene`
Analyzers: `python`

runtime code must not use assert for invariants; raise a structured error

Remediation: Replace assert with an explicit guard that raises a domain-specific exception.

##### FFH005: no-swallowed-exception-probe

Family: `hygiene`
Analyzers: `python`

runtime code must not swallow broad exceptions as existence probe answers

Remediation: Use an explicit metadata or existence check, or catch only the expected exception and preserve failures.

##### FFH006: no-complex-comprehensions-in-tooling

Family: `hygiene`
Analyzers: `python`

nested or multi-generator comprehensions hide control flow and data shapes

Remediation: Extract a named helper when the transformation has a coherent purpose. For one-off local logic, use simple statements with named intermediate values instead of nested comprehension control flow.

##### FFH007: no-unnamed-string-decisions

Family: `hygiene`
Analyzers: `python`

string literals must not directly control comparison behavior

Remediation: Name the decision value in constants.py or compare against an enum member so the branch expresses the concept it represents.

##### FFH008: no-magic-numeric-comparisons

Family: `hygiene`
Analyzers: `python`

non-canonical numeric literals must not directly control comparisons

Remediation: Name the threshold or sentinel in constants.py and compare against that name; only -1, 0, and 1 are self-explanatory comparison values.

##### FFH009: no-import-time-side-effects

Family: `hygiene`
Analyzers: `python`

runtime and tooling modules must not execute standalone calls during import

Remediation: Move the operation into an explicit function or assign a pure constructor result.

##### FFL001: absolute-imports-only

Family: `layers`
Analyzers: `python`

use absolute imports; relative imports hide package boundaries

Remediation: Replace relative imports with an absolute import path.

##### FFL002: no-star-imports

Family: `layers`
Analyzers: `python`

star imports hide names from dependency-boundary analysis

Remediation: Import each required name explicitly.

##### FFL101: no-sibling-package-internals

Family: `layers`
Analyzers: `python`

subpackage code must not import sibling internals

Remediation: Publish the dependency through the owning sibling's main/ entry or role files.

##### FFL102: no-cross-package-internals

Family: `layers`
Analyzers: `python`

cross-package imports must use public surfaces, not helpers or internals

Remediation: Import from classes, models, types, constants, exceptions, or a thin main/ entry.

##### FFL103: no-internal-public-surface-imports

Family: `layers`
Analyzers: `python`

internal code must import from the owning module, not the bare package

Remediation: Import from the concrete owning module below the package surface.

Constraints:

- Subdomain paths exempt from internal public-surface imports: `rules/exemplars`

##### FFL104: no-cross-domain-private-main-imports

Family: `layers`
Analyzers: `python`

domain-private main entries may only be imported within their owning domain

Remediation: Remove the leading underscore to publish the main entry, or route the caller through a public main entry owned by the target domain.

##### FFL105: public-main-entry-external-use

Family: `layers`
Analyzers: `python`

public main entries must have an importer outside their owning domain

Remediation: Prefix the entry module filename with '_' until another domain or tooling imports it.

##### FFL110: no-cross-file-use-of-helper-private-class

Family: `layers`
Analyzers: `python`

helper-private classes are file-local details; move shared classes to classes/

Remediation: If another module needs this class, move it to the owning classes/ package.

##### FFL301: no-runtime-imports-from-tooling

Family: `layers`
Analyzers: `python`

runtime code must not import from tooling modules

Remediation: Move reusable logic into the runtime package or keep the dependency inside tooling.

Effective configuration:

- `tooling`: `scripts`

##### FFN001: validator-must-not-return

Family: `naming`
Analyzers: `python`

functions under no-return naming contracts must not return values

Remediation: Remove the meaningful return and raise on invalid input, or rename a value-producing function as a query such as is_valid or get_validation_result.

Naming contracts:

- `enforce_*`: `no-return`
- `validate_*`: `no-return`

##### FFN002: predicate-must-return-bool

Family: `naming`
Analyzers: `python`

predicate names must declare an ordinary boolean result

Remediation: Return bool (or TypeGuard/TypeIs), or rename the function to describe the value it returns, such as read_status or current_status.

Naming contracts:

- `can_*`: `returns-bool`
- `has_*`: `returns-bool`
- `is_*`: `returns-bool`
- `supports_*`: `returns-bool`

##### FFN003: value-name-must-return-value

Family: `naming`
Analyzers: `python`

value-producing names must not declare a no-value result

Remediation: Return the queried or converted value, or rename the function to describe its side effect, such as initialize_cache or export_json.

Naming contracts:

- `as_*`: `returns-value`
- `get_*`: `returns-value`
- `to_*`: `returns-value`

##### FFN004: iterator-name-must-produce-iterator

Family: `naming`
Analyzers: `python`

iterator names must produce an iterator or generator

Remediation: Return an iterator, generator, async iterator, or async generator; otherwise rename an eager collection function with a name such as collect_items.

Naming contracts:

- `iter_*`: `returns-iterator`

##### FFR001: models-only-models

Family: `roles`
Analyzers: `python`

models role files may contain only structured runtime models

Remediation: Keep imports and public structured models only. Accepted models are dataclasses and Pydantic BaseModel subclasses; move functions and other declarations to their owning role module.

##### FFR002: types-only-types

Family: `roles`
Analyzers: `python`

types role files may contain only type-layer declarations

Remediation: Move runtime values and functions out of types.py into their owning runtime role.

##### FFR003: constants-only-constants

Family: `roles`
Analyzers: `python`

constants role files may contain only assignments and imports

Remediation: Move functions and classes out of constants.py into their owning role module.

##### FFR004: exceptions-only-exceptions

Family: `roles`
Analyzers: `python`

exceptions role files may contain only custom exceptions

Remediation: Move non-exception declarations out of exceptions.py into their owning role.

##### FFR101: model-declaration-outside-models

Family: `roles`
Analyzers: `python`

structured runtime models must be defined in the models role

Remediation: Move the dataclass or structured model into the owning models.py file.

##### FFR102: type-declaration-outside-types

Family: `roles`
Analyzers: `python`

type-layer declarations must be defined in the types role

Remediation: Move the protocol, enum, TypedDict, or public type alias into types.py.

Constraints:

- Roles allowed to own private type declarations: `helpers`

##### FFR103: constant-outside-constants

Family: `roles`
Analyzers: `python`

public uppercase constants must be defined in the constants role

Remediation: Move the public constant into constants.py and import it from there.

##### FFR104: exception-declaration-outside-exceptions

Family: `roles`
Analyzers: `python`

custom exceptions must be defined in the exceptions role

Remediation: Move the exception class into the owning exceptions.py file.

##### FFR201: banned-generic-filename

Family: `roles`
Analyzers: `python`

generic filenames hide module ownership

Remediation: Rename the module after the domain concept or operation it owns. Forbidden module filenames: misc.py.

Constraints:

- Forbidden module filenames: `misc.py`

##### FFR202: helpers-module-name

Family: `roles`
Analyzers: `python`

use an _helpers package instead of helpers.py

Remediation: Replace helpers.py with an _helpers/ package of specifically named modules.

##### FFR203: classes-module-name

Family: `roles`
Analyzers: `python`

use a classes package instead of classes.py

Remediation: Replace classes.py with a classes/ package containing one class per module.

##### FFR204: banned-generic-package-name

Family: `roles`
Analyzers: `python`

runtime package directories must identify an owner

Remediation: Rename the package after the business domain or technical capability it owns. Forbidden package names: base, common, helpers, lib, misc, shared, util, utils. This rule owns generic bucket names; container-layout rules do not emit a duplicate fault.

Constraints:

- Forbidden package names: `base`, `common`, `helpers`, `lib`, `misc`, `shared`, `util`, `utils`

##### FFR205: helpers-classes-file-private

Family: `roles`
Analyzers: `python`

plain classes in _helpers modules must be file-private

Remediation: Prefix a file-local helper class with _, or move a shared class into classes/.

##### FFR301: helpers-package-layout

Family: `roles`
Analyzers: `python`

_helpers/ packages must use bounded flat-or-grouped containers

Remediation: Keep _helpers/ flat or group every module into bounded shallow buckets; do not mix direct Python modules and Python-containing buckets in one container. Only direct .py files other than __init__.py count toward the module limit; empty and asset-only directories do not count as buckets. Runtime role names are not valid buckets. Container depth and entry-module shape are evaluated independently.

Constraints:

- Forbidden role bucket names: `main`, `_helpers`, `helpers`, `classes`, `models`, `types`, `constants`, `exceptions`

Thresholds:

- `max_helpers_container_modules`: `10` (base value; role or path overrides may apply)
- `max_role_depth`: `1` (base value; role or path overrides may apply)

##### FFR302: main-package-layout

Family: `roles`
Analyzers: `python`

main/ packages must use bounded flat-or-grouped orchestration containers

Remediation: Keep main/ flat or group every entry into bounded shallow buckets; do not mix direct Python modules and Python-containing buckets in one container. Only direct .py files other than __init__.py count toward the module limit; empty and asset-only directories do not count as buckets. Runtime role names are not valid buckets. Container depth and entry-module shape are evaluated independently.

Constraints:

- Forbidden role bucket names: `main`, `_helpers`, `helpers`, `classes`, `models`, `types`, `constants`, `exceptions`

Thresholds:

- `max_main_container_modules`: `20` (base value; role or path overrides may apply)
- `max_role_depth`: `1` (base value; role or path overrides may apply)

##### FFR303: helpers-reserved-role-filenames

Family: `roles`
Analyzers: `python`

_helpers/ packages must not contain reserved role filenames

Remediation: Rename the helper module after its specific operation, or move role-owned declarations to the corresponding sibling models, types, constants, or exceptions role.

Constraints:

- Reserved role filenames: `models.py`, `types.py`, `constants.py`, `exceptions.py`

##### FFR304: nested-direct-modules

Family: `roles`
Analyzers: `python`

nested runtime packages may contain only role-oriented direct modules

Remediation: Move additional implementation modules under the package's _helpers/ boundary.

Constraints:

- Recognized runtime role directories: `main`, `_helpers`, `classes`, `models`, `types`, `constants`, `exceptions`
- Recognized runtime role filenames: `main.py`, `helpers.py`, `classes.py`, `models.py`, `types.py`, `constants.py`, `exceptions.py`

##### FFR305: nested-direct-subpackages

Family: `roles`
Analyzers: `python`

nested runtime packages must use explicit role boundaries

Remediation: Move feature subpackages under _helpers/ or use a supported role such as main/ or classes/.

Constraints:

- Recognized runtime role directories: `main`, `_helpers`, `classes`, `models`, `types`, `constants`, `exceptions`

##### FFR306: top-level-domain-shape

Family: `roles`
Analyzers: `python`

top-level domains must be either role leaves or subdomain branches

Remediation: Keep direct role content in a leaf domain, or move it into a named subdomain when the domain contains subdomains.

##### FFR307: top-level-direct-modules

Family: `roles`
Analyzers: `python`

top-level domains must not contain ad hoc direct modules

Remediation: Move the module under a direct role boundary or into an owning named subdomain.

Constraints:

- Recognized runtime role filenames: `main.py`, `helpers.py`, `classes.py`, `models.py`, `types.py`, `constants.py`, `exceptions.py`

##### FFR308: shared-domain-prefix

Family: `roles`
Analyzers: `python`

sibling domains must not encode one parent domain through a shared name prefix

Remediation: Create one parent domain from the shared prefix and move each remaining suffix beneath it as a named subdomain. Setting min_shared_domain_prefix_packages to 0 disables this rule.

Thresholds:

- `min_shared_domain_prefix_packages`: `2` (base value; role or path overrides may apply)

##### FFR309: leaf-main-boundary

Family: `roles`
Analyzers: `python`

leaf runtime domains and subdomains must expose meaningful behavior through main/

Remediation: Every leaf requires a direct main/ boundary with at least one non-__init__.py Python entry; branch-domain parents are exempt. Add a focused entry only when the leaf owns behavior; otherwise move passive declarations into the closest behavioral owner.

##### FFR401: entry-module-shape

Family: `roles`
Analyzers: `python`

main/ entry modules must expose one focused public function

Remediation: Every non-__init__.py module whose first structural role is main is an entry, including grouped main modules. Keep only imports, one public entry function, and at most two small private glue functions; move phase logic to _helpers/. A main bucket below another role is not an entry boundary.

Fixed limits:

- Maximum private glue functions: `2`
- Required public entry functions: `1`

##### FFR402: init-module-empty

Family: `roles`
Analyzers: `python`

nested __init__.py files must be empty or docstring-only

Remediation: Remove runtime declarations and import from the concrete owning module instead.

##### FFR403: no-reexport-shim

Family: `roles`
Analyzers: `python`

internal modules must not exist only to re-export imports

Remediation: Import the implementation module directly or expose a deliberate API through an approved public surface.

Constraints:

- Roles exempt from the pure re-export shim rule: `exceptions`

##### FFR404: no-internal-helper-exports

Family: `roles`
Analyzers: `python`

_helpers/ modules must not publish an __all__ surface

Remediation: Keep _helpers/ internal and expose public behavior through main/, classes/, models, types, constants, or exceptions.

##### FFR405: main-entry-name-collision

Family: `roles`
Analyzers: `python`

main/ cannot define a module and package with the same entry name

Remediation: Choose either the flat entry module or the same-named package and remove the competing surface.

##### FFR406: public-surface-shape

Family: `roles`
Analyzers: `python`

root package surfaces may contain only imports and one __all__ declaration

Remediation: Move runtime behavior into an owning module and keep the root __init__.py as a deliberate import surface.

##### FFR501: classes-one-class-per-module

Family: `roles`
Analyzers: `python`

classes/ modules must define exactly one top-level class

Remediation: Split additional classes into separately named modules under classes/.

##### FFR502: helpers-package-shape

Family: `roles`
Analyzers: `python`

_helpers/ packages must contain no main.py orchestration entrypoints

Remediation: Move main.py orchestration into the sibling main/ role; helper depth is enforced by FFR301.

##### FFR503: private-definition-ordering

Family: `roles`
Analyzers: `python`

private constants and dataclasses must appear before top-level functions

Remediation: Move private module declarations above the first function so readers see module state before behavior.

##### FFR504: classes-runtime-reexport

Family: `roles`
Analyzers: `python`

classes/ modules must not publicly re-export imported runtime symbols

Remediation: Import runtime symbols from their defining modules and keep each classes/ module's public surface owned by its class.

##### FFR601: source-file-line-count

Family: `roles`
Analyzers: `python`

source files must stay below the configured line limit

Remediation: Split the file by a cohesive role or concern instead of extracting arbitrary numbered fragments.

Thresholds:

- `max_file_lines`: `2000` (base value; role or path overrides may apply)

##### FFR701: tooling-entrypoint-shape

Family: `roles`
Analyzers: `python`

direct scripts must remain focused command adapters

Remediation: Keep one public main(), optional private _parse_args() and _build_parser(), and move implementation into a scripts/<tool>/main/ entry.

Constraints:

- Allowed direct-script command functions: `main`, `_parse_args`, `_build_parser`
- Allowed direct-script top-level statement kinds: `import statement`, `command function`, `nonexecuting import guard`

Fixed limits:

- Required public main functions: `1`

##### FFR702: tooling-entrypoint-delegation

Family: `roles`
Analyzers: `python`

direct scripts must delegate to an imported main/ entrypoint

Remediation: Import a typed entry function from a runtime or scripts/<tool>/main/ module and return its result from main().

Constraints:

- Roles whose imported entries may be called by direct-script main(): `main`
- Allowed local direct-script main() call targets: `_parse_args`

##### FFR703: tooling-entrypoint-line-count

Family: `roles`
Analyzers: `python`

direct scripts must stay below the configured line limit

Remediation: Move command implementation into a named tooling or runtime package.

Thresholds:

- `max_script_entrypoint_lines`: `80` (base value; role or path overrides may apply)

##### FFR704: rules-role-content

Family: `roles`
Analyzers: `python`

tooling rules/ modules may contain only decorated rule declarations

Remediation: Keep imports and @rule functions here; move supporting implementation into _helpers/, classes/, models.py, types.py, constants.py, or exceptions.py.

##### FFR705: tooling-package-layout

Family: `roles`
Analyzers: `python`

tool packages must organize implementation through explicit roles

Remediation: Use main/, _helpers/, classes/, rules/, models.py, types.py, constants.py, or exceptions.py directly beneath scripts/<tool>/.

Constraints:

- Allowed tooling role directories: `main`, `_helpers`, `classes`, `rules`
- Allowed tooling role files: `models.py`, `types.py`, `constants.py`, `exceptions.py`

##### FFR706: descriptive-rule-module-names

Family: `roles`
Analyzers: `python`

rule module filenames must describe their policy rather than repeat one rule code

Remediation: Rename the module after the policy or rule family it implements, using a name such as conditional_test_flow.py instead of fft104.py.

##### FFR707: custom-rule-test-coverage

Family: `roles`
Analyzers: `python`

configured custom rules must have statically declared public-harness cases

Remediation: Add statically visible RuleCase construction passed to evaluate_rule for each custom rule. When FFT413 is active, parametrize with a local _test_types.py dataclass and convert it to RuleCase inside the test. Setting min_custom_rule_test_cases to 0 disables this rule.

Thresholds:

- `min_custom_rule_test_cases`: `1` (base value; role or path overrides may apply)

##### FFS001: too-many-statements

Family: `shape`
Analyzers: `python`

main functions must stay phase-shaped and below the statement limit

Remediation: Extract cohesive phases into helpers that return explicit result models.

Thresholds:

- `max_statements`: `40` (base value; role or path overrides may apply)

##### FFS002: too-many-distinct-calls

Family: `shape`
Analyzers: `python`

main functions must not coordinate too many distinct callees

Remediation: Group related work into named phase helpers and keep main/ as a short ordered flow.

Thresholds:

- `max_distinct_calls`: `20` (base value; role or path overrides may apply)

##### FFS003: too-many-locals

Family: `shape`
Analyzers: `python`

main functions must not juggle too many local variables

Remediation: Let each extracted phase own its intermediates and return one structured result.

Thresholds:

- `max_locals`: `20` (base value; role or path overrides may apply)

##### FFS010: max-arguments

Family: `shape`
Analyzers: `python`

functions must stay below the configured argument limit

Remediation: Reduce the function's responsibility or group cohesive inputs into a typed model.

Thresholds:

- `max_arguments`: `10` (base value; role or path overrides may apply)

##### FFS011: max-statements-global

Family: `shape`
Analyzers: `python`

functions must stay below the global statement limit

Remediation: Split the function at a meaningful phase boundary with explicit inputs and outputs. Top-level main functions are governed by FFS001 instead.

Thresholds:

- `max_statements_global`: `70` (base value; role or path overrides may apply)

##### FFS101: meaningful-project-result-discarded

Family: `shape`
Analyzers: `python`

main orchestrators must consume meaningful project-local call results

Remediation: Assign, return, or explicitly discard the phase result with _ = call(...).

##### FFS110: default-mutation-return

Family: `shape`
Analyzers: `python`

functions that mutate parameters must return every mutated parameter

Remediation: Return each mutated parameter explicitly, or avoid parameter mutation and return a new value.

Constraints:

- Function kinds exempt from parameter-mutation enforcement: `dunder`, `setter`

##### FFS120: keyword-only-arguments

Family: `shape`
Analyzers: `python`

functions beyond the parameter threshold must be entirely keyword-only

Remediation: Insert * before the first non-receiver parameter so every call argument names its meaning. Dunder methods are exempt.

Thresholds:

- `max_positional_args`: `1` (base value; role or path overrides may apply)

##### FFS130: no-outer-state-mutation

Family: `shape`
Analyzers: `python`

functions must not mutate module-global or closure-captured state

Remediation: Pass state explicitly and return the updated value instead of mutating outer scope.

##### FFS131: no-complex-comprehensions

Family: `shape`
Analyzers: `python`

nested or multi-generator comprehensions hide control flow and data shapes

Remediation: Extract a named helper when the transformation has a coherent purpose. For one-off local logic, use simple statements with named intermediate values instead of nested comprehension control flow.

##### FFS201: mutable-result-model

Family: `shape`
Analyzers: `python`

dataclass result models must be frozen

Remediation: Declare the shared result model with @dataclass(frozen=True).

##### FFT001: test-layout

Family: `tests`
Analyzers: `python`

tests must live under a configured test root and supported scope

Remediation: Move the test beneath a configured test root and one of the configured test_scopes.

Effective configuration:

- `test_scopes`: `unit`, `integration`, `e2e`
- `tests`: `tests`

##### FFT002: test-scope

Family: `tests`
Analyzers: `python`

test scope must be one of the configured test scopes

Remediation: Move the test beneath a configured test root and one of the configured test_scopes.

Effective configuration:

- `test_scopes`: `unit`, `integration`, `e2e`
- `tests`: `tests`

##### FFT003: test-mirrored-root

Family: `tests`
Analyzers: `python`

test directories must mirror a configured runtime or tooling root

Remediation: Mirror the complete configured source or tooling path beneath the test scope.

Effective configuration:

- `roots`: `src/sqlbuild`
- `tooling`: `scripts`

##### FFT004: src-mirror-depth

Family: `tests`
Analyzers: `python`

runtime tests must include an area beneath the configured source root

Remediation: Move the test beneath the package and source area it exercises.

Effective configuration:

- `roots`: `src/sqlbuild`

##### FFT005: src-package-exists

Family: `tests`
Analyzers: `python`

runtime tests must mirror a configured source package

Remediation: Correct the mirrored package name or move the test to the package it exercises.

Effective configuration:

- `roots`: `src/sqlbuild`

##### FFT006: src-area-exists

Family: `tests`
Analyzers: `python`

runtime tests must mirror an existing source package area

Remediation: Correct the mirrored area path so it matches the runtime module location.

Effective configuration:

- `roots`: `src/sqlbuild`

##### FFT007: scripts-mirror-depth

Family: `tests`
Analyzers: `python`

tooling tests must include an area beneath the configured tooling root

Remediation: Move the test beneath the configured tooling area it exercises.

Effective configuration:

- `tooling`: `scripts`

##### FFT008: scripts-area-exists

Family: `tests`
Analyzers: `python`

tooling tests must mirror an existing configured tooling area

Remediation: Correct the mirrored area path so it matches the tooling location.

Effective configuration:

- `tooling`: `scripts`

##### FFT101: init-module-empty

Family: `tests`
Analyzers: `python`

test package __init__.py files must be empty or docstring-only

Remediation: Remove runtime declarations from __init__.py and import them from their owning module.

##### FFT102: absolute-imports

Family: `tests`
Analyzers: `python`

tests must use absolute imports

Remediation: Replace the relative import with the full tests or application package path.

##### FFT103: no-top-level-helpers

Family: `tests`
Analyzers: `python`

test modules may contain only tests, imports, and declarations

Remediation: Move reusable functions into the local helpers.py module.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

##### FFT104: no-if-in-tests

Family: `tests`
Analyzers: `python`

tests and local test helpers must not contain conditional control flow

Remediation: Use parametrized cases when setup and assertions remain branch-free; otherwise split the behavior into separate test functions. Keep local test helpers deterministic with per-variant functions or dataclass-driven case data.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`
- Test helper filenames included in conditional-flow enforcement: `helpers.py`, `_test_helpers.py`

##### FFT105: private-constant-order

Family: `tests`
Analyzers: `python`

private test constants must appear before test functions

Remediation: Move the private constant above the first test so module setup is visible before behavior.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

##### FFT106: no-complex-comprehensions

Family: `tests`
Analyzers: `python`

nested or multi-generator comprehensions hide control flow and data shapes

Remediation: Extract a named helper when the transformation has a coherent purpose. For one-off local logic, use simple statements with named intermediate values instead of nested comprehension control flow.

##### FFT201: test-types-description

Family: `tests`
Analyzers: `python`

test-case dataclasses must define a description field

Remediation: Add description: str so parametrized cases explain the behavior they represent.

##### FFT202: test-types-expected-field

Family: `tests`
Analyzers: `python`

test-case dataclasses must define at least one expected_ field

Remediation: Name expected outcomes with an expected_ prefix and assert against them in the test.

##### FFT203: local-test-types-import

Family: `tests`
Analyzers: `python`

tests must import test-case types from their local _test_types.py

Remediation: Move the dataclass beside the test and import it through the mirrored absolute path.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

##### FFT204: local-test-types-file

Family: `tests`
Analyzers: `python`

test directories must provide a local _test_types.py

Remediation: Create _test_types.py beside the test. Custom-rule tests should define a local wrapper dataclass there rather than parametrizing directly with RuleCase.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

##### FFT205: scenario-models-dataclasses

Family: `tests`
Analyzers: `python`

scenario model modules may contain only imports and dataclass declarations

Remediation: Decorate each scenario model with @dataclass or move non-model behavior into a focused helper module.

Constraints:

- Scenario model filenames requiring dataclass-only declarations: `scenario_models.py`

##### FFT301: test-file-name

Family: `tests`
Analyzers: `python`

test modules must use a test_ filename

Remediation: Rename the module to test_<behavior>.py.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

##### FFT302: test-function-name

Family: `tests`
Analyzers: `python`

test functions must use test_given_<state>_when_<action>_then_<outcome>

Remediation: Rename the test so its precondition, action, and expected behavior are explicit.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

##### FFT401: dataclass-parametrize

Family: `tests`
Analyzers: `python`

tests must use dataclass-backed pytest parameterization

Remediation: Add @pytest.mark.parametrize with local test_case dataclass instances.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

##### FFT402: accepts-test-case

Family: `tests`
Analyzers: `python`

parametrized tests must accept a test_case argument

Remediation: Name the parameter test_case and read inputs and expectations from that object.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

##### FFT403: test-case-annotation

Family: `tests`
Analyzers: `python`

test_case parameters must use a local test-case dataclass annotation

Remediation: Annotate test_case with a dataclass imported from the local _test_types.py.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

##### FFT404: expected-field-assertion

Family: `tests`
Analyzers: `python`

tests must assert against an expected_ field from test_case

Remediation: Store the expected outcome on test_case and reference it in a behavior assertion.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

##### FFT405: parametrize-arguments

Family: `tests`
Analyzers: `python`

pytest parametrize decorators must define parameter names and values

Remediation: Pass both the parameter-name string and the case sequence to parametrize.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

Fixed limits:

- Minimum pytest parametrize positional arguments: `2`

##### FFT406: parametrize-test-case

Family: `tests`
Analyzers: `python`

pytest parametrize must expose cases through the test_case parameter

Remediation: Use "test_case" as the parametrize parameter name.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

Fixed limits:

- Minimum pytest parametrize positional arguments: `2`

##### FFT407: parametrize-ids

Family: `tests`
Analyzers: `python`

pytest parametrize decorators must define readable case ids

Remediation: Set ids to the case descriptions, normally with ids=lambda case: case.description.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

Fixed limits:

- Minimum pytest parametrize positional arguments: `2`

##### FFT408: inline-parametrize-values

Family: `tests`
Analyzers: `python`

pytest parametrize values must be a visible list, tuple, or local comprehension

Remediation: Inline the case sequence in @pytest.mark.parametrize so its cases are visible beside the test.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

Fixed limits:

- Minimum pytest parametrize positional arguments: `2`

##### FFT411: nonempty-parametrize-values

Family: `tests`
Analyzers: `python`

pytest parametrize case sequences must not be empty

Remediation: Add at least one behavior case or remove the test until a real case exists.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

Fixed limits:

- Minimum pytest parametrize positional arguments: `2`

##### FFT412: no-dict-test-cases

Family: `tests`
Analyzers: `python`

pytest cases must use typed dataclasses instead of dictionaries

Remediation: Define a local frozen test-case dataclass and construct one instance per case.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

Fixed limits:

- Minimum pytest parametrize positional arguments: `2`

##### FFT413: local-test-case-constructors

Family: `tests`
Analyzers: `python`

pytest cases must construct dataclasses from the local _test_types.py

Remediation: Parametrize using a dataclass imported from local _test_types.py. For framework harness inputs such as RuleCase, store their fields in the local dataclass and construct the framework object inside the test.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

Fixed limits:

- Minimum pytest parametrize positional arguments: `2`

##### FFT414: description-lambda-ids

Family: `tests`
Analyzers: `python`

pytest case ids must come from each test case description

Remediation: Use ids=lambda case: case.description so failures identify the behavior clearly.

Constraints:

- Test support filenames excluded from this test-module rule: `__init__.py`, `conftest.py`, `_test_types.py`, `helpers.py`, `_test_helpers.py`

Fixed limits:

- Minimum pytest parametrize positional arguments: `2`

##### XSB002: dev-tooling-location

Family: `custom`
Analyzers: `python`

development tooling must live under scripts, not product code

Remediation: Move check, format, lint, and test tooling beneath scripts/.

##### XSB003: sqlbuild-generic-filename

Family: `custom`
Analyzers: `python`

generic module filenames hide SQLBuild ownership

Remediation: Rename the module after the domain concept or operation it owns.

##### XSB023: client-entry-filename

Family: `custom`
Analyzers: `python`

client-style packages must use client.py instead of main.py

Remediation: Rename the primary client class entry module to client.py.

##### XSB024: client-public-class-count

Family: `custom`
Analyzers: `python`

client.py must define exactly one public top-level class

Remediation: Keep one public client class and move other classes to their owning modules.

##### XSB025: client-module-content

Family: `custom`
Analyzers: `python`

client.py may contain only imports and top-level classes

Remediation: Move functions and runtime statements into the class or an owned support module.

##### XSB031: adapter-entry-class-count

Family: `custom`
Analyzers: `python`

adapter class entry modules must define exactly one public top-level class

Remediation: Keep one public adapter class and move other classes to classes/.

##### XSB032: adapter-entry-content

Family: `custom`
Analyzers: `python`

adapter class entry modules may contain only imports and top-level classes

Remediation: Move functions and runtime statements into the adapter class or a role boundary.

##### XSB037: adapter-method-alias

Family: `custom`
Analyzers: `python`

first-class adapter methods must not alias BaseAdapter implementations

Remediation: Copy the implementation into the owning adapter class so overrides are explicit.

##### XSB038: adapter-super-delegation

Family: `custom`
Analyzers: `python`

first-class adapter contract methods must not delegate to super()

Remediation: Own the complete contract method implementation in the adapter class.

##### XSB041: color-capability-entry

Family: `custom`
Analyzers: `python`

color capability imports must use the presentation main entry

Remediation: Import supports_color from sqlbuild.presentation.main.supports_color.

##### XSB042: provider-public-surface

Family: `custom`
Analyzers: `python`

providers.py must contain imports and exactly one Provider class

Remediation: Keep only the public Provider class and imports in src/sqlbuild/providers.py.

##### XSB045: reuse-terminology

Family: `custom`
Analyzers: `python`

clone and reuse code must use unambiguous origin and destination terminology

Remediation: Use origin, destination, and reuse_from; source means a SQLBuild source node.

##### XSB051: metadata-query-loop

Family: `custom`
Analyzers: `python`

warehouse metadata calls must not run once per loop iteration

Remediation: Gather metadata once into a relation lookup or WarehouseSnapshot before looping.

##### XSB052: dbt-reference-resolution

Family: `custom`
Analyzers: `python`

dbt references must be identified by the centralized manifest resolver

Remediation: Resolve __dbt_ref through integrations/dbt/_helpers/manifest/sqlbuild_refs.py.

##### XSB053: dbt-graph-projection

Family: `custom`
Analyzers: `python`

dbt graph keys must be constructed by the centralized projection helper

Remediation: Use integrations/dbt/_helpers/planning/graph_projection.py.

##### XSB054: selector-marker-parsing

Family: `custom`
Analyzers: `python`

selector + markers must be parsed by split_selector_expansion

Remediation: Use compiler.planner.main.selection.selector_expansion.split_selector_expansion.

##### XSB056: sqlbuild-comment-policy

Family: `custom`
Analyzers: `python`

runtime and tooling comments must be approved directives

Remediation: Prefer clear names or docstrings; keep only recognized tool directives.

##### XSB057: source-freshness-batch-write

Family: `custom`
Analyzers: `python`

source freshness state must be written in batches

Remediation: Use write_source_freshness_records() instead of the singular writer.

##### XSB058: source-freshness-sql-ownership

Family: `custom`
Analyzers: `python`

source freshness INSERT SQL must be rendered by adapters

Remediation: Move source freshness INSERT rendering to the adapter contract.

##### XSB061: main-support-placement

Family: `custom`
Analyzers: `python`

main packages must not contain support packages

Remediation: Move _helpers/, classes/, or shared/ beside main/.

##### XSB062: single-macro-load-site

Family: `custom`
Analyzers: `python`

project macros must be loaded once in build_compile_inputs

Remediation: Pass loaded_macros down instead of calling load_project_macros again.

##### XSB066: main-discarded-call

Family: `custom`
Analyzers: `python`

main orchestrators must consume bare phase call results

Remediation: Assign, return, or explicitly discard the result with _ = call(...).

##### XSB067: phase-parameter-mutation

Family: `custom`
Analyzers: `python`

compiler and executor phase helpers must not mutate input parameters

Remediation: Return updated values, or mark a deliberate builder with # sc: allow-param-mutation.

##### XSB068: adapter-public-execute-override

Family: `custom`
Analyzers: `python`

adapter implementations must inherit the framework-owned execute entrypoint

Remediation: Implement the protected _execute hook; do not override public execute or delegate it to super().

##### XSB069: raw-driver-execution-boundary

Family: `custom`
Analyzers: `python`

raw driver execution must stay inside an approved observed statement executor

Remediation: Call adapter.execute(), or route the driver call through ObservedConnection/ObservedCursor.

##### XSB070: event-construction-ownership

Family: `custom`
Analyzers: `python`

canonical lifecycle records and catalogs must be created by observability owners

Remediation: Use OperationLifecycle, ResourceAttemptLifecycle, StatementLifecycle, or dispatcher APIs.

##### XSB071: sink-location

Family: `custom`
Analyzers: `python`

sink declarations and private runtime imports must stay in their owner boundary

Remediation: Put project sink declarations under sinks/**/*.py and use public APIs elsewhere.

#### Warning Rules

None.

### `rust` (rust)

- Analyzer: `rust`
- Parser provenance: `rust-syn-workspace-v1`; cache contract: `rust-rules-v2`
- Target policy fingerprint: `985eb5600a258e1a66ba4965deb675e082c2e4a854904c4b939d241d25a772f9`

#### Effective Project Configuration

This is the loaded effective configuration, not a template. Lists and mappings are rendered deterministically; path-threshold declarations retain declaration order because that order breaks equally specific matches.

- Configuration source: "fensu.toml"
- Project root from installation root: "."
- Installation root: "."
- Current skill identity: "fensu-sqlbuild"
- Analyzer: `rust`
- Complete loaded catalogue size: 117

##### Scopes

- Product roots: ["crates"]
- Test roots: []
- Tooling roots: []

- Generated source patterns: []

- UI-kit root: null

- shadcn config: null
- OpenAPI document: null

##### Configured Rule Selectors

- Blocking selectors (`select`): ["FPRS"]
- Warning selectors (`warn`): []
- Ignore selectors (`ignore`): []

##### Resolved Rule Sets

- Blocking rule codes: ["FPRSA103", "FPRSH001", "FPRSH002", "FPRSH003", "FPRSH004", "FPRSH005", "FPRSH006", "FPRSH007", "FPRSH008", "FPRSH010", "FPRSH011", "FPRSH012", "FPRSH013", "FPRSH901", "FPRSH902", "FPRSL001", "FPRSL002", "FPRSL101", "FPRSL102", "FPRSL103", "FPRSL104", "FPRSL105", "FPRSL110", "FPRSL301", "FPRSL302", "FPRSL303", "FPRSL304", "FPRSL305", "FPRSL306", "FPRSL307", "FPRSL901", "FPRSN001", "FPRSN002", "FPRSN003", "FPRSN004", "FPRSR001", "FPRSR002", "FPRSR003", "FPRSR004", "FPRSR101", "FPRSR102", "FPRSR103", "FPRSR104", "FPRSR201", "FPRSR202", "FPRSR204", "FPRSR205", "FPRSR301", "FPRSR302", "FPRSR303", "FPRSR304", "FPRSR305", "FPRSR306", "FPRSR307", "FPRSR308", "FPRSR309", "FPRSR310", "FPRSR401", "FPRSR402", "FPRSR403", "FPRSR404", "FPRSR405", "FPRSR406", "FPRSR502", "FPRSR503", "FPRSR601", "FPRSR701", "FPRSR702", "FPRSR703", "FPRSR704", "FPRSR705", "FPRSR706", "FPRSS001", "FPRSS002", "FPRSS003", "FPRSS010", "FPRSS011", "FPRSS101", "FPRSS102", "FPRSS110", "FPRSS120", "FPRSS130", "FPRSS131", "FPRSS201", "FPRST001", "FPRST002", "FPRST003", "FPRST004", "FPRST005", "FPRST006", "FPRST007", "FPRST008", "FPRST101", "FPRST102", "FPRST103", "FPRST104", "FPRST105", "FPRST110", "FPRST201", "FPRST202", "FPRST203", "FPRST204", "FPRST301", "FPRST302", "FPRST401", "FPRST402", "FPRST403", "FPRST404", "FPRST405", "FPRST406", "FPRST407", "FPRST408", "FPRST411", "FPRST412", "FPRST413", "FPRST414", "FPRST420"]
- Warning rule codes: []
- Ignored matched rule codes: []

Normal work must satisfy blocking policy. Warnings are review signals, not scope authorization. Run `fensu check --warn` after substantial changes when practical, and never delete code or change architecture solely because of an advisory warning without verifying the actual contract.

##### Custom Rule Sources

- `rule_paths`: []
- `rule_modules`: []

- `rule_packs`: ["rust"]

##### Cache And Evaluation

- Cache enabled: `true`
- Cache requires cacheable rules: `false`
- Evaluation include boundaries: []
- Evaluation exclude boundaries: []

##### Effective Global Thresholds

- `max_api_exports` = 3
- `max_api_lines` = 200
- `max_arguments` = 10
- `max_component_script_lines` = 250
- `max_distinct_calls` = 20
- `max_file_lines` = 2000
- `max_helpers_container_modules` = 10
- `max_imported_bindings` = 20
- `max_locals` = 20
- `max_main_container_modules` = 20
- `max_positional_args` = 1
- `max_public_exports` = 20
- `max_resource_families` = 1
- `max_role_depth` = 1
- `max_route_script_lines` = 200
- `max_script_entrypoint_lines` = 80
- `max_state_cells` = 15
- `max_state_functions` = 15
- `max_state_lines` = 300
- `max_state_public_members` = 20
- `max_statements` = 40
- `max_statements_global` = 70
- `max_total_runes` = 20
- `min_custom_rule_test_cases` = 1
- `min_shared_domain_prefix_packages` = 2

##### Configured Role Threshold Overrides

- None.

##### Configured Path Threshold Overrides

- Match basis: target-relative analyzer paths; reported repository paths use the same paths for this target.

- None.

##### Effective Naming Contracts

- "as_*" = "returns-value"
- "can_*" = "returns-bool"
- "enforce_*" = "no-return"
- "get_*" = "returns-value"
- "has_*" = "returns-bool"
- "is_*" = "returns-bool"
- "iter_*" = "returns-iterator"
- "iterate_*" = "returns-iterator"
- "should_*" = "returns-bool"
- "supports_*" = "returns-bool"
- "to_*" = "returns-value"
- "validate_*" = "no-return"

##### Configured Rule Exceptions

- None.

##### Configured Path-Scoped Rule Ignores

- None.

#### Blocking Rules

##### FPRSA103: rust-rsa103

Family: `annotations`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSH001: rust-rsh001

Family: `hygiene`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSH002: rust-rsh002

Family: `hygiene`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSH003: rust-rsh003

Family: `hygiene`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSH004: rust-rsh004

Family: `hygiene`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSH005: rust-rsh005

Family: `hygiene`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSH006: rust-rsh006

Family: `hygiene`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSH007: rust-rsh007

Family: `hygiene`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSH008: rust-rsh008

Family: `hygiene`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSH010: rust-rsh010

Family: `hygiene`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSH011: rust-rsh011

Family: `hygiene`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSH012: rust-rsh012

Family: `hygiene`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSH013: rust-rsh013

Family: `hygiene`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSH901: rust-rsh901

Family: `hygiene`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSH902: rust-rsh902

Family: `hygiene`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSL001: rust-rsl001

Family: `layers`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSL002: rust-rsl002

Family: `layers`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSL101: rust-rsl101

Family: `layers`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSL102: rust-rsl102

Family: `layers`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

Options:

###### `packages`

- Type: `list[string]`
- Required: `false`
- Default: []
- Current value: []
- Description: None
- Choices: None
- Minimum: None
- Maximum: None
- Minimum items: None

###### `remediation`

- Type: `string`
- Required: `false`
- Default: "consume shared fact models instead of parser or AST types"
- Current value: "consume SQLBuild-owned SQL fact rows instead of raw parser types"
- Description: None
- Choices: None
- Minimum: None
- Maximum: None
- Minimum items: None

###### `restricted_paths`

- Type: `list[string]`
- Required: `false`
- Default: ["rules"]
- Current value: ["crates/sqlbuild-rules-native/src/rules"]
- Description: None
- Choices: None
- Minimum: None
- Maximum: None
- Minimum items: None

##### FPRSL103: rust-rsl103

Family: `layers`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSL104: rust-rsl104

Family: `layers`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSL105: rust-rsl105

Family: `layers`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSL110: rust-rsl110

Family: `layers`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSL301: rust-rsl301

Family: `layers`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

Options:

###### `forbidden_packages`

- Type: `list[string]`
- Required: `false`
- Default: []
- Current value: ["sqlbuild-structure-checker", "fensu-structure-checker"]
- Description: None
- Choices: None
- Minimum: None
- Maximum: None
- Minimum items: None

##### FPRSL302: rust-rsl302

Family: `layers`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSL303: rust-rsl303

Family: `layers`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSL304: rust-rsl304

Family: `layers`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

Options:

###### `crate_names`

- Type: `list[string]`
- Required: `false`
- Default: []
- Current value: ["sqlbuild-rules-native"]
- Description: None
- Choices: None
- Minimum: None
- Maximum: None
- Minimum items: None

##### FPRSL305: rust-rsl305

Family: `layers`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

Options:

###### `domain_paths`

- Type: `list[string]`
- Required: `false`
- Default: []
- Current value: []
- Description: None
- Choices: None
- Minimum: None
- Maximum: None
- Minimum items: None

###### `intentional_layout_paths`

- Type: `list[string]`
- Required: `false`
- Default: []
- Current value: []
- Description: None
- Choices: None
- Minimum: None
- Maximum: None
- Minimum items: None

###### `role_paths`

- Type: `list[string]`
- Required: `false`
- Default: []
- Current value: []
- Description: None
- Choices: None
- Minimum: None
- Maximum: None
- Minimum items: None

##### FPRSL306: rust-rsl306

Family: `layers`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSL307: rust-rsl307

Family: `layers`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSL901: rust-rsl901

Family: `layers`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSN001: rust-rsn001

Family: `naming`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSN002: rust-rsn002

Family: `naming`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSN003: rust-rsn003

Family: `naming`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSN004: rust-rsn004

Family: `naming`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR001: rust-rsr001

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR002: rust-rsr002

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR003: rust-rsr003

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR004: rust-rsr004

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR101: rust-rsr101

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR102: rust-rsr102

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR103: rust-rsr103

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR104: rust-rsr104

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR201: rust-rsr201

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR202: rust-rsr202

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR204: rust-rsr204

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR205: rust-rsr205

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR301: rust-rsr301

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

Options:

###### `max_modules`

- Type: `integer`
- Required: `false`
- Default: 10
- Current value: 10
- Description: None
- Choices: None
- Minimum: 1
- Maximum: None
- Minimum items: None

##### FPRSR302: rust-rsr302

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

Options:

###### `max_modules`

- Type: `integer`
- Required: `false`
- Default: 20
- Current value: 20
- Description: None
- Choices: None
- Minimum: 1
- Maximum: None
- Minimum items: None

##### FPRSR303: rust-rsr303

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR304: rust-rsr304

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR305: rust-rsr305

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR306: rust-rsr306

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR307: rust-rsr307

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR308: rust-rsr308

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR309: rust-rsr309

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR310: rust-rsr310

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR401: rust-rsr401

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR402: rust-rsr402

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR403: rust-rsr403

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR404: rust-rsr404

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR405: rust-rsr405

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR406: rust-rsr406

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR502: rust-rsr502

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR503: rust-rsr503

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR601: rust-rsr601

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

Options:

###### `max_file_lines`

- Type: `integer`
- Required: `false`
- Default: 2000
- Current value: 2000
- Description: None
- Choices: None
- Minimum: 1
- Maximum: None
- Minimum items: None

##### FPRSR701: rust-rsr701

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR702: rust-rsr702

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR703: rust-rsr703

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR704: rust-rsr704

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR705: rust-rsr705

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSR706: rust-rsr706

Family: `roles`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSS001: rust-rss001

Family: `shape`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

Options:

###### `max_statements`

- Type: `integer`
- Required: `false`
- Default: 40
- Current value: 40
- Description: None
- Choices: None
- Minimum: 1
- Maximum: None
- Minimum items: None

##### FPRSS002: rust-rss002

Family: `shape`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

Options:

###### `max_distinct_calls`

- Type: `integer`
- Required: `false`
- Default: 20
- Current value: 20
- Description: None
- Choices: None
- Minimum: 1
- Maximum: None
- Minimum items: None

##### FPRSS003: rust-rss003

Family: `shape`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

Options:

###### `max_locals`

- Type: `integer`
- Required: `false`
- Default: 20
- Current value: 20
- Description: None
- Choices: None
- Minimum: 1
- Maximum: None
- Minimum items: None

##### FPRSS010: rust-rss010

Family: `shape`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

Options:

###### `max_arguments`

- Type: `integer`
- Required: `false`
- Default: 10
- Current value: 10
- Description: None
- Choices: None
- Minimum: 1
- Maximum: None
- Minimum items: None

##### FPRSS011: rust-rss011

Family: `shape`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

Options:

###### `max_statements`

- Type: `integer`
- Required: `false`
- Default: 70
- Current value: 70
- Description: None
- Choices: None
- Minimum: 1
- Maximum: None
- Minimum items: None

##### FPRSS101: rust-rss101

Family: `shape`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSS102: rust-rss102

Family: `shape`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSS110: rust-rss110

Family: `shape`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSS120: rust-rss120

Family: `shape`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSS130: rust-rss130

Family: `shape`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSS131: rust-rss131

Family: `shape`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRSS201: rust-rss201

Family: `shape`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST001: rust-rst001

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST002: rust-rst002

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST003: rust-rst003

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST004: rust-rst004

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST005: rust-rst005

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST006: rust-rst006

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST007: rust-rst007

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST008: rust-rst008

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST101: rust-rst101

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST102: rust-rst102

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST103: rust-rst103

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST104: rust-rst104

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST105: rust-rst105

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST110: rust-rst110

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST201: rust-rst201

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST202: rust-rst202

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST203: rust-rst203

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST204: rust-rst204

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST301: rust-rst301

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST302: rust-rst302

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST401: rust-rst401

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST402: rust-rst402

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST403: rust-rst403

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST404: rust-rst404

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST405: rust-rst405

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST406: rust-rst406

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST407: rust-rst407

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST408: rust-rst408

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST411: rust-rst411

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST412: rust-rst412

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST413: rust-rst413

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST414: rust-rst414

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

##### FPRST420: rust-rst420

Family: `tests`
Analyzers: `rust`

Rust workspace structure policy violation.

Remediation: Run fensu check for the diagnostic's rule-specific remediation.

#### Warning Rules

None.
