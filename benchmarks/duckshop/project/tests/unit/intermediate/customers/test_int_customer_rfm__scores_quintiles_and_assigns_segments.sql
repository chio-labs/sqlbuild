TEST (name "int_customer_rfm__scores_quintiles_and_assigns_segments");

WITH __ref__int_customer_order_sequence AS (
  SELECT
    'A1' AS order_id,
    'A' AS customer_id,
    NULL AS placed_at,
    '2026-01-01'::DATE AS placed_date_local,
    NULL AS order_number,
    NULL AS is_first_order,
    NULL AS days_since_previous_order,
    NULL AS amount_usd,
    1000.0::DECIMAL(18, 2) AS lifetime_revenue_usd,
    NULL AS rolling_90d_revenue_usd,
    NULL AS previous_sales_channel,
    NULL AS is_channel_switch,
    NULL AS cohort_month
  UNION ALL
  SELECT
    'A2',
    'A',
    NULL,
    '2026-02-01'::DATE,
    NULL,
    NULL,
    NULL,
    NULL,
    2000.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'A3',
    'A',
    NULL,
    '2026-03-31'::DATE,
    NULL,
    NULL,
    NULL,
    NULL,
    3000.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'B1',
    'B',
    NULL,
    '2026-03-01'::DATE,
    NULL,
    NULL,
    NULL,
    NULL,
    450.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'B2',
    'B',
    NULL,
    '2026-03-20'::DATE,
    NULL,
    NULL,
    NULL,
    NULL,
    900.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'C1',
    'C',
    NULL,
    '2026-03-30'::DATE,
    NULL,
    NULL,
    NULL,
    NULL,
    100.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'D1',
    'D',
    NULL,
    '2025-12-01'::DATE,
    NULL,
    NULL,
    NULL,
    NULL,
    50.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'E1',
    'E',
    NULL,
    '2025-10-01'::DATE,
    NULL,
    NULL,
    NULL,
    NULL,
    200.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'E2',
    'E',
    NULL,
    '2025-11-01'::DATE,
    NULL,
    NULL,
    NULL,
    NULL,
    400.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__int_customer_rfm AS (
  SELECT
    'A' AS customer_id,
    0 AS days_since_last_order,
    3 AS order_count,
    1000.0::DECIMAL(18, 2) AS average_order_usd,
    '555' AS rfm_code,
    'CHAMPION' AS segment,
    TRUE AS is_vip
  UNION ALL
  SELECT
    'B' AS customer_id,
    11 AS days_since_last_order,
    2 AS order_count,
    450.0::DECIMAL(18, 2) AS average_order_usd,
    '334' AS rfm_code,
    'LOYAL' AS segment,
    FALSE AS is_vip
  UNION ALL
  SELECT
    'C' AS customer_id,
    1 AS days_since_last_order,
    1 AS order_count,
    100.0::DECIMAL(18, 2) AS average_order_usd,
    '412' AS rfm_code,
    'NEW' AS segment,
    FALSE AS is_vip
  UNION ALL
  SELECT
    'D' AS customer_id,
    120 AS days_since_last_order,
    1 AS order_count,
    50.0::DECIMAL(18, 2) AS average_order_usd,
    '221' AS rfm_code,
    'HIBERNATING' AS segment,
    FALSE AS is_vip
  UNION ALL
  SELECT
    'E' AS customer_id,
    150 AS days_since_last_order,
    2 AS order_count,
    200.0::DECIMAL(18, 2) AS average_order_usd,
    '143' AS rfm_code,
    'AT_RISK' AS segment,
    FALSE AS is_vip
)
