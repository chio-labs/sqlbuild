SCENARIO (
  description "Order sales and recognised revenue combine into one monthly scorecard per region",
  tags ["cross-area", "orders", "finance", "executive"],
);

WITH __ref__fct_orders AS (
  SELECT
    'O1' AS order_id,
    'C1' AS customer_id,
    'EU' AS region_code,
    NULL AS placed_at,
    '2026-03-10'::DATE AS placed_date_local,
    'DELIVERED' AS order_status,
    NULL AS sales_channel,
    1 AS units,
    NULL AS currency_code,
    NULL AS amount,
    60.0::NUMBER(18, 2) AS amount_usd,
    NULL AS rate_to_usd,
    NULL AS rate_date,
    NULL AS gross_amount_usd,
    0.0::NUMBER(18, 2) AS discount_amount_usd,
    NULL AS tax_amount_usd,
    NULL AS promo_code,
    NULL AS utm_source,
    NULL AS utm_medium,
    NULL AS utm_campaign,
    NULL AS basket_size,
    NULL AS order_number,
    TRUE AS is_first_order,
    NULL AS first_paid_at,
    NULL AS first_delivered_at,
    NULL AS hours_paid_to_shipped,
    NULL AS captured_minor,
    NULL AS refunded_minor,
    NULL AS net_collected_minor,
    NULL AS is_fully_refunded
  UNION ALL
  SELECT
    'O2',
    'C2',
    'EU',
    NULL,
    '2026-03-10'::DATE,
    'DELIVERED',
    NULL,
    1,
    NULL,
    NULL,
    40.0::NUMBER(18, 2),
    NULL,
    NULL,
    NULL,
    0.0::NUMBER(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'O3',
    'C2',
    'EU',
    NULL,
    '2026-03-20'::DATE,
    'DELIVERED',
    NULL,
    1,
    NULL,
    NULL,
    50.0::NUMBER(18, 2),
    NULL,
    NULL,
    NULL,
    0.0::NUMBER(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'O4',
    'C3',
    'US',
    NULL,
    '2026-03-05'::DATE,
    'DELIVERED',
    NULL,
    1,
    NULL,
    NULL,
    200.0::NUMBER(18, 2),
    NULL,
    NULL,
    NULL,
    0.0::NUMBER(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_revenue_recognition_daily AS (
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
),

__expected__rpt_revenue_recognition_monthly AS (
  SELECT
    '2026-03:EU'::TEXT AS recognition_month_key,
    150.0::DECIMAL(18, 2) AS product_usd,
    -15.0::DECIMAL(18, 2) AS refund_usd,
    10.0::DECIMAL(18, 2) AS subscription_usd,
    145.0::DECIMAL(18, 2) AS net_revenue_usd,
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
)
