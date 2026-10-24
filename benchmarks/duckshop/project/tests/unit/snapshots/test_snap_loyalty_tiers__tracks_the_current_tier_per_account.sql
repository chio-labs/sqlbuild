TEST (name "snap_loyalty_tiers__tracks_the_current_tier_per_account");

WITH __ref__stg_loyalty_accounts AS (
  SELECT
    'LA1' AS loyalty_account_id,
    'C1' AS customer_id,
    'GOLDEN_DUCK' AS tier_code,
    NULL AS points_balance,
    NULL AS enrolled_at,
    NULL AS tier_change_count,
    'DRAKE' AS previous_tier_code,
    NULL AS tier_history,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'LA2',
    'C2',
    'DUCKLING',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__snap_loyalty_tiers AS (
  SELECT
    'LA1' AS loyalty_account_id,
    'C1' AS customer_id,
    'GOLDEN_DUCK' AS tier_code
  UNION ALL
  SELECT
    'LA2' AS loyalty_account_id,
    'C2' AS customer_id,
    'DUCKLING' AS tier_code
),

__assert__loyalty_account_id_is_unique_and_present AS (
  SELECT t.loyalty_account_id
  FROM __ref("snap_loyalty_tiers") AS t
  GROUP BY
    t.loyalty_account_id
  HAVING
    COUNT(*) > 1
    OR t.loyalty_account_id IS NULL
)
