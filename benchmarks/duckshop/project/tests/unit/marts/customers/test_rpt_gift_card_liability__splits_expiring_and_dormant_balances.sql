TEST (name "rpt_gift_card_liability__splits_expiring_and_dormant_balances");

WITH __ref__int_gift_card_balances AS (
  SELECT
    'G1' AS gift_card_id,
    'EUR' AS currency_code,
    NULL AS issued_at,
    '2026-05-01'::DATE AS expires_on,
    NULL AS initial_amount,
    NULL AS redeemed_amount,
    NULL AS balance_amount,
    50.0::DECIMAL(18, 2) AS balance_usd,
    NULL AS transaction_count,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ AS last_used_at,
    'active' AS liability_status
  UNION ALL
  SELECT
    'G2',
    'EUR',
    NULL,
    '2027-01-01'::DATE,
    NULL,
    NULL,
    NULL,
    20.0::DECIMAL(18, 2),
    NULL,
    '2025-01-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    'active'
  UNION ALL
  SELECT
    'G3',
    'EUR',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    -5.0::DECIMAL(18, 2),
    NULL,
    NULL,
    'active'
  UNION ALL
  SELECT
    'G4',
    'USD',
    NULL,
    '2026-01-01'::DATE,
    NULL,
    NULL,
    NULL,
    10.0::DECIMAL(18, 2),
    NULL,
    '2025-12-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    'expired'
),

__expected__rpt_gift_card_liability AS (
  SELECT
    'EUR:active' AS liability_key,
    3 AS card_count,
    70.0::DECIMAL(18, 2) AS balance_usd,
    50.0::DECIMAL(18, 2) AS expiring_90d_usd,
    1 AS dormant_card_count
  UNION ALL
  SELECT
    'USD:expired' AS liability_key,
    1 AS card_count,
    10.0::DECIMAL(18, 2) AS balance_usd,
    10.0::DECIMAL(18, 2) AS expiring_90d_usd,
    0 AS dormant_card_count
),

__assert__liability_key_is_unique_and_present AS (
  SELECT t.liability_key
  FROM __ref("rpt_gift_card_liability") AS t
  GROUP BY
    t.liability_key
  HAVING
    COUNT(*) > 1
    OR t.liability_key IS NULL
)
