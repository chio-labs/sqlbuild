#!/usr/bin/env bash
# Correctness matrix on 50-model projects: clean, a reference to a missing model, and a column the
# upstream model does not have. Run from the repository root. check_strict.py reads the logs.
#
# Usage: correctness.sh OUTROOT
# Environment: SQB, DBT_V2 and PYTHON, as for bench.sh; set DBT_CORE to add dbt Core rows. PYTHON
# must be able to import duckdb, pytest and the installed sqlbuild package (the generator uses the
# CI helpers).
set -u
OUT=$(realpath -m "$1")
HERE=$(cd "$(dirname "$0")" && pwd)
SQB=${SQB:-sqb}
DBT_CORE=${DBT_CORE:-}
DBT_V2=${DBT_V2:-dbt2}
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

# run KIND ID LABEL DIR COMMAND...: logs to logs/KIND.ID.log and the exit code to logs/KIND.ID.rc.
# Set KEEP_TARGET=1 to keep DIR's target/ from an earlier run.
run() {
  local kind=$1 id=$2 label=$3 dir=$4
  shift 4
  local log="$OUT/logs/$kind.$id.log"
  [ "${KEEP_TARGET:-0}" = 1 ] || rm -rf "$dir/target" "$dir/logs"
  (cd "$dir" && "$@" >"$log" 2>&1)
  local rc=$?
  echo "$rc" >"$OUT/logs/$kind.$id.rc"
  printf '| %s | %s | %s | %s |\n' "$kind" "$label" "$rc" "$(first_problem "$log")"
}

echo "| project | tool and command | exit code | first problem reported |"
echo "|---|---|---|---|"
for kind in clean ref column; do
  P=$OUT/p50-$kind
  DBTFLAGS=(--profiles-dir "$P/profiles" --no-version-check)
  STRICT=(--static-analysis strict)
  run "$kind" sqb_rules "sqb compile (rules on)" "$P/sqlbuild" "$SQB" --no-color compile
  run "$kind" sqb_norules "sqb compile (rules off)" "$P/sqlbuild-norules" "$SQB" --no-color compile
  run "$kind" v2_parse "dbt v2 parse" "$P/dbt" "$DBT_V2" parse "${DBTFLAGS[@]}"
  run "$kind" v2_compile "dbt v2 compile" "$P/dbt" "$DBT_V2" compile "${DBTFLAGS[@]}"
  run "$kind" v2_strict "dbt v2 compile --static-analysis strict" "$P/dbt" "$DBT_V2" compile \
    "${DBTFLAGS[@]}" "${STRICT[@]}"
  run "$kind" v2_strict_remote "dbt v2 compile --static-analysis strict, sources from warehouse" \
    "$P/dbt-remote" "$DBT_V2" compile "${DBTFLAGS[@]}" "${STRICT[@]}"
  if [ -n "$DBT_CORE" ]; then
    run "$kind" core_parse "dbt Core parse" "$P/dbt" "$DBT_CORE" parse "${DBTFLAGS[@]}"
    run "$kind" core_compile "dbt Core compile" "$P/dbt" "$DBT_CORE" compile "${DBTFLAGS[@]}"
  fi
done

# The cached and dirty strict modes must catch the column error on a warm run: build the cache on
# the clean project, copy in the seeded model, then compile again.
P=$OUT/p50-clean
DBTFLAGS=(--profiles-dir "$P/profiles" --no-version-check)
seeded=$(cd "$OUT/p50-column/dbt" && find models -name '*.sql' -exec grep -l missing_col {} +)
for mode in cached dirty; do
  W=$OUT/warm-$mode
  rm -rf "$W"
  cp -a "$P/dbt" "$W"
  run clean "v2_strict_${mode}_cold" "dbt v2 strict $mode: build the cache" "$W" "$DBT_V2" compile \
    "${DBTFLAGS[@]}" --static-analysis strict --partial-parse --partial-load
  cp "$OUT/p50-column/dbt/$seeded" "$W/$seeded"
  if [ "$mode" = cached ]; then
    flags=(--partial-parse --partial-load)
  else
    flags=(--partial-load --dirty)
  fi
  KEEP_TARGET=1 run column "v2_strict_${mode}_warm" "dbt v2 strict $mode: after seeding the error" \
    "$W" "$DBT_V2" compile "${DBTFLAGS[@]}" --static-analysis strict "${flags[@]}"
done
