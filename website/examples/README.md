# Landing page examples

The projects that produced the real `sqb` output on the landing page, so it can be regenerated when
the CLI changes. Build output, logs and DuckDB files are not kept; every project runs locally on
DuckDB.

| Project | Landing page |
|---------|--------------|
| `waffle-shop/` | Steps 02 to 07. It is `sqb playground waffle-shop` plus the custom Rule in `rules/layers.py` and its test, the scoped enum and macros under `models/marts/_sqlbuild/`, and the renamed `daily_order_rollup` model. |
| `tidy-shop/` | Step 08, the janitor. |
| `hero-shop/` | The hero: a model moved and renamed. |

## Step 08: janitor

`tidy-shop` shows the state after the stale model was removed. To regenerate the output, restore it
first:

```bash
cd tidy-shop
cat > models/weekly_revenue.sql <<'SQL'
MODEL (
  materialized table,
);

SELECT DATE_TRUNC('week', revenue_date) AS revenue_week, SUM(total_revenue_cents) AS total_revenue_cents
FROM __ref("daily_revenue")
GROUP BY 1
SQL
sqb build
rm models/weekly_revenue.sql
sqb janitor
```

## Hero: move and rename

`hero-shop` shows the state after the move. The model started as `models/marts/revenue.sql`:

```bash
cd hero-shop
mkdir -p models/marts
mv models/finance/daily_revenue.sql models/marts/revenue.sql
sqb build
mv models/marts/revenue.sql models/finance/daily_revenue.sql
sqb plan
```
