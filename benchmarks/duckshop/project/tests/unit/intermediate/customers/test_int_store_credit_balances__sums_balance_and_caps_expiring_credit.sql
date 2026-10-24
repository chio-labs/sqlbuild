TEST (name "int_store_credit_balances__sums_balance_and_caps_expiring_credit");

WITH __ref__stg_store_credit_ledger AS (
  SELECT
    'S1' AS entry_id,
    'C1' AS customer_id,
    'EUR' AS currency_code,
    1000 AS amount_minor,
    'GOODWILL_DELAY' AS reason_code,
    '2026-01-01 00:00:00 +00:00'::TIMESTAMP_TZ AS posted_at,
    NULL AS source_order_id,
    '2026-04-15'::DATE AS expires_on,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'S2',
    'C1',
    'EUR',
    500,
    'REFUND',
    '2026-02-01 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    '2026-12-31'::DATE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'S3',
    'C1',
    'EUR',
    -300,
    'SPEND',
    '2026-03-01 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_fx_rates AS (
  SELECT
    'EUR' AS currency_code,
    '2026-03-01'::DATE AS rate_date,
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

__expected__int_store_credit_balances AS (
  SELECT
    'C1:EUR' AS store_credit_key,
    1200 AS balance_minor,
    1000 AS expiring_30d_minor,
    3 AS posting_count,
    0.666667::DECIMAL(9, 6) AS goodwill_share,
    13.2::DECIMAL(18, 2) AS balance_usd
)
