#!/usr/bin/env bash
# Record one demo to out/<demo>.gif and out/<demo>.mp4. Usage: record.sh <demo>
# Uses the sqb on PATH; set SQB_BIN to a directory containing another sqb to use that instead.
set -euo pipefail
demo="$1"
here="$(cd "$(dirname "$0")" && pwd)"
if [[ -n "${SQB_BIN:-}" ]]; then
  export PATH="$SQB_BIN:$PATH"
fi
"$here/prepare.sh" "$demo"
mkdir -p "$here/out"
cd "$here"
# Headless Chromium's sandbox is unavailable in many containers and CI runners.
VHS_NO_SANDBOX="${VHS_NO_SANDBOX:-true}" vhs "tapes/$demo.tape"
