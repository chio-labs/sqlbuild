TEST (name "int_subscription_mrr_daily__spreads_active_periods_into_daily_usd_mrr");

WITH __ref__int_subscription_periods AS (
  SELECT
    'S1#1' AS subscription_period_key,
    'S1' AS subscription_id,
    'C1' AS customer_id,
    1 AS period_number,
    'active' AS period_state,
    '2026-01-01 08:00:00 +00:00'::TIMESTAMPTZ AS period_start,
    '2026-01-04 08:00:00 +00:00'::TIMESTAMPTZ AS period_end,
    NULL AS period_days,
    3000 AS billing_amount_minor,
    'EUR' AS billing_currency_code,
    30 AS interval_days
  UNION ALL
  SELECT
    'S1#2',
    'S1',
    'C1',
    2,
    'paused',
    '2026-01-04 08:00:00 +00:00'::TIMESTAMPTZ,
    '2026-01-10 08:00:00 +00:00'::TIMESTAMPTZ,
    NULL,
    3000,
    'EUR',
    30
),

__ref__stg_fx_rates AS (
  SELECT
    'EUR' AS currency_code,
    '2025-12-31'::DATE AS rate_date,
    1.1::NUMBER(18, 8) AS rate_to_usd,
    NULL AS usd_to_rate,
    NULL AS next_rate_date
),

__seed__currencies AS (
  SELECT
    'EUR' AS currency_code,
    NULL AS currency_name,
    2 AS minor_unit_exponent,
    NULL AS symbol
),

__expected__int_subscription_mrr_daily AS (
  SELECT
    'S1:20260101' AS subscription_day_key,
    33.4813::DECIMAL(18, 4) AS mrr_usd,
    TRUE AS is_first_day
  UNION ALL
  SELECT
    'S1:20260102' AS subscription_day_key,
    33.4813::DECIMAL(18, 4) AS mrr_usd,
    FALSE AS is_first_day
  UNION ALL
  SELECT
    'S1:20260103' AS subscription_day_key,
    33.4813::DECIMAL(18, 4) AS mrr_usd,
    FALSE AS is_first_day
)
