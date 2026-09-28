<!-- generated-by: sqlbuild skills -->

# Testing and deterministic Rules

> Test custom findings and keep implementations safe for dependency-aware caching.

Online: https://sqlbuild.com/docs/concepts/rules/custom-rules/testing-and-determinism/

## Test Rules

Use the public harness to exercise discovery, compilation, and Rules evaluation:

```python
from sqlbuild.rules.testing import RuleCase, evaluate_rule
from rules.final_outputs import final_order_identifier

def test_given_missing_order_id_when_evaluating_then_reports_finding() -> None:
    result = evaluate_rule(
        rule=final_order_identifier,
        test_case=RuleCase(
            description="missing order identifier",
            source='MODEL (description "Orders");\nSELECT 1 AS customer_id\n',
            path="models/final/customer_orders.sql",
            expected_finding_count=1,
        ),
    )

    assert result.finding_count == 1
```

`RuleCase.files` adds supporting project files. `RuleCase.config` supplies option values. Include
passing cases, failing cases, near misses, and exact source-position assertions.

Each case also checks determinism. The harness evaluates every subject once, then evaluates every
subject again in reverse order in the same process. If the Rule's findings differ between the two
passes, the case fails with `custom rule <code> is not deterministic`. The usual cause is
module-level state, such as a set of already-seen models, that carries over from one subject to
the next. Compute findings from the subject and `ctx` alone.

Repository pytest files remain outside the SQLBuild project's SQL `tests/` directory.

## Helpers

Custom Rules can import repository-owned helpers under `rules/` and these deterministic standard
library modules:

`abc`, `bisect`, `collections`, `copy`, `dataclasses`, `decimal`, `difflib`, `enum`, `fnmatch`,
`fractions`, `functools`, `graphlib`, `hashlib`, `heapq`, `itertools`, `json`, `math`,
`operator`, `pathlib`, `re`, `statistics`, `string`, `textwrap`, `types`, `typing`, and
`unicodedata`, plus `__future__` and `sqlbuild.rules`.

Modules that expose the clock, randomness, the process, or the network are rejected, including
`time`, `datetime`, `random`, `uuid`, `secrets`, `os`, `sys`, `subprocess`, `socket`, and
`importlib`. SQLBuild checks the `import` statements in each selected Rule's file and in the
helpers it imports, which are the files the Rules cache fingerprints. Other Python files under
`rules/`, such as tests or scratch scripts, are not checked.

Changing an imported helper invalidates the Rules that depend on it.

Only decorated functions register. Ordinary functions, constants, dataclasses, and classes remain
helpers.

## Deterministic inputs

The Rules cache can only reuse a result when the Rule depends on tracked inputs. SQLBuild runs
custom Rules in a separate host process and enforces that at runtime:

- Rules run with an empty environment, so `os.environ` is empty even when it is reached through
  an allowed module, for example `pathlib.os.environ`.
- The host starts with `PYTHONHASHSEED=0`, so iterating over a set of strings gives the same order
  on every run.
- While Rule code runs, opening files, listing directories, running commands, forking, network
  access, and `ctypes` are rejected, however they are reached. Loading a module outside the
  allowed list for the first time is rejected too.

A rejected operation fails the command with `non-hermetic custom rule <code> at <file>:<line>`, even
if the Rule catches the exception. These checks keep cached results correct. They are not a
security sandbox.

Read supported project text and structure through `ctx.project.tree`:

```python
text = ctx.project.tree.read_text("rules/requirements.yaml")
matches = ctx.project.tree.glob("models/*/interface/*.sql")
```

Both positive and negative observations are tracked. If `glob` returns no paths, adding a matching
path invalidates the cached result.

## Cache granularity

Cache identity incorporates the Rule implementation, imported helper closure, configured options,
subject, accessed compiler facts, tracked project observations, dialect, and compatibility
versions. Prefer model subjects for independent per-model checks and project subjects for genuine
cross-project invariants.
