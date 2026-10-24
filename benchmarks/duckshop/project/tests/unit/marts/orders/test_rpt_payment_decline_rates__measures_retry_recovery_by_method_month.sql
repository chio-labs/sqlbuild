TEST (name "rpt_payment_decline_rates__measures_retry_recovery_by_method_month");

WITH __ref__fct_payments AS (
  SELECT
    'P1' AS payment_id,
    NULL AS order_id,
    NULL AS attempt_number,
    TRUE AS is_final_attempt,
    'card' AS payment_method,
    '2026-03-05 10:00:00 +00:00'::TIMESTAMP_TZ AS authorised_at,
    TRUE AS is_successful,
    'NONE' AS decline_family,
    NULL AS risk_band,
    NULL AS card_scheme,
    NULL AS had_chargeback,
    NULL AS currency_code,
    NULL AS amount,
    20.0::DECIMAL(18, 2) AS amount_usd
  UNION ALL
  SELECT
    'P2',
    NULL,
    NULL,
    FALSE,
    'card',
    '2026-03-06 10:00:00 +00:00'::TIMESTAMP_TZ,
    FALSE,
    'INSUFFICIENT_FUNDS',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    15.0::DECIMAL(18, 2)
  UNION ALL
  SELECT
    'P3',
    NULL,
    NULL,
    TRUE,
    'card',
    '2026-03-07 10:00:00 +00:00'::TIMESTAMP_TZ,
    FALSE,
    'INSUFFICIENT_FUNDS',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    15.0::DECIMAL(18, 2)
  UNION ALL
  SELECT
    'P4',
    NULL,
    NULL,
    TRUE,
    'wallet',
    '2026-03-31 23:30:00 -02:00'::TIMESTAMP_TZ,
    TRUE,
    'NONE',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    30.0::DECIMAL(18, 2)
),

__expected__rpt_payment_decline_rates AS (
  SELECT
    '2026-03:card:NONE' AS decline_key,
    1 AS attempts,
    0.3333::DECIMAL(9, 4) AS share_of_method_attempts,
    20.0::DECIMAL(18, 2) AS attempted_usd,
    0 AS recovered_on_retry,
    0.0::DECIMAL(9, 4) AS retry_recovery_rate
  UNION ALL
  SELECT
    '2026-03:card:INSUFFICIENT_FUNDS' AS decline_key,
    2 AS attempts,
    0.6667::DECIMAL(9, 4) AS share_of_method_attempts,
    30.0::DECIMAL(18, 2) AS attempted_usd,
    1 AS recovered_on_retry,
    0.5::DECIMAL(9, 4) AS retry_recovery_rate
  UNION ALL
  SELECT
    '2026-04:wallet:NONE' AS decline_key,
    1 AS attempts,
    1.0::DECIMAL(9, 4) AS share_of_method_attempts,
    30.0::DECIMAL(18, 2) AS attempted_usd,
    0 AS recovered_on_retry,
    0.0::DECIMAL(9, 4) AS retry_recovery_rate
),

__assert__decline_key_is_unique_and_present AS (
  SELECT t.decline_key
  FROM __ref("rpt_payment_decline_rates") AS t
  GROUP BY
    t.decline_key
  HAVING
    COUNT(*) > 1
    OR t.decline_key IS NULL
)
