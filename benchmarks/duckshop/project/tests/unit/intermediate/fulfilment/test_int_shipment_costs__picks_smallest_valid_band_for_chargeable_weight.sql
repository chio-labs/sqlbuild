TEST (name "int_shipment_costs__picks_smallest_valid_band_for_chargeable_weight");

WITH __ref__stg_shipment_packages AS (
  SELECT
    'P1' AS package_id,
    'S1' AS shipment_id,
    1500 AS weight_grams,
    NULL AS length_cm,
    NULL AS width_cm,
    NULL AS height_cm,
    1.2::DECIMAL(10, 3) AS volumetric_weight_kg,
    NULL AS content_line_count,
    NULL AS contents,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'P2',
    'S1',
    500,
    NULL,
    NULL,
    NULL,
    2.4::DECIMAL(10, 3),
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'P3',
    'S1',
    12000,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_shipments AS (
  SELECT
    'S1' AS shipment_id,
    'O1' AS order_id,
    'W1' AS warehouse_code,
    'FLAPWING' AS carrier_code,
    'STANDARD' AS service_level,
    NULL AS tracking_number,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ AS shipped_at,
    NULL AS delivered_at,
    NULL AS tracking_event_count,
    NULL AS tracking_events,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__ref__stg_warehouses AS (
  SELECT
    'W1' AS warehouse_code,
    NULL AS warehouse_name,
    'DE' AS country_code,
    NULL AS iana_timezone,
    NULL AS opens_local,
    NULL AS closes_local,
    NULL AS opening_minutes,
    NULL AS supports_same_day,
    NULL AS supports_cold_chain,
    NULL AS max_parcel_kg,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__ref__int_orders_enriched AS (
  SELECT
    'O1' AS order_id,
    NULL AS customer_id,
    NULL AS storefront_code,
    NULL AS region_code,
    NULL AS storefront_timezone,
    NULL AS currency_code,
    NULL AS placed_at,
    NULL AS placed_date_local,
    NULL AS order_status,
    NULL AS sales_channel,
    NULL AS line_count,
    NULL AS units,
    NULL AS gross_amount_minor,
    NULL AS discount_amount_minor,
    NULL AS net_amount_minor,
    NULL AS tax_amount_minor,
    NULL AS captured_amount_minor,
    NULL AS outstanding_amount_minor,
    NULL AS promo_code,
    'FR' AS ship_to_country_code,
    NULL AS is_cross_border,
    NULL AS is_first_party_customer,
    NULL AS basket_size,
    NULL AS is_gift,
    NULL AS utm_source,
    NULL AS utm_medium,
    NULL AS utm_campaign,
    NULL AS total_weight_kg
),

__ref__stg_carrier_rate_cards AS (
  SELECT
    'RC1' AS rate_card_id,
    'FLAPWING' AS carrier_code,
    'STANDARD' AS service_level,
    'DE' AS origin_country,
    'FR' AS destination_country,
    'EUR' AS currency_code,
    '2026-01-01'::DATE AS valid_from,
    '2026-12-31'::DATE AS valid_to,
    NULL AS band_count,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT('max_kg', 2, 'amount_minor', 600),
      OBJECT_CONSTRUCT('max_kg', 5, 'amount_minor', 900),
      OBJECT_CONSTRUCT('max_kg', 10, 'amount_minor', 1500)
    )::ARRAY AS bands,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'RC0',
    'FLAPWING',
    'STANDARD',
    'DE',
    'FR',
    'EUR',
    '2025-01-01'::DATE,
    '2025-12-31'::DATE,
    NULL,
    ARRAY_CONSTRUCT(OBJECT_CONSTRUCT('max_kg', 30, 'amount_minor', 100))::ARRAY,
    NULL,
    NULL
),

__expected__int_shipment_costs AS (
  SELECT
    'P1' AS package_id,
    1.5::DECIMAL(10, 3) AS chargeable_weight_kg,
    'actual' AS weight_basis,
    2.0::DECIMAL(10, 3) AS band_max_kg,
    600 AS rate_minor,
    'EUR' AS rate_currency_code,
    TRUE AS has_rate
  UNION ALL
  SELECT
    'P2' AS package_id,
    2.4::DECIMAL(10, 3) AS chargeable_weight_kg,
    'volumetric' AS weight_basis,
    5.0::DECIMAL(10, 3) AS band_max_kg,
    900 AS rate_minor,
    'EUR' AS rate_currency_code,
    TRUE AS has_rate
  UNION ALL
  SELECT
    'P3' AS package_id,
    12.0::DECIMAL(10, 3) AS chargeable_weight_kg,
    'actual' AS weight_basis,
    CAST(NULL AS DECIMAL(10, 3)) AS band_max_kg,
    CAST(NULL AS INT) AS rate_minor,
    CAST(NULL AS VARCHAR) AS rate_currency_code,
    FALSE AS has_rate
)
