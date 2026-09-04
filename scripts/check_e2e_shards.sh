#!/usr/bin/env bash

set -euo pipefail

readonly marker_expression="not real_warehouse and not dbt and not performance"
readonly e2e_root="tests/e2e"

declare -a shard_names=()
declare -a root_names=()
declare -a root_shards=()
declare -A seen_shards=()
declare -A seen_roots=()

while (( $# > 0 )); do
  if [[ "$1" != "--shard" || $# -lt 3 ]]; then
    echo "usage: $0 --shard NAME PATH [PATH ...] [--shard ...]" >&2
    exit 2
  fi

  shard="$2"
  shift 2
  if [[ -n "${seen_shards[$shard]:-}" ]]; then
    echo "duplicate shard name: $shard" >&2
    exit 1
  fi
  seen_shards[$shard]=1
  shard_names+=("$shard")

  path_count=0
  while (( $# > 0 )) && [[ "$1" != "--shard" ]]; do
    root="$1"
    shift
    ((path_count += 1))
    if [[ -n "${seen_roots[$root]:-}" ]]; then
      echo "path is declared more than once: $root" >&2
      exit 1
    fi
    if [[ "$root" != "$e2e_root/"* ]]; then
      echo "path is outside $e2e_root: $root" >&2
      exit 1
    fi
    if [[ ! -e "$root" ]]; then
      echo "path does not exist: $root" >&2
      exit 1
    fi
    seen_roots[$root]=1
    root_names+=("$root")
    root_shards+=("$shard")
  done
  if (( path_count == 0 )); then
    echo "shard has no paths: $shard" >&2
    exit 1
  fi
done

mkdir -p /tmp/opencode
collection_file=$(mktemp /tmp/opencode/check-e2e-shards-XXXXXX.log)
trap 'rm -f "$collection_file"' EXIT

if ! uv run pytest "$e2e_root" --collect-only -q --color=no \
  -m "$marker_expression" >"$collection_file"; then
  cat "$collection_file"
  echo "DuckDB E2E pytest collection failed" >&2
  exit 1
fi

declare -A counts=()
declare -A invalid_files=()
test_count=0
while IFS= read -r node_id; do
  if [[ "$node_id" != "$e2e_root/"*::* ]]; then
    continue
  fi

  ((test_count += 1))
  test_file="${node_id%%::*}"
  owner_count=0
  owner=""
  ownership=""
  for index in "${!root_names[@]}"; do
    root="${root_names[$index]}"
    if [[ "$test_file" == "$root" || "$test_file" == "$root/"* ]]; then
      ((owner_count += 1))
      owner="${root_shards[$index]}"
      ownership+="${ownership:+, }$owner:$root"
    fi
  done

  if (( owner_count != 1 )); then
    invalid_files[$test_file]="${ownership:-none}"
  else
    counts[$owner]=$(( ${counts[$owner]:-0} + 1 ))
  fi
done <"$collection_file"

if (( test_count == 0 )); then
  echo "pytest collection returned no deterministic DuckDB E2E tests" >&2
  exit 1
fi

if (( ${#invalid_files[@]} > 0 )); then
  echo "DuckDB E2E shard coverage failed:" >&2
  for test_file in "${!invalid_files[@]}"; do
    echo "  - $test_file owners: ${invalid_files[$test_file]}" >&2
  done
  exit 1
fi

echo "DuckDB E2E shard coverage passed ($test_count tests):"
for shard in "${shard_names[@]}"; do
  echo "  $shard: ${counts[$shard]:-0}"
done
