TEST (name "int_ledger_balances_daily__fills_quiet_days_and_checks_normal_side");

WITH __ref__stg_ledger_entries AS (
  SELECT
    'E1' AS entry_id,
    NULL AS journal_code,
    '1100' AS account_code,
    'asset' AS account_class,
    5000 AS signed_amount_minor,
    'EUR' AS currency_code,
    '2026-03-28 10:00:00 +00:00'::TIMESTAMP_TZ AS posted_at,
    NULL AS reference_type,
    NULL AS reference_id,
    NULL AS reference,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'E2',
    NULL,
    '1100',
    'asset',
    -2000,
    'EUR',
    '2026-03-29 23:30:00 -01:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'E3',
    NULL,
    '1100',
    'asset',
    -4000,
    'EUR',
    '2026-03-31 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'E4',
    NULL,
    '4000',
    'revenue',
    -1000,
    'EUR',
    '2026-03-31 08:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__seed__currencies AS (
  SELECT
    'EUR' AS currency_code,
    NULL AS currency_name,
    2 AS minor_unit_exponent,
    NULL AS symbol
),

__expected__int_ledger_balances_daily AS (
  SELECT
    '1100:EUR:2026-03-28' AS balance_key,
    5000 AS debit_minor,
    0 AS credit_minor,
    1 AS posting_count,
    5000 AS closing_balance_minor,
    50.0::NUMBER(38, 6) AS closing_balance,
    5000 AS month_to_date_movement_minor,
    FALSE AS is_month_end,
    TRUE AS is_normal_side
  UNION ALL
  SELECT
    '1100:EUR:2026-03-29' AS balance_key,
    0 AS debit_minor,
    0 AS credit_minor,
    0 AS posting_count,
    5000 AS closing_balance_minor,
    50.0::NUMBER(38, 6) AS closing_balance,
    5000 AS month_to_date_movement_minor,
    FALSE AS is_month_end,
    TRUE AS is_normal_side
  UNION ALL
  SELECT
    '1100:EUR:2026-03-30' AS balance_key,
    0 AS debit_minor,
    2000 AS credit_minor,
    1 AS posting_count,
    3000 AS closing_balance_minor,
    30.0::NUMBER(38, 6) AS closing_balance,
    3000 AS month_to_date_movement_minor,
    FALSE AS is_month_end,
    TRUE AS is_normal_side
  UNION ALL
  SELECT
    '1100:EUR:2026-03-31' AS balance_key,
    0 AS debit_minor,
    4000 AS credit_minor,
    1 AS posting_count,
    -1000 AS closing_balance_minor,
    -10.0::NUMBER(38, 6) AS closing_balance,
    -1000 AS month_to_date_movement_minor,
    TRUE AS is_month_end,
    FALSE AS is_normal_side
  UNION ALL
  SELECT
    '4000:EUR:2026-03-31' AS balance_key,
    0 AS debit_minor,
    1000 AS credit_minor,
    1 AS posting_count,
    -1000 AS closing_balance_minor,
    -10.0::NUMBER(38, 6) AS closing_balance,
    -1000 AS month_to_date_movement_minor,
    TRUE AS is_month_end,
    TRUE AS is_normal_side
)
