#!/usr/bin/env bash
# Build a clean scratch project for one demo. Usage: prepare.sh <demo>
set -euo pipefail
demo="$1"
here="$(cd "$(dirname "$0")" && pwd)"
examples="$here/../examples"
dir="$here/scratch/$demo"
rm -rf "$dir"
mkdir -p "$here/scratch"
case "$demo" in
  quickstart)
    mkdir -p "$dir" ;;
  rename)
    # Build the model under its old name, so the tape can move and rename it.
    cp -r "$examples/hero-shop" "$dir"
    cd "$dir"
    mkdir -p models/marts
    mv models/finance/daily_revenue.sql models/marts/revenue.sql
    rmdir models/finance
    sqb build >/dev/null ;;
  scope)
    cp -r "$examples/waffle-shop" "$dir"
    cd "$dir"
    sqb compile >/dev/null || true ;;
  janitor)
    # Build a model, then remove it, so the janitor has a stale table to archive.
    cp -r "$examples/tidy-shop" "$dir"
    cd "$dir"
    cat > models/weekly_revenue.sql <<'SQL'
MODEL (
  materialized table,
);

SELECT DATE_TRUNC('week', revenue_date) AS revenue_week, SUM(total_revenue_cents) AS total_revenue_cents
FROM __ref("daily_revenue")
GROUP BY 1
SQL
    sqb build >/dev/null
    rm models/weekly_revenue.sql ;;
  compile)
    # Introduce an unknown column and a type mismatch, checked against enforced source contracts.
    cp -r "$examples/waffle-shop" "$dir"
    cd "$dir"
    python3 - <<'PY'
import re

path = "sources/raw.yml"
text = open(path).read()
for name in ("raw__customers", "raw__orders"):
    text = re.sub(rf"(\n(\s*)- name: {name}\n)", rf"\1\2  contract: enforced\n", text, count=1)
open(path, "w").write(text)

path = "models/marts/fact_orders.sql"
text = open(path).read()
text = text.replace("o.quantity,", "o.qty,", 1).rstrip() + "\nWHERE o.ordered_at > 5\n"
open(path, "w").write(text)
PY
    ;;
  *)
    echo "unknown demo: $demo" >&2
    exit 2 ;;
esac
