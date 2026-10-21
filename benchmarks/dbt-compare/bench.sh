#!/usr/bin/env bash
# Dense-project compile benchmark: SQLBuild vs dbt v2 and dbt Core.
#
# Usage: bench.sh PROJECT_ROOT OUTDIR ROUNDS [VARIANT...]
#
# PROJECT_ROOT is a directory written by write_dbt_dense.py. Each round runs every variant once, in
# alternating order (odd rounds forward, even rounds reversed). For each variant and round:
#   1. copy the pristine project into PROJECT_ROOT/work/VARIANT (no target/, no caches)
#   2. cold:    first compile or parse
#   3. warm:    the same command again, nothing changed
#   4. edit1:   edit one model's SQL body, run again
#   5. edit100: edit 100 models' SQL bodies (1% of 10,000), run again
#
# Environment:
#   SQB       sqb executable (default: sqb)
#   DBT_V2    dbt v2 executable (default: dbt2)
#   DBT_CORE  dbt Core executable, for the core_* variants (default: dbt)
#   PYTHON    Python used for the edit helper (default: python3)
#   SCENARIOS which of warm, edit1 and edit100 to run after cold (default: all three)
#
# Default variants: sqb_rules sqb_norules sqb_rules_full v2_compile_cached v2_compile_strict_cached
# v2_compile_dirty v2_compile_strict_dirty v2_compile v2_compile_strict. Also available: v2_parse
# core_parse core_compile.
set -u
ROOT=$(realpath "$1")
OUT=$(realpath -m "$2")
ROUNDS=$3
shift 3
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=$ROOT/work
SQB=${SQB:-sqb}
DBT_CORE=${DBT_CORE:-dbt}
DBT_V2=${DBT_V2:-dbt2}
PYTHON=${PYTHON:-python3}
SCENARIOS=" ${SCENARIOS:-warm edit1 edit100} "
MODELS=$(find "$ROOT/sqlbuild/models" -name '*.sql' | wc -l)
export DBT_SEND_ANONYMOUS_USAGE_STATS=false
DBTFLAGS="--profiles-dir $ROOT/profiles --no-version-check"
# CMD_COLD overrides CMD for the cold scenario.
declare -A SRC CMD CMD_COLD
SRC[sqb_rules]=sqlbuild
CMD[sqb_rules]="$SQB --no-color compile"
SRC[sqb_norules]=sqlbuild-norules
CMD[sqb_norules]="$SQB --no-color compile"
SRC[sqb_rules_full]=sqlbuild
CMD[sqb_rules_full]="env SQLBUILD_DISABLE_COMPILE_REUSE=1 SQLBUILD_DISABLE_DELTA_COMPILE=1 $SQB --no-color compile"
SRC[core_parse]=dbt
CMD[core_parse]="$DBT_CORE parse $DBTFLAGS"
SRC[core_compile]=dbt
CMD[core_compile]="$DBT_CORE compile $DBTFLAGS"
SRC[v2_parse]=dbt
CMD[v2_parse]="$DBT_V2 parse $DBTFLAGS"
SRC[v2_compile]=dbt
CMD[v2_compile]="$DBT_V2 compile $DBTFLAGS"
SRC[v2_compile_strict]=dbt
CMD[v2_compile_strict]="$DBT_V2 compile $DBTFLAGS --static-analysis strict"
# dbt v2's parse cache is off by default. --partial-parse keeps it under target/private/metadata/;
# --partial-load loads it faster. --dirty selects only nodes whose files changed since the last
# --partial-parse run, plus their descendants, so its cold run builds the cache without it.
SRC[v2_compile_cached]=dbt
CMD[v2_compile_cached]="$DBT_V2 compile $DBTFLAGS --partial-parse --partial-load"
SRC[v2_compile_strict_cached]=dbt
CMD[v2_compile_strict_cached]="$DBT_V2 compile $DBTFLAGS --static-analysis strict --partial-parse --partial-load"
SRC[v2_compile_dirty]=dbt
CMD_COLD[v2_compile_dirty]="$DBT_V2 compile $DBTFLAGS --partial-parse --partial-load"
CMD[v2_compile_dirty]="$DBT_V2 compile $DBTFLAGS --partial-load --dirty"
SRC[v2_compile_strict_dirty]=dbt
CMD_COLD[v2_compile_strict_dirty]="$DBT_V2 compile $DBTFLAGS --static-analysis strict --partial-parse --partial-load"
CMD[v2_compile_strict_dirty]="$DBT_V2 compile $DBTFLAGS --static-analysis strict --partial-load --dirty"

VARIANTS=("$@")
if [ ${#VARIANTS[@]} -eq 0 ]; then
  VARIANTS=(sqb_rules sqb_norules sqb_rules_full v2_compile_cached v2_compile_strict_cached
    v2_compile_dirty v2_compile_strict_dirty v2_compile v2_compile_strict)
fi
for v in "${VARIANTS[@]}"; do
  if [ -z "${CMD[$v]+set}" ]; then
    echo "unknown variant: $v" >&2
    exit 2
  fi
done
mkdir -p "$OUT" "$WORK"

load1() { cut -d' ' -f1 /proc/loadavg; }

measure() {
  local v=$1 scenario=$2 round=$3 base cmd
  base="$OUT/$v.$scenario.r$round"
  cmd=${CMD[$v]}
  if [ "$scenario" = cold ] && [ -n "${CMD_COLD[$v]+set}" ]; then cmd=${CMD_COLD[$v]}; fi
  echo "$cmd" >"$base.cmd"
  local before after
  before=$(load1)
  /usr/bin/time -f '%e %U %S %M' -o "$base.time" \
    bash -c "cd '$WORK/$v' && exec $cmd" >"$base.out" 2>"$base.err"
  echo $? >"$base.rc"
  after=$(load1)
  echo "$v $scenario r$round load $before $after" >>"$OUT/uptime.log"
  echo "$v $scenario r$round rc=$(cat "$base.rc") time=$(tail -1 "$base.time") load=$before/$after" |
    tee -a "$OUT/summary.log"
}

edit() {
  "$PYTHON" "$HERE/edit_models.py" "$WORK/$1" --models "$MODELS" --count "$2" --value "$3"
}

for round in $(seq 1 "$ROUNDS"); do
  n=${#VARIANTS[@]}
  for i in $(seq 0 $((n - 1))); do
    if [ $((round % 2)) -eq 0 ]; then v=${VARIANTS[$((n - 1 - i))]}; else v=${VARIANTS[$i]}; fi
    rm -rf "${WORK:?}/$v"
    cp -a "$ROOT/${SRC[$v]}" "$WORK/$v"
    sync
    # Let the copy age past file-change heuristics that treat just-written files specially.
    sleep 5
    measure "$v" cold "$round"
    [[ $SCENARIOS == *" warm "* ]] && measure "$v" warm "$round"
    if [[ $SCENARIOS == *" edit1 "* ]]; then
      edit "$v" 1 $((round * 10 + 1))
      measure "$v" edit1 "$round"
    fi
    if [[ $SCENARIOS == *" edit100 "* ]]; then
      edit "$v" 100 $((round * 10 + 2))
      measure "$v" edit100 "$round"
    fi
  done
done
rm -rf "${WORK:?}"
