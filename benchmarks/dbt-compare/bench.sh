#!/usr/bin/env bash
# Dense-project compile benchmark: SQLBuild vs dbt Core (and optionally dbt v2).
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
#   DBT_CORE  dbt Core executable (default: dbt)
#   DBT_V2    dbt v2 executable; the v2_* variants are skipped when unset
#   PYTHON    Python used for the edit helper (default: python3)
#   LOAD_MAX  wait until the 1-minute load average is below this before each timed run (default 2)
#   LOAD_WAIT_MAX  give up waiting after this many seconds and run anyway (default 1800)
#   SCENARIOS which of warm, edit1 and edit100 to run after cold (default: all three)
set -u
ROOT=$(realpath "$1")
OUT=$(realpath -m "$2")
ROUNDS=$3
shift 3
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=$ROOT/work
SQB=${SQB:-sqb}
DBT_CORE=${DBT_CORE:-dbt}
DBT_V2=${DBT_V2:-}
PYTHON=${PYTHON:-python3}
LOAD_MAX=${LOAD_MAX:-2}
LOAD_WAIT_MAX=${LOAD_WAIT_MAX:-1800}
SCENARIOS=" ${SCENARIOS:-warm edit1 edit100} "
MODELS=$(find "$ROOT/sqlbuild/models" -name '*.sql' | wc -l)
export DBT_SEND_ANONYMOUS_USAGE_STATS=false
DBTFLAGS="--profiles-dir $ROOT/profiles --no-version-check"
mkdir -p "$OUT" "$WORK"

declare -A SRC CMD
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

VARIANTS=("$@")
if [ ${#VARIANTS[@]} -eq 0 ]; then
  VARIANTS=(sqb_rules sqb_norules core_parse core_compile)
  [ -n "$DBT_V2" ] && VARIANTS+=(v2_parse v2_compile)
fi

load1() { cut -d' ' -f1 /proc/loadavg; }

wait_quiet() {
  local waited=0
  while awk -v l="$(load1)" -v m="$LOAD_MAX" 'BEGIN { exit !(l >= m) }'; do
    if [ "$waited" -ge "$LOAD_WAIT_MAX" ]; then
      echo "load gate timed out at $(load1) after ${waited}s" >>"$OUT/uptime.log"
      return
    fi
    sleep 15
    waited=$((waited + 15))
  done
}

measure() {
  local v=$1 scenario=$2 round=$3 base
  base="$OUT/$v.$scenario.r$round"
  wait_quiet
  local before after
  before=$(load1)
  /usr/bin/time -f '%e %U %S %M' -o "$base.time" \
    bash -c "cd '$WORK/$v' && exec ${CMD[$v]}" >"$base.out" 2>"$base.err"
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
