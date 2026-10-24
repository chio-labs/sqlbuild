TEST (name "rpt_referral_program__costs_qualified_referrals_by_utc_invite_month");

WITH __ref__int_referral_conversions AS (
  SELECT
    'I1' AS invite_id,
    NULL AS referrer_customer_id,
    NULL AS invitee_customer_id,
    NULL AS invitee_email_domain,
    '2026-03-05 10:00:00 +00:00'::TIMESTAMP_TZ AS sent_at,
    '2026-03-06 10:00:00 +00:00'::TIMESTAMP_TZ AS accepted_at,
    NULL AS hours_to_accept,
    NULL AS first_order_id,
    50.0::DECIMAL(18, 2) AS first_order_usd,
    NULL AS days_to_first_order,
    FALSE AS is_self_referral,
    TRUE AS is_qualified,
    10.0::DECIMAL(18, 2) AS reward_usd,
    NULL AS invite_sequence_for_referrer,
    NULL AS referrer_lifetime_orders
  UNION ALL
  SELECT
    'I2',
    NULL,
    NULL,
    NULL,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    FALSE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'I3',
    NULL,
    NULL,
    NULL,
    '2026-03-31 23:30:00 -02:00'::TIMESTAMP_TZ,
    '2026-04-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
    FALSE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'I4',
    NULL,
    NULL,
    NULL,
    '2026-03-12 10:00:00 +00:00'::TIMESTAMP_TZ,
    '2026-03-12 12:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    30.0::DECIMAL(18, 2),
    NULL,
    FALSE,
    TRUE,
    10.0::DECIMAL(18, 2),
    NULL,
    NULL
),

__expected__rpt_referral_program AS (
  SELECT
    '2026-03-01'::DATE AS invite_month,
    3 AS invites_sent,
    2 AS accepted,
    2 AS qualified,
    0 AS self_referrals,
    0.6667::DECIMAL(9, 4) AS acceptance_rate,
    20.0::DECIMAL(18, 2) AS reward_cost_usd,
    80.0::DECIMAL(18, 2) AS referred_revenue_usd,
    10.0::DECIMAL(18, 2) AS cost_per_qualified_usd
  UNION ALL
  SELECT
    '2026-04-01'::DATE AS invite_month,
    1 AS invites_sent,
    1 AS accepted,
    0 AS qualified,
    1 AS self_referrals,
    1.0::DECIMAL(9, 4) AS acceptance_rate,
    0.0::DECIMAL(18, 2) AS reward_cost_usd,
    0.0::DECIMAL(18, 2) AS referred_revenue_usd,
    CAST(NULL AS DECIMAL(18, 2)) AS cost_per_qualified_usd
),

__assert__invite_month_is_unique_and_present AS (
  SELECT t.invite_month
  FROM __ref("rpt_referral_program") AS t
  GROUP BY
    t.invite_month
  HAVING
    COUNT(*) > 1
    OR t.invite_month IS NULL
)
