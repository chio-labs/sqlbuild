TEST (name "int_orders_usd__converts_minor_units_by_currency_exponent");

WITH __ref__int_orders_enriched AS (
  SELECT
    'O-JPY' AS order_id,
    'C1' AS customer_id,
    NULL AS storefront_code,
    NULL AS region_code,
    NULL AS storefront_timezone,
    'JPY' AS currency_code,
    '2026-03-10 12:00:00 +00:00'::TIMESTAMP_TZ AS placed_at,
    '2026-03-10'::DATE AS placed_date_local,
    'PAID' AS order_status,
    NULL AS sales_channel,
    NULL AS line_count,
    NULL AS units,
    1500 AS gross_amount_minor,
    0 AS discount_amount_minor,
    1500 AS net_amount_minor,
    0 AS tax_amount_minor,
    NULL AS captured_amount_minor,
    NULL AS outstanding_amount_minor,
    NULL AS promo_code,
    NULL AS ship_to_country_code,
    NULL AS is_cross_border,
    NULL AS is_first_party_customer,
    NULL AS basket_size,
    NULL AS is_gift,
    NULL AS utm_source,
    NULL AS utm_medium,
    NULL AS utm_campaign,
    NULL AS total_weight_kg
  UNION ALL
  SELECT
    'O-EUR',
    'C1',
    NULL,
    NULL,
    NULL,
    'EUR',
    '2026-03-10 12:00:00 +00:00'::TIMESTAMP_TZ,
    '2026-03-10'::DATE,
    'PAID',
    NULL,
    NULL,
    NULL,
    2499,
    500,
    1999,
    0,
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
  UNION ALL
  SELECT
    'O-KWD',
    'C1',
    NULL,
    NULL,
    NULL,
    'KWD',
    '2026-03-10 12:00:00 +00:00'::TIMESTAMP_TZ,
    '2026-03-20'::DATE,
    'PAID',
    NULL,
    NULL,
    NULL,
    12345,
    0,
    12345,
    0,
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
    'JPY' AS currency_code,
    '2026-03-01'::DATE AS rate_date,
    1.0::NUMBER(18, 8) AS rate_to_usd,
    NULL AS usd_to_rate,
    NULL AS next_rate_date
  UNION ALL
  SELECT
    'JPY',
    '2026-03-09'::DATE,
    0.0067::NUMBER(18, 8),
    NULL,
    NULL
  UNION ALL
  SELECT
    'JPY',
    '2026-03-11'::DATE,
    99.0::NUMBER(18, 8),
    NULL,
    NULL
  UNION ALL
  SELECT
    'EUR',
    '2026-03-10'::DATE,
    1.08::NUMBER(18, 8),
    NULL,
    NULL
  UNION ALL
  SELECT
    'KWD',
    '2026-03-09'::DATE,
    3.25::NUMBER(18, 8),
    NULL,
    NULL
),

__seed__currencies AS (
  SELECT
    'JPY' AS currency_code,
    NULL AS currency_name,
    0 AS minor_unit_exponent,
    NULL AS symbol
  UNION ALL
  SELECT
    'EUR',
    NULL,
    2,
    NULL
  UNION ALL
  SELECT
    'KWD',
    NULL,
    3,
    NULL
),

__expected__int_orders_usd AS (
  SELECT
    'O-JPY' AS order_id,
    1500.0::DECIMAL(38, 6) AS amount,
    10.05::DECIMAL(18, 2) AS amount_usd,
    10.05::DECIMAL(18, 2) AS gross_amount_usd,
    0.0::DECIMAL(18, 2) AS discount_amount_usd,
    '2026-03-09'::DATE AS rate_date,
    1 AS rate_age_days,
    FALSE AS is_rate_stale
  UNION ALL
  SELECT
    'O-EUR' AS order_id,
    19.99::DECIMAL(38, 6) AS amount,
    21.59::DECIMAL(18, 2) AS amount_usd,
    26.99::DECIMAL(18, 2) AS gross_amount_usd,
    5.4::DECIMAL(18, 2) AS discount_amount_usd,
    '2026-03-10'::DATE AS rate_date,
    0 AS rate_age_days,
    FALSE AS is_rate_stale
  UNION ALL
  SELECT
    'O-KWD' AS order_id,
    12.345::DECIMAL(38, 6) AS amount,
    40.12::DECIMAL(18, 2) AS amount_usd,
    40.12::DECIMAL(18, 2) AS gross_amount_usd,
    0.0::DECIMAL(18, 2) AS discount_amount_usd,
    '2026-03-09'::DATE AS rate_date,
    11 AS rate_age_days,
    TRUE AS is_rate_stale
)
