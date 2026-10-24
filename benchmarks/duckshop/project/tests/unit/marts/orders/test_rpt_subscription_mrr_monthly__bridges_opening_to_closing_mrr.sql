TEST (name "rpt_subscription_mrr_monthly__bridges_opening_to_closing_mrr");

WITH __ref__int_subscription_mrr_daily AS (
  SELECT
    'S1:2026-01-15' AS subscription_day_key,
    'S1' AS subscription_id,
    NULL AS customer_id,
    '2026-01-15'::DATE AS calendar_date,
    10.0::DECIMAL(18, 4) AS mrr_usd,
    TRUE AS is_first_day
  UNION ALL
  SELECT
    'S1:2026-01-31',
    'S1',
    NULL,
    '2026-01-31'::DATE,
    10.0::DECIMAL(18, 4),
    FALSE
  UNION ALL
  SELECT
    'S1:2026-02-28',
    'S1',
    NULL,
    '2026-02-28'::DATE,
    10.0::DECIMAL(18, 4),
    FALSE
  UNION ALL
  SELECT
    'S1:2026-03-31',
    'S1',
    NULL,
    '2026-03-31'::DATE,
    10.0::DECIMAL(18, 4),
    FALSE
  UNION ALL
  SELECT
    'S2:2026-02-10',
    'S2',
    NULL,
    '2026-02-10'::DATE,
    20.0::DECIMAL(18, 4),
    TRUE
  UNION ALL
  SELECT
    'S2:2026-02-28',
    'S2',
    NULL,
    '2026-02-28'::DATE,
    20.0::DECIMAL(18, 4),
    FALSE
  UNION ALL
  SELECT
    'S3:2026-03-05',
    'S3',
    NULL,
    '2026-03-05'::DATE,
    5.0::DECIMAL(18, 4),
    TRUE
  UNION ALL
  SELECT
    'S3:2026-03-31',
    'S3',
    NULL,
    '2026-03-31'::DATE,
    5.0::DECIMAL(18, 4),
    FALSE
),

__expected__rpt_subscription_mrr_monthly AS (
  SELECT
    '2026-01-01'::DATE AS month_start,
    10.0::DECIMAL(18, 2) AS closing_mrr_usd,
    0.0::DECIMAL(18, 2) AS opening_mrr_usd,
    10.0::DECIMAL(18, 2) AS new_mrr_usd,
    0.0::DECIMAL(18, 2) AS churned_mrr_usd,
    10.0::DECIMAL(18, 2) AS net_change_usd,
    1 AS active_subscribers,
    1 AS new_subscribers
  UNION ALL
  SELECT
    '2026-02-01'::DATE AS month_start,
    30.0::DECIMAL(18, 2) AS closing_mrr_usd,
    10.0::DECIMAL(18, 2) AS opening_mrr_usd,
    20.0::DECIMAL(18, 2) AS new_mrr_usd,
    0.0::DECIMAL(18, 2) AS churned_mrr_usd,
    20.0::DECIMAL(18, 2) AS net_change_usd,
    2 AS active_subscribers,
    1 AS new_subscribers
  UNION ALL
  SELECT
    '2026-03-01'::DATE AS month_start,
    15.0::DECIMAL(18, 2) AS closing_mrr_usd,
    30.0::DECIMAL(18, 2) AS opening_mrr_usd,
    5.0::DECIMAL(18, 2) AS new_mrr_usd,
    20.0::DECIMAL(18, 2) AS churned_mrr_usd,
    -15.0::DECIMAL(18, 2) AS net_change_usd,
    2 AS active_subscribers,
    1 AS new_subscribers
),

__assert__month_start_is_unique_and_present AS (
  SELECT t.month_start
  FROM __ref("rpt_subscription_mrr_monthly") AS t
  GROUP BY
    t.month_start
  HAVING
    COUNT(*) > 1
    OR t.month_start IS NULL
)
