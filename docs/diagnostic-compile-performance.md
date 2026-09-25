# Diagnostic-heavy compile guards

Clean projects do not exercise diagnostic source mapping or error recovery. Run their
companion guards with:

```sh
make test-e2e-diagnostic-compile-performance
```

The 1,000-model CI job runs this target explicitly; these tests also carry the
`performance` and `cold_compile_performance` markers.

- Three models each contain more than 3,000 lines of macro-backed, wide CTE chains.
  Every model must report at least 50 errors and 50 warnings, and its dependent model
  must remain partially checked. The fresh-process wall ceiling is 20 seconds, with
  a separate 65-second process timeout to bound a severely regressed implementation.
- Position mapping uses one 4,000-line body and median timings for 100 and 200 spans.
  The cold-map plus larger run must take less than 8 seconds. Doubling the spans must
  stay within `2.8 * smaller_time + 0.1 seconds`.
- Cascades use 50 independently poisoned columns through 40- and 80-level DAGs.
  Every dependent initially produces type errors; recovery must leave precisely the
  50 root errors and attribute each transitive use correctly. Each run must take less
  than 35 seconds, and doubling depth must stay within `3 * smaller_time + 1 second`.

The scaling assertions and absolute headroom accommodate ordinary CI scheduling
variation. Counts, locations, partial coverage and recovery notes prevent a fast but
incomplete implementation from passing.

## Shared native validation

Compact analysis can validate its already-parsed statement with full semantic/type
options. SQLBuild reuses that result only when the authoritative input schema remains
identical; newly inferred inputs and target-specific quoted-identifier handling retain
the required subsequent validation. Native batches already use bounded Rayon parallelism.

Analysis-cache entries include binding diagnostics and are keyed by SQL, schema inputs,
dialect, declarations and analysis policy. Unchanged warm compiles do not repeat model
semantic validation. Empty validation batches return without entering native code.
SQL-test fixture interfaces are inferred in a single batch rather than repeated Python
AST walks.
