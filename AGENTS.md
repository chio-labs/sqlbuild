# Agent Instructions

## Testing

- Run targeted pytest commands with xdist by default: `uv run pytest <paths> -n auto --dist loadfile`.
- Do not run pytest serially unless diagnosing an xdist-specific failure.
- Do not run the full local test or CI suite unless the user explicitly requests it.
- Before pushing, run the exact static CI target with all optional dependencies available: `uv sync --all-extras` followed by `make check-ci`.

## Subagent Verification

- The primary agent owns the overall verification plan. Do not ask multiple subagents to run the same broad test suites.
- Implementation subagents should run only tests directly covering changed behavior plus targeted lint, type, and architecture checks for touched files.
- Review subagents are read-only by default. They should inspect the diff and relevant call flow and run only focused tests needed to validate a concrete suspected finding.
- Follow-up reviews should verify only previously reported findings and affected boundaries rather than repeating the complete review or full suite.
- Use repository CI for full unit, integration, and end-to-end suites unless the user explicitly requests local full verification or CI is unavailable.
- State the expected verification scope in subagent prompts and explicitly prohibit unnecessary full-suite runs.
- Do not delay committing and pushing a focused fix solely to repeat checks already completed successfully by another agent or CI.

## Direct-Mode Warehouse State

- NEVER implement a mutable lifecycle state machine in raw warehouse state tables in direct mode. Do not represent progress by repeatedly updating one row through statuses such as `PLANNED`, `RUNNING`, and `COMPLETE`.
- Model lifecycle state as immutable, append-only events or facts with deterministic event IDs and idempotent writes. Derive current status by projecting event history, following the existing microbatch requirement/completion pattern. Retention pruning is cleanup, not a lifecycle update.
- Design every warehouse-DML/state-publication failure window for reconciliation from durable events and physical warehouse evidence. If append-only state cannot represent a proposed direct-mode feature safely, stop and resolve the architecture explicitly rather than adding mutable transitions.

## Pull Requests

- Prefer one PR for related changes targeting the same release; split work only when independent review, release timing, or risk isolation provides a concrete benefit that outweighs duplicate CI and review overhead.
- PR titles must follow Conventional Commits.
- PR descriptions must be no longer than 2,000 characters.
- PR descriptions must contain non-empty `## Why`, `## Changes`, and `## Verification` sections in that order.
- Before running `gh pr create` or editing PR metadata, validate the proposed title and body locally with `make check-pr-metadata PR_TITLE='type: summary' PR_BODY_FILE=/path/to/body.md`.

## Release Follow-Through

- After opening a deployable pull request, monitor it through CI, merge, release workflow completion, and package publication, either directly or with a background task. Resolve failures where possible and verify the published version before handing off. Do not stop at pull request creation unless the user explicitly asks you to.
