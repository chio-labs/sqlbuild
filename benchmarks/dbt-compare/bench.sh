#!/usr/bin/env bash
# Cold 10k benchmark: sqlbuild vs dbt v2 (full `dbt` distribution and `dbt-oss`).
# Usage: bench.sh ROUNDS OUTDIR [VARIANT...]
# Every round runs each variant once (alternating order); all runs under the shared lock.
set -u
ROUNDS=$1
OUT=$2
shift 2
ROOT=/mnt/data/meas/dbt-compare
P=$ROOT/p10k
SQB=/mnt/data/sqlbuild-perf1/.venv/bin/sqlbuild-python
DBT=$ROOT/venv-dbt/bin/dbt
OSS=$ROOT/venv-dbt-oss/bin/dbt
DBTCOMMON=(--profiles-dir ../profiles --threads 4 --no-version-check --no-send-anonymous-usage-stats)
mkdir -p "$OUT"

declare -A CMD
CMD[sqb_rules]="cd $P/sqb-duck && SQLBUILD_CONCURRENCY=4 $SQB --project-dir $P/sqb-duck --no-color compile --json --no-cache"
CMD[sqb_norules]="cd $P/sqb-duck-norules && SQLBUILD_CONCURRENCY=4 $SQB --project-dir $P/sqb-duck-norules --no-color compile --json --no-cache"
CMD[dbt_parse]="cd $P/dbt && $DBT parse ${DBTCOMMON[*]}"
CMD[dbt_parse_nojson]="cd $P/dbt && $DBT parse ${DBTCOMMON[*]} --no-write-json"
CMD[dbt_compile_baseline]="cd $P/dbt && $DBT compile ${DBTCOMMON[*]}"
CMD[dbt_compile_baseline_nojson]="cd $P/dbt && $DBT compile ${DBTCOMMON[*]} --no-write-json"
CMD[dbt_compile_strict]="cd $P/dbt && $DBT compile ${DBTCOMMON[*]} --static-analysis strict"
CMD[dbt_compile_strict_nojson]="cd $P/dbt && $DBT compile ${DBTCOMMON[*]} --static-analysis strict --no-write-json"
CMD[dbt_compile_off]="cd $P/dbt && $DBT compile ${DBTCOMMON[*]} --static-analysis off"
CMD[dbt_compile_off_nojson]="cd $P/dbt && $DBT compile ${DBTCOMMON[*]} --static-analysis off --no-write-json"
CMD[dbt_lint]="cd $P/dbt && $DBT lint ${DBTCOMMON[*]}"
CMD[dbt_check]="cd $P/dbt && $DBT check ${DBTCOMMON[*]}"
CMD[oss_parse]="cd $P/dbt && $OSS parse ${DBTCOMMON[*]}"
CMD[oss_parse_nojson]="cd $P/dbt && $OSS parse ${DBTCOMMON[*]} --no-write-json"
CMD[oss_compile_default]="cd $P/dbt && $OSS compile ${DBTCOMMON[*]}"
CMD[oss_compile_default_nojson]="cd $P/dbt && $OSS compile ${DBTCOMMON[*]} --no-write-json"
CMD[oss_compile_strict]="cd $P/dbt && $OSS compile ${DBTCOMMON[*]} --static-analysis strict"
CMD[oss_compile_off]="cd $P/dbt && $OSS compile ${DBTCOMMON[*]} --static-analysis off"
CMD[oss_check]="cd $P/dbt && $OSS check ${DBTCOMMON[*]}"

VARIANTS=("$@")
[ ${#VARIANTS[@]} -eq 0 ] && VARIANTS=(sqb_rules sqb_norules dbt_parse dbt_parse_nojson
  dbt_compile_baseline dbt_compile_baseline_nojson dbt_compile_strict dbt_compile_strict_nojson
  dbt_compile_off dbt_compile_off_nojson dbt_lint dbt_check oss_parse oss_parse_nojson
  oss_compile_default oss_compile_default_nojson oss_compile_strict oss_compile_off oss_check)

clean() {
  rm -rf "$P"/sqb-duck/target "$P"/sqb-duck/logs "$P"/sqb-duck/.sqlbuild \
    "$P"/sqb-duck-norules/target "$P"/sqb-duck-norules/logs "$P"/sqb-duck-norules/.sqlbuild \
    "$P"/dbt/target "$P"/dbt/logs "$P"/dbt/dbt_packages "$P"/dbt/package-lock.yml
}

exec 9>/mnt/data/.native-build.lock
flock 9
echo "lock acquired $(date -Is)" >>"$OUT/uptime.log"
for round in $(seq 1 "$ROUNDS"); do
  n=${#VARIANTS[@]}
  for i in $(seq 0 $((n - 1))); do
    # alternate order: even rounds run the variant list reversed
    if [ $((round % 2)) -eq 0 ]; then v=${VARIANTS[$((n - 1 - i))]}; else v=${VARIANTS[$i]}; fi
    clean
    sync
    up_before=$(uptime)
    /usr/bin/time -f '%e %U %S %M' -o "$OUT/$v.r$round.time" \
      bash -c "${CMD[$v]}" >"$OUT/$v.r$round.out" 2>"$OUT/$v.r$round.err"
    rc=$?
    up_after=$(uptime)
    echo "$v r$round rc=$rc time=$(tail -1 "$OUT/$v.r$round.time")" | tee -a "$OUT/summary.log"
    printf '%s r%s before: %s\n%s r%s after:  %s\n' "$v" "$round" "$up_before" "$v" "$round" "$up_after" >>"$OUT/uptime.log"
  done
done
clean
