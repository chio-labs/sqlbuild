# Varied warm-compile guard

`make test-e2e-varied-cache-performance` exercises a generated 1,000-model order
project in fresh CLI processes. The cache performance CI job runs this guard in a
4GiB cgroup with swap disabled, alongside the existing scaling benchmarks.

The workload uses independently authored synthetic SQL. It retains the dense
fixture's sources, seeds, SQL functions, audits, scoped Python macros, SQL tests,
all built-in rules and one isolated custom project rule. It adds a shared dependency
graph and varies the actual expressions: CASE, aggregate windows, array indexing,
null handling, grouped queries, lateral joins and unions.

## Structural protection

The guard measures structure from compiled SQL and model dependencies. It requires:

- At least 950 distinct operator-tree shapes. Identifier names and literal values
  do not count toward this diversity measurement.
- A connected component containing at least 900 models.
- Dependency depth between 40 and 60 models, with 150–400 leaf models.

These checks prevent a fixture change from silently replacing the workload with
mostly repeated queries or independent shallow chains. Structural diversity is
still a proxy for application workloads; private acceptance measurements remain
separate from this public synthetic fixture.

## Cache and correctness protection

The guard measures initial cache fill, an unchanged warm compile, a leaf SQL edit,
a shared upstream SQL edit and a Python macro edit. Each edit is followed by an
unchanged compile and an uncached oracle with both analysis and rule cache reuse
disabled. Project configuration is restored after each oracle.

Every edited cached result must match its oracle's semantic JSON and every compiled
artifact. Unchanged runs must reuse analysis for every model. Edit runs must record
both reuse and invalidation, rather than treating a high cache-hit count alone as
evidence of correctness. A smaller integration fixture executes its generated SQL
tests in DuckDB with the standard rules enabled.

Warm and edit budgets apply to complete fresh-process CLI wall time, including
discovery, macro expansion, lint, rules, artifacts and output. SQL-analysis timing
alone is insufficient: these other phases can dominate after analysis is cached.

The initial ceilings are 24s for cache fill, 10s for unchanged warm compiles and
13s for edits, with a 2GiB process-RSS ceiling and the separate 4GiB combined CI
limit. These are regression ceilings with hosted-execution headroom, not promised
application timings. Golden fingerprints also protect the baseline and edited
outputs across compiler releases.
