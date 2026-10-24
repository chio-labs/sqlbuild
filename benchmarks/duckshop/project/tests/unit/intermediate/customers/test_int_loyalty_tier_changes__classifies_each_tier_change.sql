TEST (name "int_loyalty_tier_changes__classifies_each_tier_change");

WITH __ref__stg_loyalty_accounts AS (
  SELECT
    'LA1' AS loyalty_account_id,
    'C1' AS customer_id,
    NULL AS tier_code,
    NULL AS points_balance,
    NULL AS enrolled_at,
    NULL AS tier_change_count,
    NULL AS previous_tier_code,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT(
        'tier',
        'duckling',
        'at',
        '2025-01-01T00:00:00Z'
      ),
      OBJECT_CONSTRUCT(
        'tier',
        'golden_duck',
        'at',
        '2025-03-01T00:00:00Z'
      ),
      OBJECT_CONSTRUCT(
        'tier',
        'drake',
        'at',
        '2025-04-01T00:00:00Z'
      ),
      OBJECT_CONSTRUCT(
        'tier',
        'drake',
        'at',
        '2025-04-11T00:00:00Z'
      )
    )::ARRAY AS tier_history,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__expected__int_loyalty_tier_changes AS (
  SELECT
    'LA1:0' AS tier_change_key,
    'DUCKLING' AS tier_code,
    CAST(NULL AS VARCHAR) AS previous_tier_code,
    'enrol' AS direction,
    CAST(NULL AS INT) AS days_in_previous_tier
  UNION ALL
  SELECT
    'LA1:1' AS tier_change_key,
    'GOLDEN_DUCK' AS tier_code,
    'DUCKLING' AS previous_tier_code,
    'upgrade' AS direction,
    59 AS days_in_previous_tier
  UNION ALL
  SELECT
    'LA1:2' AS tier_change_key,
    'DRAKE' AS tier_code,
    'GOLDEN_DUCK' AS previous_tier_code,
    'downgrade' AS direction,
    31 AS days_in_previous_tier
  UNION ALL
  SELECT
    'LA1:3' AS tier_change_key,
    'DRAKE' AS tier_code,
    'DRAKE' AS previous_tier_code,
    'same' AS direction,
    10 AS days_in_previous_tier
)
