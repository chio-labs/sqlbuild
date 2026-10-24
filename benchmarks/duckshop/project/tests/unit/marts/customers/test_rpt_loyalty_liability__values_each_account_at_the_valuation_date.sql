TEST (name "rpt_loyalty_liability__values_each_account_at_the_valuation_date");

WITH __ref__int_loyalty_balances AS (
  SELECT
    'E1' AS entry_id,
    'LA1' AS loyalty_account_id,
    NULL AS customer_id,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ AS posted_at,
    NULL AS points_delta,
    100 AS running_points,
    0 AS expiring_points,
    NULL AS is_expired,
    1.0::DECIMAL(18, 4) AS running_value_usd,
    NULL AS reason_code,
    'DUCKLING' AS tier_code
  UNION ALL
  SELECT
    'E2',
    'LA1',
    NULL,
    '2026-03-20 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    250,
    50,
    NULL,
    2.5::DECIMAL(18, 4),
    NULL,
    'DRAKE'
  UNION ALL
  SELECT
    'E3',
    'LA1',
    NULL,
    '2026-04-02 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    999,
    0,
    NULL,
    9.99::DECIMAL(18, 4),
    NULL,
    'GOLDEN_DUCK'
  UNION ALL
  SELECT
    'E4',
    'LA2',
    NULL,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    150,
    0,
    NULL,
    1.5::DECIMAL(18, 4),
    NULL,
    'DRAKE'
  UNION ALL
  SELECT
    'E5',
    'LA3',
    NULL,
    '2026-02-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    40,
    0,
    NULL,
    0.4::DECIMAL(18, 4),
    NULL,
    NULL
),

__expected__rpt_loyalty_liability AS (
  SELECT
    'DRAKE' AS tier_code,
    2 AS member_count,
    400 AS outstanding_points,
    4.0::DECIMAL(18, 2) AS liability_usd,
    50 AS expiring_points,
    200.0::DECIMAL(12, 2) AS average_points_per_member
  UNION ALL
  SELECT
    'NONE' AS tier_code,
    1 AS member_count,
    40 AS outstanding_points,
    0.4::DECIMAL(18, 2) AS liability_usd,
    0 AS expiring_points,
    40.0::DECIMAL(12, 2) AS average_points_per_member
),

__assert__tier_code_is_unique_and_present AS (
  SELECT t.tier_code
  FROM __ref("rpt_loyalty_liability") AS t
  GROUP BY
    t.tier_code
  HAVING
    COUNT(*) > 1
    OR t.tier_code IS NULL
)
