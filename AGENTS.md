# Agent Instructions

## Testing

- Actively look for opportunities to add sensible integration and E2E tests, not only unit tests.
  DuckDB makes real end-to-end coverage cheap in this repository: prefer exercising the real CLI,
  compiler, executor, and state paths over mocking them. Unit-only coverage of new behavior gives a
  false sense of completion and lets the product rot; every new feature or behavior change should
  ship with at least one integration or E2E test proving the complete path works.

- Run targeted pytest commands with xdist by default: `uv run pytest <paths> -n auto --dist loadfile`.
- Do not run pytest serially unless diagnosing an xdist-specific failure.
- `make test` is the sanctioned broader local unit and integration check. It is normally acceptable
  when the change warrants broader regression coverage because the target owns the required paths,
  marker exclusions, xdist settings, and logging.
- Do not replace `make test` with a raw broad pytest command. Do not run `make test-all`, E2E, dbt,
  real-warehouse, or the full CI suite locally unless reproducing a specific failure or the user
  explicitly requests it; rely on CI for those suites.
- Before pushing, run the exact static CI target with all optional dependencies available: `uv sync --all-extras` followed by `make check-ci`.

## Real-Project Verification and Performance Guards

- Synthetic fixtures and clean benchmark projects do not exercise every path. Before releasing
  changes to compilation, SQL analysis, diagnostics, formatting, Rules, or planning, run the built
  branch against at least one large real project available locally outside this repository, and
  compare it with the latest release. Compare diagnostic counts by code, cold compile wall time and
  peak memory, and, for formatter changes, that formatting preserves compiled dependencies, lineage,
  and query semantics.
- Treat every new diagnostic on a real project as a false positive until warehouse evidence proves
  otherwise, for example a model that has built successfully since its SQL last changed.
- A material slowdown or new false positive is a release blocker, not a follow-up.
- Real-project names, SQL, identifiers, file paths, and results never enter this repository, commits,
  pull requests, or CI output. Record only neutral aggregate conclusions, and rebuild every
  reproduction synthetically.
- Performance guards must cover worst-case paths, not only clean projects: very large models,
  diagnostic-heavy compiles with many errors and warnings, wide queries, and deep macro expansion.
  Any per-diagnostic, per-reference, or per-token work must be bounded by a test with a strict time
  limit. A path that is only slow when something is wrong is still a regression.

## Public Repository Hygiene

- Treat every tracked file, generated artifact, fixture, benchmark, filename, commit, branch, pull
  request, review comment, screenshot, and CI log as publicly visible.
- Use only neutral synthetic examples such as orders, customers, products, inventory, fulfillment,
  support tickets, and product-owned identifiers. Never copy organization-, client-, provider-,
  environment-, infrastructure-, or production-specific names, data, query output, identifiers, or
  links into public artifacts, even when the source operation was read-only.
- Keep real-system validation evidence in its approved private tracking location. Do not paste that
  evidence into source, tests, documentation, generated skills, benchmarks, commit metadata, pull
  requests, or CI output.
- Load and follow the `public-repository-hygiene` skill before editing or publishing this repository.
  Run its private scanner over the working tree and introduced history before every push, and
  rescan after generation, formatting, rebasing, or merging.
- Never bypass the configured public-repository Git hooks. A missing or failing private scanner is
  a publication blocker.
- Do not copy the private restricted-vocabulary list or scanner implementation into this public
  repository.

## Command-Line User Experience

- Keep lifecycle feedback consistent across commands. Potentially slow discovery, connection,
  inspection, planning, and execution phases must emit a concise start message and an explicit
  success or failure completion message; do not leave users watching a blank terminal with no
  indication that work is active.
- Preserve machine-readable stdout. When JSON or another machine-output mode is active, send
  lifecycle progress to stderr so redirected output remains valid while interactive users still see
  meaningful progress.
- Prefer a few meaningful phase transitions over noisy per-resource narration. Long-running TTY
  phases should use the shared transient progress facilities where practical.
- Maintenance notices and unrelated warnings must not be the final visible output of an otherwise
  successful command. Report them before command execution or ensure the command still prints an
  unambiguous terminal success state afterward.
- Use `sqb debug` as the first diagnostic when distinguishing authentication, connection,
  configuration, and command-specific failures.

## Subagent Verification

- Read-only review subagents are standing-authorized at meaningful review boundaries and do not
  require a task-specific user request. This standing authorization does not extend to implementation
  or open-ended research delegation. The bounded review cycle below remains the required limit.
- The primary agent owns the overall verification plan. Do not ask multiple subagents to run the same broad test suites.
- Implementation subagents should run only tests directly covering changed behavior plus targeted lint, type, and architecture checks for touched files.
- Review subagents are read-only by default. They should inspect the diff and relevant call flow and run only focused tests needed to validate a concrete suspected finding.
- Follow-up reviews should verify only previously reported findings and affected boundaries rather than repeating the complete review or full suite.
- `make test` may be used for broader local unit and integration verification; use repository CI for
  `test-all`, end-to-end, dbt, real-warehouse, and other full suites unless the user explicitly
  requests local verification or CI is unavailable.
- State the expected verification scope in subagent prompts and explicitly prohibit unnecessary full-suite runs.
- Do not delay committing and pushing a focused fix solely to repeat checks already completed successfully by another agent or CI.

## State and Source of Truth

- Do not store what can be calculated. If a value can be derived from the project or the live
  warehouse at the point of use, derive it there and then instead of persisting it and reading it
  back later.
- Stored state is for history, auditing, logging, and facts that genuinely cannot be recalculated:
  what was built, when, at which version, and whether a migration or batch completed.
- The warehouse catalog and planner snapshot are authoritative for live facts such as relation
  existence, relation type, columns and types, table type, and retention. Never infer a live fact
  from fingerprints, events, bindings, or a plan reason when the warehouse can answer; built-up
  state drifts through external drops and edits and then needs reconciliation.
- Consult stored state only after the live facts it describes are confirmed. For example, a model
  whose relation is missing plans as a first run regardless of any recorded fingerprint.

## Direct-Mode Warehouse State

- NEVER implement a mutable lifecycle state machine in raw warehouse state tables in direct mode. Do not represent progress by repeatedly updating one row through statuses such as `PLANNED`, `RUNNING`, and `COMPLETE`.
- Model lifecycle state as immutable, append-only events or facts with deterministic event IDs and idempotent writes. Derive current status by projecting event history, following the existing microbatch requirement/completion pattern. Retention pruning is cleanup, not a lifecycle update.
- Design every warehouse-DML/state-publication failure window for reconciliation from durable events and physical warehouse evidence. If append-only state cannot represent a proposed direct-mode feature safely, stop and resolve the architecture explicitly rather than adding mutable transitions.
- Sequential microbatch execution (`batch_concurrency = 1`) is fully stateless: zero reads and zero writes of `_sqlbuild_microbatches`. The state table is strictly a concurrency-coordination feature. Reintroducing state reads or writes into the sequential path requires an explicit user-approved design decision, never incidental wiring.
- State-table schemas evolve additively only: add new columns and deprecate old columns in place; never repurpose a column or change a stored format in place. Readers must tolerate absent new columns. Do not build version-reset or migration machinery for state tables; a breaking state change requires an explicit user decision and a one-time operator-performed table drop.

## Delivery Workflow

- Consolidate related work targeting the same release into one delivery branch and one pull request. Use separate pull requests only for independently releasable changes, intentionally different delivery timing, concrete risk isolation, or explicit user instruction.
- Local commits are checkpoints and do not trigger CI. Complete related implementation and review before the first push.
- Run targeted regressions and fast local static checks before pushing. Do not delay a ready commit or push solely to run or wait for long full integration or end-to-end suites that CI already executes; run those locally only to reproduce or diagnose the change, or when the user explicitly requests them. CI remains the required broad-suite gate.
- Review the complete local diff against the target branch and resolve findings before pushing. Do not push partial or overlapping branches merely to start CI.
- Push once and open one ready pull request, then immediately enable squash auto-merge unless the
  user explicitly asks to leave that pull request unmerged. The delivery agent owns enabling
  auto-merge; do not assume a separate GitHub workflow or bot will enable it. Verify the pull
  request reports an active auto-merge request, or confirm it completed as a squash merge
  immediately after the enable command when all required checks had already passed.
- Do not interpret "do not manually merge" as permission to leave auto-merge disabled. It means
  enable auto-merge and let GitHub merge after required checks pass. Do not invoke a manual merge
  while the automation is healthy. Watch the pull request through merge in the foreground when no
  other useful work remains, or keep a background watch running while continuing independent work.
  Use a manual merge only with concrete evidence that auto-merge is broken or unavailable, and
  document that evidence and the fallback reason first.
- PR titles must follow Conventional Commits. Descriptions must be no longer than 2,000 characters and contain non-empty `## Why`, `## Changes`, and `## Verification` sections in that order.
- Before creating or editing a PR, validate its metadata with `make check-pr-metadata PR_TITLE='type: summary' PR_BODY_FILE=/path/to/body.md`.
- Monitor CI after every push and follow it through completion. Address failures before considering delivery complete.
- When asked to babysit or watch a pull request, keep exactly one active background CI watcher for
  the surviving pull request until its latest commit reaches a terminal state. Do not stop at the
  initial push, PR creation, or an intermediate green run superseded by a later push. If pull
  requests are consolidated, stop obsolete watchers and retain one watcher for the combined PR.
- Babysitting includes inspecting failures, applying and pushing required fixes, restarting the
  watcher after each push, and reporting the final green state. It does not authorize merging when
  the user has asked for the pull request to remain unmerged.
- Push follow-up commits only for CI failures or correctness findings that could not reasonably have been found before the first push.
- For deployable changes, continue through auto-merge, release workflow completion, package publication, and published-version verification. Do not stop at PR creation unless the user explicitly asks.

## Review Discipline

- Treat review findings as hypotheses to validate against the supported product contract, ownership boundary, and realistic execution paths before changing code.
- Prioritize concrete correctness, authorization, data-loss, and mutation risks within systems the project manages. Distinguish those from unsupported external misuse or purely theoretical states.
- Keep fixes within the requested scope. Do not expand supported behavior, permissions, operational cost, or system ownership without a short product decision from the user.
- Do not add safeguards solely for impossible or unsupported states. Record residual risks when a concern is real but outside the current contract.

## Duplicated Code

- Run `uv run fensu dupes --since origin/main` before review, and `uv run fensu dupes --path '<area glob>'` before adding helpers or logic to an area that may already implement them. The report is advisory: unlike `fensu check`, it never gates and never needs to reach zero.
- Treat a genuine duplicate as evidence of possible wider drift, not only a cleanup task: a missing shared owner, parallel implementations of one concept, logic on the wrong side of a boundary, or copies that have already diverged (use `--diff`; a fix present in only one copy may be a bug in the others). Diagnose and record that wider smell before consolidating, because removing the copies erases the only deterministic signal of it.
- Consolidate genuine duplication the change introduces or touches. Report unrelated findings as follow-ups instead of refactoring them opportunistically.
- Members marked `[forced]` are adapter contract overrides required by `test_strict_adapter.py`. Record other intentional mirrors in `[dupes]` in `fensu.toml` with a reason.
- Public adapter contract methods are duplicated per adapter on purpose: `test_strict_adapter.py` requires every first-class adapter to define them, and `[dupes]` exempts them. The private helpers behind them must not be copied. Keep them in shared builders, such as the snapshot SQL builders in `src/sqlbuild/adapter/contract/classes/`, and let each contract method delegate. Express real dialect differences as explicit parameters, such as a `SnapshotSqlDialect` field, not as a forked copy of the helper.

## Bounded Review Process

Orchestrating agents must run reviews as a single bounded cycle, not an open-ended loop:

1. The orchestrator first performs its own targeted diff scan of dangerous seams (boundaries, gates, exit codes, state writes, deleted-symbol references) — not a line-by-line style review.
2. Use exactly one independent read-only review subagent on the complete combined diff, scoped to concrete correctness, data-loss, authorization, and behavioral-regression risks, with file:line evidence required for every finding. The reviewer must be explicitly told not to propose architecture expansions or run broad test suites.
3. Findings are hypotheses, never mandates. A validated in-scope correctness bug is fixed; any finding whose fix would expand behavior, state, permissions, or ownership is escalated to the user as a product decision — accept the reviewer's finding, never its solution, without validation. This rule exists because converting a correct review finding directly into an unapproved stateful implementation caused a production defect.
4. One follow-up pass verifies only the fixed findings and their affected boundaries — never a fresh full re-review, never broad suites.
5. Do not run overlapping review agents, issue "look for more things to harden" prompts, or enter review→fix→review loops. Valid out-of-scope findings become tickets, not opportunistic fixes.
6. After the single review cycle, the mechanical gates (`make test` where warranted, `make check-ci`, repository CI) are the final arbiter.
