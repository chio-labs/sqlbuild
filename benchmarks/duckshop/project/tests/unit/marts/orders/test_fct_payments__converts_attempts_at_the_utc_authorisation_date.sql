TEST (name "fct_payments__converts_attempts_at_the_utc_authorisation_date");

WITH __ref__int_payment_attempts AS (
  SELECT
    'P1' AS payment_id,
    'O1' AS order_id,
    1 AS attempt_number,
    NULL AS attempt_count,
    TRUE AS is_final_attempt,
    'card' AS payment_method,
    1250 AS amount_minor,
    'EUR' AS currency_code,
    '2026-03-10 23:30:00 -02:00'::TIMESTAMPTZ AS authorised_at,
    NULL AS seconds_since_previous_attempt,
    NULL AS gateway_status,
    TRUE AS is_successful,
    NULL AS decline_family,
    NULL AS gateway_error_code,
    NULL AS risk_score,
    NULL AS risk_band,
    NULL AS three_ds_outcome,
    NULL AS card_bin_valid,
    'network_a' AS card_scheme,
    NULL AS had_chargeback
  UNION ALL
  SELECT
    'P2',
    'O1',
    1,
    NULL,
    TRUE,
    'card',
    1500,
    'KWD',
    '2026-03-10 12:00:00 +03:00'::TIMESTAMPTZ,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'network_b',
    NULL
  UNION ALL
  SELECT
    'P3',
    'O1',
    1,
    NULL,
    TRUE,
    'card',
    100,
    'XXX',
    '2026-03-10 12:00:00 +00:00'::TIMESTAMPTZ,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'network_a',
    NULL
  UNION ALL
  SELECT
    'P4',
    'O1',
    1,
    NULL,
    TRUE,
    'card',
    1000,
    'JPY',
    '2026-03-10 12:00:00 +09:00'::TIMESTAMPTZ,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_fx_rates AS (
  SELECT
    'EUR' AS currency_code,
    '2026-03-10'::DATE AS rate_date,
    1.08::NUMBER(18, 8) AS rate_to_usd,
    NULL AS usd_to_rate,
    NULL AS next_rate_date
  UNION ALL
  SELECT
    'EUR',
    '2026-03-11'::DATE,
    1.1::NUMBER(18, 8),
    NULL,
    NULL
  UNION ALL
  SELECT
    'KWD',
    '2026-03-01'::DATE,
    3.25::NUMBER(18, 8),
    NULL,
    NULL
),

__seed__currencies AS (
  SELECT
    'EUR' AS currency_code,
    NULL AS currency_name,
    2 AS minor_unit_exponent,
    NULL AS symbol
  UNION ALL
  SELECT
    'KWD',
    NULL,
    3,
    NULL
  UNION ALL
  SELECT
    'JPY',
    NULL,
    0,
    NULL
),

__expected__fct_payments AS (
  SELECT
    'P1' AS payment_id,
    'network_a' AS card_scheme,
    12.5::DECIMAL(38, 6) AS amount,
    13.75::DECIMAL(18, 2) AS amount_usd
  UNION ALL
  SELECT
    'P2' AS payment_id,
    'network_b' AS card_scheme,
    1.5::DECIMAL(38, 6) AS amount,
    4.88::DECIMAL(18, 2) AS amount_usd
  UNION ALL
  SELECT
    'P4' AS payment_id,
    CAST(NULL AS VARCHAR) AS card_scheme,
    1000.0::DECIMAL(38, 6) AS amount,
    CAST(NULL AS DECIMAL(18, 2)) AS amount_usd
),

__assert__payment_id_is_unique_and_present AS (
  SELECT t.payment_id
  FROM __ref("fct_payments") AS t
  GROUP BY
    t.payment_id
  HAVING
    COUNT(*) > 1
    OR t.payment_id IS NULL
)
