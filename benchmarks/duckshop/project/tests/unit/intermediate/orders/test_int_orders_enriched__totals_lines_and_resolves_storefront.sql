TEST (name "int_orders_enriched__totals_lines_and_resolves_storefront");

WITH __ref__stg_orders AS (
  SELECT
    'O1' AS order_id,
    'C1' AS customer_id,
    'DE' AS storefront_code,
    'EUR' AS currency_code,
    '2026-03-28 23:30:00 +00:00'::TIMESTAMP_TZ AS placed_at,
    'PAID' AS order_status,
    NULL AS sales_channel,
    NULL AS is_gift,
    'Search_Ads' AS utm_source,
    NULL AS utm_medium,
    NULL AS utm_campaign,
    NULL AS device_type,
    NULL AS item_count_hint,
    'A1' AS shipping_address_id,
    NULL AS attributes,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'O2',
    'C2',
    'ZZ',
    'USD',
    '2026-03-28 23:30:00 +00:00'::TIMESTAMP_TZ,
    'PENDING',
    'app',
    NULL,
    '',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_order_lines_priced AS (
  SELECT
    'L1' AS order_line_id,
    'O1' AS order_id,
    NULL AS sku,
    NULL AS sku_family,
    NULL AS product_id,
    4 AS quantity,
    NULL AS unit_amount_minor,
    NULL AS list_amount_minor,
    NULL AS markdown_pct,
    4000 AS gross_amount_minor,
    3500 AS net_amount_minor,
    500 AS discount_amount_minor,
    700 AS tax_amount_minor,
    1.5::DECIMAL(12, 3) AS line_weight_kg,
    NULL AS has_list_price
  UNION ALL
  SELECT
    'L2',
    'O1',
    NULL,
    NULL,
    NULL,
    3,
    NULL,
    NULL,
    NULL,
    1500,
    1500,
    0,
    300,
    0.5::DECIMAL(12, 3),
    NULL
),

__ref__stg_customers AS (
  SELECT
    'C1' AS customer_id,
    'ada@duckshop.test' AS email_normalised,
    NULL AS phone_normalised,
    NULL AS first_name,
    NULL AS last_name,
    'EU' AS region_code,
    NULL AS storefront_code,
    NULL AS created_at,
    NULL AS preferred_language,
    NULL AS marketing_opt_in,
    NULL AS consent_types,
    NULL AS birth_year,
    NULL AS preferences,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'C2',
    'bob@example.org',
    NULL,
    NULL,
    NULL,
    'US',
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

__ref__stg_payments AS (
  SELECT
    'P1' AS payment_id,
    'O1' AS order_id,
    NULL AS payment_method,
    4000 AS amount_minor,
    NULL AS currency_code,
    NULL AS authorised_at,
    NULL AS captured_at,
    NULL AS card_bin,
    'captured' AS gateway_status,
    NULL AS gateway_error_code,
    NULL AS risk_score,
    NULL AS three_ds_outcome,
    NULL AS gateway_reference,
    NULL AS gateway_response,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'P2',
    'O1',
    NULL,
    6000,
    NULL,
    NULL,
    NULL,
    NULL,
    'declined',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_customer_addresses AS (
  SELECT
    'A1' AS address_id,
    'C1' AS customer_id,
    NULL AS line1,
    NULL AS line2,
    NULL AS city,
    'FR' AS country_code,
    NULL AS postcode_canonical,
    NULL AS is_default,
    NULL AS valid_from,
    NULL AS latitude,
    NULL AS longitude,
    NULL AS geo,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__ref__stg_promotion_redemptions AS (
  SELECT
    'R2' AS redemption_id,
    'LATE' AS promo_code,
    'O1' AS order_id,
    NULL AS discount_minor,
    '2026-03-28 23:31:00 +00:00'::TIMESTAMP_TZ AS redeemed_at,
    NULL AS entry_method,
    NULL AS redemption_context,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'R1',
    'EARLY',
    'O1',
    NULL,
    '2026-03-28 23:30:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL
),

__seed__countries AS (
  SELECT
    'DE' AS country_code,
    NULL AS country_name,
    'EU' AS region_code,
    'Europe/Berlin' AS default_timezone,
    NULL AS currency_code,
    NULL AS vat_registered
),

__expected__int_orders_enriched AS (
  SELECT
    'O1' AS order_id,
    'EU' AS region_code,
    'Europe/Berlin' AS storefront_timezone,
    '2026-03-29'::DATE AS placed_date_local,
    'web' AS sales_channel,
    2 AS line_count,
    7 AS units,
    5000 AS net_amount_minor,
    1000 AS tax_amount_minor,
    4000 AS captured_amount_minor,
    2000 AS outstanding_amount_minor,
    'EARLY' AS promo_code,
    'FR' AS ship_to_country_code,
    TRUE AS is_cross_border,
    TRUE AS is_first_party_customer,
    'LARGE' AS basket_size,
    'search_ads' AS utm_source,
    2.0::DECIMAL(12, 3) AS total_weight_kg
  UNION ALL
  SELECT
    'O2' AS order_id,
    'US' AS region_code,
    'UTC' AS storefront_timezone,
    '2026-03-28'::DATE AS placed_date_local,
    'app' AS sales_channel,
    0 AS line_count,
    0 AS units,
    0 AS net_amount_minor,
    0 AS tax_amount_minor,
    0 AS captured_amount_minor,
    0 AS outstanding_amount_minor,
    CAST(NULL AS VARCHAR) AS promo_code,
    CAST(NULL AS VARCHAR) AS ship_to_country_code,
    FALSE AS is_cross_border,
    FALSE AS is_first_party_customer,
    'SINGLE' AS basket_size,
    CAST(NULL AS VARCHAR) AS utm_source,
    0.0::DECIMAL(12, 3) AS total_weight_kg
)
