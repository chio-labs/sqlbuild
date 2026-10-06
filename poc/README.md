# Native compile floor proof of concept (throwaway, not for merge)

Measures how fast a compile could be if SQLBuild's compiler were native, keeping only user
extension points (macros, providers, Python models, custom rules) in Python.

- `capture/capture_native.py` runs `sqb compile` in-process and records every native analysis
  call (catalog updates, compact analysis batches, normalization, binding validation) to JSONL.
- `capture/capture_render.py` runs `sqb compile` in-process and dumps each rendered model input
  (query SQL, references, macro dependencies, config values) as the verification oracle.
- `sqlbuild-floor` (Rust, workspace member) holds the benchmarks:
  - `analysis_replay OPS_JSONL [--verify] [--parse] [--threads 1,2,4] [--runs 5]` replays the
    captured analysis inputs in pure Rust in dataflow order and checks every result.
  - `render_floor PROJECT [--verify RENDER_JSON] [--threads N] [--site-packages DIR]` discovers a
    project, layers config, substitutes vars and declarations, calls user macros through an
    embedded interpreter (memoised) and extracts references.
  - `boundary_bench calls|startup` measures Rust -> Python -> Rust call cost and interpreter
    start-up.
  - `bare_start` is a minimal native binary for CLI start-up comparison.

The `poc` feature of `sqlbuild-rules-native` exposes a pure-Rust facade (`src/poc.rs`) over the
existing native catalog, header parser, var substitution and reference extraction. It is never
enabled in shipped builds.

Build: `cargo build --release -p sqlbuild-floor` with `PYO3_PYTHON` pointing at the interpreter
whose shared library should be embedded.
