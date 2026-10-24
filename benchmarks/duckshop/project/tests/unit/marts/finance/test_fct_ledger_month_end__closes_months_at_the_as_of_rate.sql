TEST (name "fct_ledger_month_end__closes_months_at_the_as_of_rate");

WITH __ref__int_ledger_balances_daily AS (
  SELECT
    '4000|EUR|2026-02-27' AS balance_key,
    '4000' AS account_code,
    'REVENUE' AS account_class,
    'EUR' AS currency_code,
    '2026-02-27'::DATE AS calendar_date,
    0 AS debit_minor,
    1000 AS credit_minor,
    NULL AS posting_count,
    NULL AS closing_balance_minor,
    -1000.0::NUMBER(38, 6) AS closing_balance,
    NULL AS month_to_date_movement_minor,
    FALSE AS is_month_end,
    TRUE AS is_normal_side
  UNION ALL
  SELECT
    '4000|EUR|2026-02-28',
    '4000',
    'REVENUE',
    'EUR',
    '2026-02-28'::DATE,
    100,
    500,
    NULL,
    NULL,
    -1400.0::NUMBER(38, 6),
    NULL,
    TRUE,
    TRUE
  UNION ALL
  SELECT
    '4000|EUR|2026-03-15',
    '4000',
    'REVENUE',
    'EUR',
    '2026-03-15'::DATE,
    0,
    300,
    NULL,
    NULL,
    -1700.0::NUMBER(38, 6),
    NULL,
    FALSE,
    TRUE
  UNION ALL
  SELECT
    '4000|EUR|2026-03-31',
    '4000',
    'REVENUE',
    'EUR',
    '2026-03-31'::DATE,
    0,
    200,
    NULL,
    NULL,
    -1900.0::NUMBER(38, 6),
    NULL,
    TRUE,
    TRUE
  UNION ALL
  SELECT
    '1000|GBP|2026-03-30',
    '1000',
    'ASSET',
    'GBP',
    '2026-03-30'::DATE,
    20,
    0,
    NULL,
    NULL,
    20.0::NUMBER(38, 6),
    NULL,
    FALSE,
    TRUE
  UNION ALL
  SELECT
    '1000|GBP|2026-03-31',
    '1000',
    'ASSET',
    'GBP',
    '2026-03-31'::DATE,
    50,
    0,
    NULL,
    NULL,
    70.0::NUMBER(38, 6),
    NULL,
    TRUE,
    TRUE
),

__ref__stg_fx_rates AS (
  SELECT
    'EUR' AS currency_code,
    '2026-02-27'::DATE AS rate_date,
    1.05::NUMBER(18, 8) AS rate_to_usd,
    NULL AS usd_to_rate,
    NULL AS next_rate_date
  UNION ALL
  SELECT
    'EUR',
    '2026-03-30'::DATE,
    1.1::NUMBER(18, 8),
    NULL,
    NULL
),

__expected__fct_ledger_month_end AS (
  SELECT
    '4000:EUR:2026-02-28' AS ledger_month_key,
    100 AS month_debit_minor,
    1500 AS month_credit_minor,
    -1400.0::NUMBER(38, 6) AS closing_balance,
    -1470.0::DECIMAL(18, 2) AS closing_balance_usd
  UNION ALL
  SELECT
    '4000:EUR:2026-03-31' AS ledger_month_key,
    0 AS month_debit_minor,
    500 AS month_credit_minor,
    -1900.0::NUMBER(38, 6) AS closing_balance,
    -2090.0::DECIMAL(18, 2) AS closing_balance_usd
  UNION ALL
  SELECT
    '1000:GBP:2026-03-31' AS ledger_month_key,
    70 AS month_debit_minor,
    0 AS month_credit_minor,
    70.0::NUMBER(38, 6) AS closing_balance,
    CAST(NULL AS DECIMAL(18, 2)) AS closing_balance_usd
),

__assert__ledger_month_key_is_unique_and_present AS (
  SELECT t.ledger_month_key
  FROM __ref("fct_ledger_month_end") AS t
  GROUP BY
    t.ledger_month_key
  HAVING
    COUNT(*) > 1
    OR t.ledger_month_key IS NULL
)
