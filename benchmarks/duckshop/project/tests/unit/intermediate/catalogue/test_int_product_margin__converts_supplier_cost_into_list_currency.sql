TEST (name "int_product_margin__converts_supplier_cost_into_list_currency");

WITH __ref__int_price_history AS (
  SELECT
    'P-DUCK-1' AS price_list_id,
    'DUCK-1' AS sku,
    'EUR' AS currency_code,
    1000 AS list_amount_minor,
    NULL AS valid_from,
    NULL AS effective_valid_to,
    NULL AS previous_amount_minor,
    NULL AS change_pct,
    NULL AS is_markdown,
    NULL AS price_version,
    NULL AS days_at_price,
    NULL AS lowest_price_30d_minor
  UNION ALL
  SELECT
    'P-DUCK-2',
    'DUCK-2',
    'EUR',
    400,
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
    '2026-03-01'::DATE AS rate_date,
    1.1::NUMBER(18, 8) AS rate_to_usd,
    0.9::DECIMAL(18, 8) AS usd_to_rate,
    NULL AS next_rate_date
),

__ref__int_supplier_cost_current AS (
  SELECT
    'DUCK-1' AS sku,
    'S1' AS supplier_code,
    NULL AS supplier_name,
    NULL AS currency_code,
    NULL AS unit_cost_minor,
    5.5::DECIMAL(18, 4) AS unit_cost_usd,
    NULL AS effective_from,
    NULL AS supplier_count,
    NULL AS payment_terms_days,
    NULL AS cost_spread_pct
  UNION ALL
  SELECT
    'DUCK-2',
    'S1',
    NULL,
    NULL,
    NULL,
    5.0::DECIMAL(18, 4),
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_product_catalogue AS (
  SELECT
    'DUCK-1' AS sku,
    NULL AS product_id,
    NULL AS sku_family,
    NULL AS title,
    NULL AS variant_label,
    NULL AS brand_code,
    NULL AS brand_name,
    NULL AS is_private_label,
    NULL AS category_id,
    NULL AS category_slug_path,
    'decoys' AS category_level_1,
    NULL AS material,
    NULL AS weight_kg,
    NULL AS primary_image_url,
    NULL AS image_count,
    NULL AS is_active,
    NULL AS launched_on,
    NULL AS is_bundle_component
  UNION ALL
  SELECT
    'DUCK-2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'decoys',
    NULL,
    NULL,
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

__expected__int_product_margin AS (
  SELECT
    'DUCK-1:EUR' AS sku_price_key,
    10.0::DECIMAL(18, 4) AS list_price,
    4.95::DECIMAL(18, 4) AS unit_cost,
    5.05::DECIMAL(18, 4) AS unit_margin,
    50.5::DECIMAL(9, 2) AS margin_pct,
    FALSE AS is_below_cost,
    'decoys' AS category_level_1
  UNION ALL
  SELECT
    'DUCK-2:EUR' AS sku_price_key,
    4.0::DECIMAL(18, 4) AS list_price,
    4.5::DECIMAL(18, 4) AS unit_cost,
    -0.5::DECIMAL(18, 4) AS unit_margin,
    -12.5::DECIMAL(9, 2) AS margin_pct,
    TRUE AS is_below_cost,
    'decoys' AS category_level_1
)
