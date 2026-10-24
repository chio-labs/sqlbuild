TEST (name "int_affiliate_commissions_usd__pays_only_the_last_click_on_live_orders");

WITH __ref__stg_affiliate_conversions AS (
  SELECT
    'CV1' AS conversion_id,
    'AWN-duck123' AS affiliate_code,
    'O1' AS order_id,
    500 AS commission_minor,
    'EUR' AS currency_code,
    '2026-03-10 23:30:00 -02:00'::TIMESTAMP_TZ AS converted_at,
    '2026-03-09 10:00:00 +00:00'::TIMESTAMP_TZ AS clicked_at,
    NULL AS click_to_conversion_hours,
    'social_pf' AS sub_id,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'CV2',
    'creatorx',
    'O1',
    300,
    'EUR',
    '2026-03-10 12:00:00 +00:00'::TIMESTAMP_TZ,
    '2026-03-08 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'CV3',
    'PN_kw',
    'O2',
    1500,
    'KWD',
    '2026-03-10 12:00:00 +00:00'::TIMESTAMP_TZ,
    '2026-03-09 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    '123',
    NULL,
    NULL
),

__ref__int_orders_usd AS (
  SELECT
    'O1' AS order_id,
    NULL AS customer_id,
    NULL AS region_code,
    NULL AS currency_code,
    NULL AS placed_at,
    NULL AS placed_date_local,
    'DELIVERED' AS order_status,
    NULL AS sales_channel,
    NULL AS units,
    NULL AS amount,
    110.0::DECIMAL(18, 2) AS amount_usd,
    NULL AS gross_amount_usd,
    NULL AS discount_amount_usd,
    NULL AS tax_amount_usd,
    NULL AS rate_to_usd,
    NULL AS rate_date,
    NULL AS rate_age_days,
    NULL AS is_rate_stale,
    NULL AS promo_code,
    NULL AS utm_source,
    NULL AS utm_medium,
    NULL AS utm_campaign,
    NULL AS basket_size
  UNION ALL
  SELECT
    'O2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'CANCELLED',
    NULL,
    NULL,
    NULL,
    100.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_fx_rates AS (
  SELECT
    'EUR' AS currency_code,
    '2026-03-10'::DATE AS rate_date,
    1.08::NUMBER(18, 8) AS rate_to_usd,
    NULL AS usd_to_rate,
    NULL AS next_rate_date
  UNION ALL
  SELECT
    'EUR',
    '2026-03-11'::DATE,
    1.1::NUMBER(18, 8),
    NULL,
    NULL
  UNION ALL
  SELECT
    'KWD',
    '2026-03-01'::DATE,
    3.25::NUMBER(18, 8),
    NULL,
    NULL
),

__seed__currencies AS (
  SELECT
    'EUR' AS currency_code,
    NULL AS currency_name,
    2 AS minor_unit_exponent,
    NULL AS symbol
  UNION ALL
  SELECT
    'KWD',
    NULL,
    3,
    NULL
),

__expected__int_affiliate_commissions_usd AS (
  SELECT
    'CV1' AS conversion_id,
    'AWN' AS affiliate_network,
    'social' AS sub_channel,
    5.0::DECIMAL(38, 6) AS commission,
    5.5::DECIMAL(18, 2) AS commission_usd,
    0.05::DECIMAL(9, 6) AS commission_rate,
    2 AS claims_on_order,
    TRUE AS is_last_click,
    FALSE AS is_reversible,
    5.5::DECIMAL(18, 2) AS payable_commission_usd
  UNION ALL
  SELECT
    'CV2' AS conversion_id,
    'DIRECT' AS affiliate_network,
    CAST(NULL AS VARCHAR) AS sub_channel,
    3.0::DECIMAL(38, 6) AS commission,
    3.24::DECIMAL(18, 2) AS commission_usd,
    0.029455::DECIMAL(9, 6) AS commission_rate,
    2 AS claims_on_order,
    FALSE AS is_last_click,
    FALSE AS is_reversible,
    0.0::DECIMAL(18, 2) AS payable_commission_usd
  UNION ALL
  SELECT
    'CV3' AS conversion_id,
    'PN' AS affiliate_network,
    CAST(NULL AS VARCHAR) AS sub_channel,
    1.5::DECIMAL(38, 6) AS commission,
    4.88::DECIMAL(18, 2) AS commission_usd,
    0.04875::DECIMAL(9, 6) AS commission_rate,
    1 AS claims_on_order,
    TRUE AS is_last_click,
    TRUE AS is_reversible,
    0.0::DECIMAL(18, 2) AS payable_commission_usd
)
