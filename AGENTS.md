# Agent Instructions

## Testing

- Run targeted pytest commands with xdist by default: `uv run pytest <paths> -n auto --dist loadfile`.
- Do not run pytest serially unless diagnosing an xdist-specific failure.
- `make test` is the sanctioned broader local unit and integration check. It is normally acceptable
  when the change warrants broader regression coverage because the target owns the required paths,
  marker exclusions, xdist settings, and logging.
- Do not replace `make test` with a raw broad pytest command. Do not run `make test-all`, E2E, dbt,
  real-warehouse, or the full CI suite locally unless reproducing a specific failure or the user
  explicitly requests it; rely on CI for those suites.
- Before pushing, run the exact static CI target with all optional dependencies available: `uv sync --all-extras` followed by `make check-ci`.

## Subagent Verification

- The primary agent owns the overall verification plan. Do not ask multiple subagents to run the same broad test suites.
- Implementation subagents should run only tests directly covering changed behavior plus targeted lint, type, and architecture checks for touched files.
- Review subagents are read-only by default. They should inspect the diff and relevant call flow and run only focused tests needed to validate a concrete suspected finding.
- Follow-up reviews should verify only previously reported findings and affected boundaries rather than repeating the complete review or full suite.
- `make test` may be used for broader local unit and integration verification; use repository CI for
  `test-all`, end-to-end, dbt, real-warehouse, and other full suites unless the user explicitly
  requests local verification or CI is unavailable.
- State the expected verification scope in subagent prompts and explicitly prohibit unnecessary full-suite runs.
- Do not delay committing and pushing a focused fix solely to repeat checks already completed successfully by another agent or CI.

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
- Push once and open one ready pull request so CI and configured auto-merge can complete delivery.
- After auto-merge is enabled, do not invoke a manual merge while the automation is healthy. Watch the pull request through merge in the foreground when no other useful work remains, or keep a background watch running while continuing independent work. Use a manual merge only with concrete evidence that auto-merge is broken or unavailable, and document that evidence and the fallback reason first.
- PR titles must follow Conventional Commits. Descriptions must be no longer than 2,000 characters and contain non-empty `## Why`, `## Changes`, and `## Verification` sections in that order.
- Before creating or editing a PR, validate its metadata with `make check-pr-metadata PR_TITLE='type: summary' PR_BODY_FILE=/path/to/body.md`.
- Monitor CI after every push and follow it through completion. Address failures before considering delivery complete.
- Push follow-up commits only for CI failures or correctness findings that could not reasonably have been found before the first push.
- For deployable changes, continue through auto-merge, release workflow completion, package publication, and published-version verification. Do not stop at PR creation unless the user explicitly asks.

## Review Discipline

- Treat review findings as hypotheses to validate against the supported product contract, ownership boundary, and realistic execution paths before changing code.
- Prioritize concrete correctness, authorization, data-loss, and mutation risks within systems the project manages. Distinguish those from unsupported external misuse or purely theoretical states.
- Keep fixes within the requested scope. Do not expand supported behavior, permissions, operational cost, or system ownership without a short product decision from the user.
- Do not add safeguards solely for impossible or unsupported states. Record residual risks when a concern is real but outside the current contract.

## Bounded Review Process

Orchestrating agents must run reviews as a single bounded cycle, not an open-ended loop:

1. The orchestrator first performs its own targeted diff scan of dangerous seams (boundaries, gates, exit codes, state writes, deleted-symbol references) — not a line-by-line style review.
2. Exactly one independent read-only review pass runs on the complete combined diff, scoped to concrete correctness, data-loss, authorization, and behavioral-regression risks, with file:line evidence required for every finding. The reviewer must be explicitly told not to propose architecture expansions.
3. Findings are hypotheses, never mandates. A validated in-scope correctness bug is fixed; any finding whose fix would expand behavior, state, permissions, or ownership is escalated to the user as a product decision — accept the reviewer's finding, never its solution, without validation. This rule exists because converting a correct review finding directly into an unapproved stateful implementation caused a production defect.
4. One follow-up pass verifies only the fixed findings and their affected boundaries — never a fresh full re-review, never broad suites.
5. Do not run overlapping review agents, issue "look for more things to harden" prompts, or enter review→fix→review loops. Valid out-of-scope findings become tickets, not opportunistic fixes.
6. After the single review cycle, the mechanical gates (`make test` where warranted, `make check-ci`, repository CI) are the final arbiter.
