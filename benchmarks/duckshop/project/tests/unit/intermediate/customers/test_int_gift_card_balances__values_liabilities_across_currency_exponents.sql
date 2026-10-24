TEST (name "int_gift_card_balances__values_liabilities_across_currency_exponents");

WITH __ref__stg_gift_cards AS (
  SELECT
    'G1' AS gift_card_id,
    NULL AS code_last4,
    'EUR' AS currency_code,
    5000 AS initial_amount_minor,
    NULL AS issued_at,
    '2027-01-01'::DATE AS expires_on,
    NULL AS purchaser_customer_id,
    NULL AS is_promotional,
    NULL AS design_code,
    NULL AS details,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'G2',
    NULL,
    'KWD',
    10000,
    NULL,
    '2026-01-01'::DATE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'G3',
    NULL,
    'USD',
    1000,
    NULL,
    '2027-01-01'::DATE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_gift_card_transactions AS (
  SELECT
    'T1' AS transaction_id,
    'G1' AS gift_card_id,
    NULL AS order_id,
    'REDEEM' AS transaction_type,
    -2000 AS signed_amount_minor,
    '2026-02-01 10:00:00 +00:00'::TIMESTAMP_TZ AS occurred_at,
    NULL AS channel,
    NULL AS terminal_id,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'T2',
    'G3',
    NULL,
    'REDEEM',
    -1000,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_fx_rates AS (
  SELECT
    'EUR' AS currency_code,
    '2026-03-30'::DATE AS rate_date,
    1.1::NUMBER(18, 8) AS rate_to_usd,
    NULL AS usd_to_rate,
    NULL AS next_rate_date
  UNION ALL
  SELECT
    'KWD',
    '2026-01-01'::DATE,
    3.25::NUMBER(18, 8),
    NULL,
    NULL
  UNION ALL
  SELECT
    'USD',
    '2020-01-01'::DATE,
    1.0::NUMBER(18, 8),
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
    'USD',
    NULL,
    2,
    NULL
),

__expected__int_gift_card_balances AS (
  SELECT
    'G1' AS gift_card_id,
    50.0::NUMBER(38, 6) AS initial_amount,
    20.0::NUMBER(38, 6) AS redeemed_amount,
    30.0::NUMBER(38, 6) AS balance_amount,
    33.0::DECIMAL(18, 2) AS balance_usd,
    1 AS transaction_count,
    'active' AS liability_status
  UNION ALL
  SELECT
    'G2' AS gift_card_id,
    10.0::NUMBER(38, 6) AS initial_amount,
    0.0::NUMBER(38, 6) AS redeemed_amount,
    10.0::NUMBER(38, 6) AS balance_amount,
    32.5::DECIMAL(18, 2) AS balance_usd,
    0 AS transaction_count,
    'expired_unused' AS liability_status
  UNION ALL
  SELECT
    'G3' AS gift_card_id,
    10.0::NUMBER(38, 6) AS initial_amount,
    10.0::NUMBER(38, 6) AS redeemed_amount,
    0.0::NUMBER(38, 6) AS balance_amount,
    0.0::DECIMAL(18, 2) AS balance_usd,
    1 AS transaction_count,
    'fully_redeemed' AS liability_status
)
