TEST (name "int_bundle_pricing__prices_bundles_by_pricing_mode");

WITH __ref__stg_bundles AS (
  SELECT
    'B1' AS bundle_sku,
    NULL AS title,
    NULL AS active_from,
    NULL AS active_to,
    'percent_off' AS pricing_mode,
    NULL AS fixed_amount_minor,
    10::DECIMAL(5, 2) AS percent_off,
    NULL AS pricing_currency_code,
    NULL AS pricing,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'B2',
    NULL,
    NULL,
    NULL,
    'cheapest_free',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_bundle_components AS (
  SELECT
    'X1' AS component_id,
    'B1' AS bundle_sku,
    'DUCK-1' AS component_sku,
    2 AS quantity,
    FALSE AS is_optional,
    NULL AS substitute_skus,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'X2',
    'B1',
    'DUCK-2',
    1,
    FALSE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'X3',
    'B1',
    'DUCK-3',
    1,
    TRUE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'X4',
    'B2',
    'DUCK-1',
    1,
    FALSE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'X5',
    'B2',
    'DUCK-4',
    1,
    FALSE,
    NULL,
    NULL,
    NULL
),

__ref__int_price_history AS (
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
    500,
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
    'P-DUCK-3',
    'DUCK-3',
    'EUR',
    9999,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__int_bundle_pricing AS (
  SELECT
    'B1:EUR' AS bundle_price_key,
    2 AS component_count,
    2500 AS components_list_minor,
    2250 AS bundle_price_minor,
    250 AS saving_minor,
    10.0::DECIMAL(9, 4) AS saving_pct,
    FALSE AS has_unpriced_component
  UNION ALL
  SELECT
    'B2:EUR' AS bundle_price_key,
    2 AS component_count,
    1000 AS components_list_minor,
    0 AS bundle_price_minor,
    1000 AS saving_minor,
    100.0::DECIMAL(9, 4) AS saving_pct,
    TRUE AS has_unpriced_component
)
