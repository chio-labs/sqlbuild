TEST (name "rpt_revenue_recognition_monthly__pivots_revenue_streams_per_region_month");

WITH __ref__int_revenue_recognition_daily AS (
  SELECT
    '2026-03-05:EU:product' AS recognition_key,
    '2026-03-05'::DATE AS recognition_date,
    'EU' AS region_code,
    'product' AS revenue_stream,
    100.0::DECIMAL(18, 2) AS revenue_usd,
    NULL AS document_count,
    NULL AS month_to_date_usd,
    NULL AS trailing_7d_usd,
    NULL AS share_of_day
  UNION ALL
  SELECT
    '2026-03-20:EU:product',
    '2026-03-20'::DATE,
    'EU',
    'product',
    50.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    '2026-03-21:EU:refund',
    '2026-03-21'::DATE,
    'EU',
    'refund',
    -15.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    '2026-03-10:EU:subscription',
    '2026-03-10'::DATE,
    'EU',
    'subscription',
    10.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    '2026-03-02:US:subscription',
    '2026-03-02'::DATE,
    'US',
    'subscription',
    20.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__rpt_revenue_recognition_monthly AS (
  SELECT
    '2026-03:EU'::TEXT AS recognition_month_key,
    150.0::DECIMAL(18, 2) AS product_usd,
    -15.0::DECIMAL(18, 2) AS refund_usd,
    10.0::DECIMAL(18, 2) AS subscription_usd,
    145.0::DECIMAL(18, 2) AS net_revenue_usd,
    0.1::DECIMAL(9, 4) AS refund_ratio
  UNION ALL
  SELECT
    '2026-03:US'::TEXT AS recognition_month_key,
    0.0::DECIMAL(18, 2) AS product_usd,
    0.0::DECIMAL(18, 2) AS refund_usd,
    20.0::DECIMAL(18, 2) AS subscription_usd,
    20.0::DECIMAL(18, 2) AS net_revenue_usd,
    CAST(NULL AS DECIMAL(9, 4)) AS refund_ratio
),

__assert__recognition_month_key_is_unique_and_present AS (
  SELECT t.recognition_month_key
  FROM __ref("rpt_revenue_recognition_monthly") AS t
  GROUP BY
    t.recognition_month_key
  HAVING
    COUNT(*) > 1
    OR t.recognition_month_key IS NULL
)
