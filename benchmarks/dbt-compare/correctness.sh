#!/usr/bin/env bash
# Correctness checks on the 50-model clean and seeded-error projects.
set -u
ROOT=/mnt/data/meas/dbt-compare
SQB=/mnt/data/sqlbuild-perf1/.venv/bin/sqlbuild-python
OUT=$ROOT/correctness
mkdir -p "$OUT"
exec 9>/mnt/data/.native-build.lock
flock 9
for proj in p50 p50err; do
  P=$ROOT/$proj
  for v in sqb-duck sqb-duck-norules; do
    rm -rf "$P/$v/target" "$P/$v/.sqlbuild"
    SQLBUILD_CONCURRENCY=4 "$SQB" --project-dir "$P/$v" --no-color compile --json --no-cache \
      >"$OUT/$proj.$v.json" 2>"$OUT/$proj.$v.err"
    echo "$proj $v rc=$?"
  done
  for dist in dbt dbt-oss; do
    for sa in default baseline strict off; do
      for cmd in parse compile; do
        rm -rf "$P/dbt/target" "$P/dbt/logs"
        args=()
        [ "$sa" != default ] && args=(--static-analysis "$sa")
        (cd "$P/dbt" && "$ROOT/venv-$dist/bin/dbt" "$cmd" --profiles-dir ../profiles --threads 4 \
          --no-version-check "${args[@]}" >"$OUT/$proj.$dist.$cmd.$sa.log" 2>&1)
        echo "$proj $dist $cmd $sa rc=$?"
      done
    done
  done
done
