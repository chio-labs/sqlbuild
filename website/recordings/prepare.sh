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
  rename)
    # Build the model under its old name, so the tape can move it back to models/finance.
    cp -r "$examples/hero-shop" "$dir"
    cd "$dir"
    mkdir -p models/marts
    mv models/finance/daily_revenue.sql models/marts/revenue.sql
    sqb build >/dev/null ;;
  contract)
    # Give daily_revenue an enforced contract, then rename one of its columns in the SELECT.
    cp -r "$examples/waffle-shop" "$dir"
    cd "$dir"
    python3 - <<'PY'
path = "models/marts/daily_revenue.sql"
text = open(path).read()
text = text.replace("  materialized table,\n", "  materialized table,\n  contract enforced,\n", 1)
text = text.replace(
    "    revenue_date (nullable false),\n",
    "    revenue_date (type DATE, nullable false),\n"
    '    order_count (description "Orders placed that day"),\n'
    '    waffles_sold (description "Waffles sold that day"),\n'
    '    total_revenue_cents (description "Successful payments in cents"),\n'
    '    total_revenue_dollars (description "Successful payments in dollars"),\n'
    '    avg_order_value_cents (description "Average order value in cents"),\n',
    1,
)
text = text.replace("AS waffles_sold", "AS units_sold", 1)
open(path, "w").write(text)
PY
    ;;
  rules)
    # Make a mart read a raw source directly, which the project's layering rule forbids.
    cp -r "$examples/waffle-shop" "$dir"
    cd "$dir"
    sed -i 's/LEFT JOIN __ref("stg_payments") p/LEFT JOIN __source("raw__payments") p/' \
      models/marts/fact_orders.sql ;;
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
