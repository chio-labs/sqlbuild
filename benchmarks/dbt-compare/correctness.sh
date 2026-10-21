#!/usr/bin/env bash
# Correctness matrix on 50-model projects: clean, a reference to a missing model, and a column the
# upstream model does not have. Run from the repository root.
#
# Usage: correctness.sh OUTROOT
# Environment: SQB, DBT_CORE, DBT_V2 (optional) and PYTHON, as for bench.sh. PYTHON must be able to
# import duckdb, pytest and the installed sqlbuild package (the generator uses the CI helpers).
set -u
OUT=$(realpath -m "$1")
HERE=$(cd "$(dirname "$0")" && pwd)
SQB=${SQB:-sqb}
DBT_CORE=${DBT_CORE:-dbt}
DBT_V2=${DBT_V2:-}
PYTHON=${PYTHON:-python3}
export DBT_SEND_ANONYMOUS_USAGE_STATS=false
mkdir -p "$OUT/logs"

for kind in clean ref column; do
  args=()
  [ "$kind" != clean ] && args=(--seed-error "$kind")
  "$PYTHON" "$HERE/write_dbt_dense.py" --models 50 --out "$OUT/p50-$kind" "${args[@]}" || exit 1
done

first_problem() {
  sed 's/\x1b\[[0-9;]*m//g' "$1" | grep -m1 -E 'error\[|\[error\]|depends on a node' |
    sed -E 's/^ +//' | cut -c1-140
}

run() {
  local kind=$1 label=$2 dir=$3
  shift 3
  local log="$OUT/logs/$kind.$label.log"
  rm -rf "$dir/target" "$dir/logs"
  (cd "$dir" && "$@" >"$log" 2>&1)
  local rc=$?
  printf '| %s | %s | %s | %s |\n' "$kind" "$label" "$rc" "$(first_problem "$log")"
}

echo "| project | tool and command | exit code | first problem reported |"
echo "|---|---|---|---|"
for kind in clean ref column; do
  P=$OUT/p50-$kind
  DBTFLAGS=(--profiles-dir "$P/profiles" --no-version-check)
  run "$kind" "sqb compile (rules on)" "$P/sqlbuild" "$SQB" --no-color compile
  run "$kind" "sqb compile (rules off)" "$P/sqlbuild-norules" "$SQB" --no-color compile
  run "$kind" "dbt Core parse" "$P/dbt" "$DBT_CORE" parse "${DBTFLAGS[@]}"
  run "$kind" "dbt Core compile" "$P/dbt" "$DBT_CORE" compile "${DBTFLAGS[@]}"
  if [ -n "$DBT_V2" ]; then
    run "$kind" "dbt v2 parse" "$P/dbt" "$DBT_V2" parse "${DBTFLAGS[@]}"
    run "$kind" "dbt v2 compile" "$P/dbt" "$DBT_V2" compile "${DBTFLAGS[@]}"
    run "$kind" "dbt v2 compile --static-analysis strict" "$P/dbt" "$DBT_V2" compile \
      "${DBTFLAGS[@]}" --static-analysis strict
  fi
done
