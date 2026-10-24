TEST (name "stg_loyalty_accounts__keeps_latest_live_version");

WITH __source__storefront__loyalty_accounts AS (
  SELECT
    'K1' AS loyalty_account_id,
    NULL AS customer_id,
    NULL AS tier_code,
    NULL AS points_balance,
    NULL AS enrolled_at,
    NULL AS tier_history,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'K1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'U',
    2,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'I',
    3,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_loyalty_accounts AS (
  SELECT
    'K1' AS loyalty_account_id,
    2 AS source_seq
)
