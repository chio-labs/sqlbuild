# Contributing

Thanks for helping improve SQLBuild. Keep changes focused, tested, and easy to review.

## Setup

SQLBuild requires Python 3.12 or newer.

Install dependencies with:

```bash
uv sync
```

## Development Workflow

- Create a branch for your change.
- Keep pull requests focused on one behavior change or cleanup.
- Add or update tests for behavior changes.
- Prefer small, direct changes over broad rewrites.
- Do not commit secrets, credentials, machine-local config, or generated scratch files.

## Checks

Before opening a pull request, run:

```bash
make check
```

For broader validation, run:

```bash
make verify
```

For focused iteration, run the narrowest relevant pytest target, for example:

```bash
pytest tests/unit/src/sqlbuild/compiler/compile/test_main.py
```

## Tests

- Mirror source layout under `tests/<scope>/src/sqlbuild/...`.
- Prefer dataclass-backed test cases for non-trivial scenarios.
- Use clear Given-When-Then test names.
- Prefer real parsing, filesystem, compile, and planner behavior over mocks when practical.
- For substantive behavior changes, validate test strength with a small semantic mutation and confirm the relevant test fails before reverting it.

## Project Conventions

- Keep `sqb compile` offline and static unless intentionally changing that contract.
- Keep examples reproducible and avoid environment-specific assumptions.
- Use project-local config files for local overrides, and do not commit credentials or personal settings.
- Follow existing code style and module organization before introducing new patterns.

## Commits And Pull Requests

- Use concise conventional commit messages, such as `fix: ...`, `feat: ...`, `test: ...`, or `docs: ...`.
- In pull requests, summarize the behavior change and list the checks you ran.
- Call out breaking changes, migrations, or compatibility decisions explicitly.
