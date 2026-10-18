#!/usr/bin/env bash
# Diagnostic (single cold run each): dbt parse/compile with the unit-test YAML removed.
set -u
D=/mnt/data/meas/dbt-compare/diag
DBT=/mnt/data/meas/dbt-compare/venv-dbt/bin/dbt
A=(--profiles-dir ../profiles --threads 4 --no-version-check --no-send-anonymous-usage-stats)
exec 9>/mnt/data/.native-build.lock
flock 9
cd "$D/dbt-nounit" || exit 1
for cmd in parse compile; do
  rm -rf target logs
  uptime >>"$D/uptime.log"
  /usr/bin/time -f '%e %U %S %M' -o "$D/${cmd}_nounit.time" "$DBT" "$cmd" "${A[@]}" >"$D/${cmd}_nounit.out" 2>&1
  uptime >>"$D/uptime.log"
done
rm -rf target logs
