TEST (name "rpt_customer_cohorts_monthly__tracks_retention_and_cumulative_revenue_per_cohort");

WITH __ref__int_customer_order_sequence AS (
  SELECT
    'O1' AS order_id,
    'C1' AS customer_id,
    NULL AS placed_at,
    '2026-01-05'::DATE AS placed_date_local,
    NULL AS order_number,
    NULL AS is_first_order,
    NULL AS days_since_previous_order,
    10.0::NUMBER(18, 2) AS amount_usd,
    NULL AS lifetime_revenue_usd,
    NULL AS rolling_90d_revenue_usd,
    NULL AS previous_sales_channel,
    NULL AS is_channel_switch,
    '2026-01-01'::DATE AS cohort_month
  UNION ALL
  SELECT
    'O2',
    'C1',
    NULL,
    '2026-01-20'::DATE,
    NULL,
    NULL,
    NULL,
    20.0::NUMBER(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-01-01'::DATE
  UNION ALL
  SELECT
    'O3',
    'C1',
    NULL,
    '2026-03-02'::DATE,
    NULL,
    NULL,
    NULL,
    30.0::NUMBER(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-01-01'::DATE
  UNION ALL
  SELECT
    'O4',
    'C2',
    NULL,
    '2026-01-10'::DATE,
    NULL,
    NULL,
    NULL,
    40.0::NUMBER(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-01-01'::DATE
  UNION ALL
  SELECT
    'O5',
    'C3',
    NULL,
    '2026-02-14'::DATE,
    NULL,
    NULL,
    NULL,
    50.0::NUMBER(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-02-01'::DATE
),

__expected__rpt_customer_cohorts_monthly AS (
  SELECT
    '2026-01+0' AS cohort_cell_key,
    2 AS cohort_size,
    2 AS active_customers,
    1.0::DECIMAL(9, 4) AS retention_rate,
    70.0::DECIMAL(18, 2) AS revenue_usd,
    35.0::DECIMAL(18, 2) AS cumulative_revenue_per_customer_usd
  UNION ALL
  SELECT
    '2026-01+2' AS cohort_cell_key,
    2 AS cohort_size,
    1 AS active_customers,
    0.5::DECIMAL(9, 4) AS retention_rate,
    30.0::DECIMAL(18, 2) AS revenue_usd,
    50.0::DECIMAL(18, 2) AS cumulative_revenue_per_customer_usd
  UNION ALL
  SELECT
    '2026-02+0' AS cohort_cell_key,
    1 AS cohort_size,
    1 AS active_customers,
    1.0::DECIMAL(9, 4) AS retention_rate,
    50.0::DECIMAL(18, 2) AS revenue_usd,
    50.0::DECIMAL(18, 2) AS cumulative_revenue_per_customer_usd
),

__assert__cohort_cell_key_is_unique_and_present AS (
  SELECT t.cohort_cell_key
  FROM __ref("rpt_customer_cohorts_monthly") AS t
  GROUP BY
    t.cohort_cell_key
  HAVING
    COUNT(*) > 1
    OR t.cohort_cell_key IS NULL
)
