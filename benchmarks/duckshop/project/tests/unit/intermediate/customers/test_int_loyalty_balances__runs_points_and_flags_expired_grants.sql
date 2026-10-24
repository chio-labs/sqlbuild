TEST (name "int_loyalty_balances__runs_points_and_flags_expired_grants");

WITH __ref__stg_loyalty_ledger AS (
  SELECT
    'E1' AS entry_id,
    'LA1' AS loyalty_account_id,
    100 AS points_delta,
    'ORDER' AS reason_code,
    NULL AS order_id,
    '2026-01-01 00:00:00 +00:00'::TIMESTAMP_TZ AS posted_at,
    NULL AS campaign_ref,
    '2026-02-01'::DATE AS expires_on,
    NULL AS metadata,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'E2',
    'LA1',
    50,
    'REVIEW',
    NULL,
    '2026-02-01 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    '2026-12-31'::DATE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'E3',
    'LA1',
    -30,
    'REDEEM',
    NULL,
    '2026-03-01 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_loyalty_accounts AS (
  SELECT
    'LA1' AS loyalty_account_id,
    'C1' AS customer_id,
    'GOLDEN_DUCK' AS tier_code,
    NULL AS points_balance,
    NULL AS enrolled_at,
    NULL AS tier_change_count,
    NULL AS previous_tier_code,
    NULL AS tier_history,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__expected__int_loyalty_balances AS (
  SELECT
    'E1' AS entry_id,
    'C1' AS customer_id,
    100 AS running_points,
    100 AS expiring_points,
    TRUE AS is_expired,
    1.0::DECIMAL(18, 4) AS running_value_usd,
    'GOLDEN_DUCK' AS tier_code
  UNION ALL
  SELECT
    'E2' AS entry_id,
    'C1' AS customer_id,
    150 AS running_points,
    0 AS expiring_points,
    FALSE AS is_expired,
    1.5::DECIMAL(18, 4) AS running_value_usd,
    'GOLDEN_DUCK' AS tier_code
  UNION ALL
  SELECT
    'E3' AS entry_id,
    'C1' AS customer_id,
    120 AS running_points,
    0 AS expiring_points,
    FALSE AS is_expired,
    1.2::DECIMAL(18, 4) AS running_value_usd,
    'GOLDEN_DUCK' AS tier_code
)
