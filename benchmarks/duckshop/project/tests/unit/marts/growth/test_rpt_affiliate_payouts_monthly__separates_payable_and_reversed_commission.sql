TEST (name "rpt_affiliate_payouts_monthly__separates_payable_and_reversed_commission");

WITH __ref__int_affiliate_commissions_usd AS (
  SELECT
    'AC1' AS conversion_id,
    NULL AS affiliate_code,
    'network_one' AS affiliate_network,
    NULL AS sub_channel,
    NULL AS order_id,
    '2026-03-05 10:00:00 +00:00'::TIMESTAMP_TZ AS converted_at,
    NULL AS click_to_conversion_hours,
    NULL AS commission,
    5.0::DECIMAL(18, 2) AS commission_usd,
    50.0::NUMBER(18, 2) AS order_amount_usd,
    NULL AS commission_rate,
    NULL AS claims_on_order,
    TRUE AS is_last_click,
    FALSE AS is_reversible,
    5.0::DECIMAL(18, 2) AS payable_commission_usd
  UNION ALL
  SELECT
    'AC2',
    NULL,
    'network_one',
    NULL,
    NULL,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    3.0::DECIMAL(18, 2),
    40.0::NUMBER(18, 2),
    NULL,
    NULL,
    FALSE,
    FALSE,
    0.0::DECIMAL(18, 2)
  UNION ALL
  SELECT
    'AC3',
    NULL,
    'network_one',
    NULL,
    NULL,
    '2026-03-20 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    2.0::DECIMAL(18, 2),
    30.0::NUMBER(18, 2),
    NULL,
    NULL,
    TRUE,
    TRUE,
    0.0::DECIMAL(18, 2)
  UNION ALL
  SELECT
    'AC4',
    NULL,
    'network_one',
    NULL,
    NULL,
    '2026-03-31 23:30:00 -02:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    1.0::DECIMAL(18, 2),
    10.0::NUMBER(18, 2),
    NULL,
    NULL,
    TRUE,
    FALSE,
    1.0::DECIMAL(18, 2)
),

__expected__rpt_affiliate_payouts_monthly AS (
  SELECT
    'network_one:2026-03' AS affiliate_month_key,
    3 AS conversions,
    2 AS last_click_conversions,
    5.0::DECIMAL(18, 2) AS payable_commission_usd,
    2.0::DECIMAL(18, 2) AS reversed_commission_usd,
    0.0625::DECIMAL(9, 6) AS effective_commission_rate
  UNION ALL
  SELECT
    'network_one:2026-04' AS affiliate_month_key,
    1 AS conversions,
    1 AS last_click_conversions,
    1.0::DECIMAL(18, 2) AS payable_commission_usd,
    0.0::DECIMAL(18, 2) AS reversed_commission_usd,
    0.1::DECIMAL(9, 6) AS effective_commission_rate
),

__assert__affiliate_month_key_is_unique_and_present AS (
  SELECT t.affiliate_month_key
  FROM __ref("rpt_affiliate_payouts_monthly") AS t
  GROUP BY
    t.affiliate_month_key
  HAVING
    COUNT(*) > 1
    OR t.affiliate_month_key IS NULL
)
