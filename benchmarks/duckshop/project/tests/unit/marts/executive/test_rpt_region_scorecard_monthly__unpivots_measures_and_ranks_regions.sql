TEST (name "rpt_region_scorecard_monthly__unpivots_measures_and_ranks_regions");

WITH __ref__rpt_daily_sales_by_region AS (
  SELECT
    'EU:2026-03-10' AS sales_day_key,
    '2026-03-10'::DATE AS placed_date_local,
    'EU' AS region_code,
    2 AS order_count,
    NULL AS customer_count,
    1 AS first_order_count,
    NULL AS units,
    100.0::DECIMAL(18, 2) AS revenue_usd,
    NULL AS discount_usd,
    NULL AS average_order_usd,
    NULL AS revenue_same_day_last_week_usd,
    NULL AS revenue_trailing_28d_usd
  UNION ALL
  SELECT
    'EU:2026-03-20',
    '2026-03-20'::DATE,
    'EU',
    1,
    NULL,
    0,
    NULL,
    50.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'US:2026-03-05',
    '2026-03-05'::DATE,
    'US',
    1,
    NULL,
    1,
    NULL,
    200.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__rpt_revenue_recognition_monthly AS (
  SELECT
    '2026-03:EU'::TEXT AS recognition_month_key,
    '2026-03-01'::DATE AS recognition_month,
    'EU'::TEXT AS region_code,
    NULL AS product_usd,
    NULL AS refund_usd,
    10.0::DECIMAL(18, 2) AS subscription_usd,
    NULL AS net_revenue_usd,
    0.1::DECIMAL(9, 4) AS refund_ratio
),

__expected__rpt_region_scorecard_monthly AS (
  SELECT
    '2026-03:EU:orders'::TEXT AS scorecard_key,
    3.0::DECIMAL(18, 4) AS measure_value,
    1 AS rank_among_regions
  UNION ALL
  SELECT
    '2026-03:US:orders'::TEXT AS scorecard_key,
    1.0::DECIMAL(18, 4) AS measure_value,
    2 AS rank_among_regions
  UNION ALL
  SELECT
    '2026-03:EU:revenue_usd'::TEXT AS scorecard_key,
    150.0::DECIMAL(18, 4) AS measure_value,
    2 AS rank_among_regions
  UNION ALL
  SELECT
    '2026-03:US:revenue_usd'::TEXT AS scorecard_key,
    200.0::DECIMAL(18, 4) AS measure_value,
    1 AS rank_among_regions
  UNION ALL
  SELECT
    '2026-03:EU:first_orders'::TEXT AS scorecard_key,
    1.0::DECIMAL(18, 4) AS measure_value,
    1 AS rank_among_regions
  UNION ALL
  SELECT
    '2026-03:US:first_orders'::TEXT AS scorecard_key,
    1.0::DECIMAL(18, 4) AS measure_value,
    1 AS rank_among_regions
  UNION ALL
  SELECT
    '2026-03:EU:average_order_usd'::TEXT AS scorecard_key,
    50.0::DECIMAL(18, 4) AS measure_value,
    2 AS rank_among_regions
  UNION ALL
  SELECT
    '2026-03:US:average_order_usd'::TEXT AS scorecard_key,
    200.0::DECIMAL(18, 4) AS measure_value,
    1 AS rank_among_regions
  UNION ALL
  SELECT
    '2026-03:EU:refund_ratio'::TEXT AS scorecard_key,
    0.1::DECIMAL(18, 4) AS measure_value,
    1 AS rank_among_regions
  UNION ALL
  SELECT
    '2026-03:US:refund_ratio'::TEXT AS scorecard_key,
    0.0::DECIMAL(18, 4) AS measure_value,
    2 AS rank_among_regions
  UNION ALL
  SELECT
    '2026-03:EU:subscription_usd'::TEXT AS scorecard_key,
    10.0::DECIMAL(18, 4) AS measure_value,
    1 AS rank_among_regions
  UNION ALL
  SELECT
    '2026-03:US:subscription_usd'::TEXT AS scorecard_key,
    0.0::DECIMAL(18, 4) AS measure_value,
    2 AS rank_among_regions
),

__assert__scorecard_key_is_unique_and_present AS (
  SELECT t.scorecard_key
  FROM __ref("rpt_region_scorecard_monthly") AS t
  GROUP BY
    t.scorecard_key
  HAVING
    COUNT(*) > 1
    OR t.scorecard_key IS NULL
)
