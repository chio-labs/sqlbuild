TEST (name "int_partner_listing_status__grades_listing_health_from_catalogue_stock_and_price");

WITH __ref__stg_partner_listings AS (
  SELECT
    'LS1' AS listing_id,
    'MKT' AS partner_code,
    'DUCK-1' AS sku,
    'live' AS listing_status,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ AS listed_at,
    15.0::DECIMAL(5, 2) AS commission_pct,
    FALSE AS fulfilled_by_partner,
    PARSE_JSON('{"shipping": "free", "returns": 30}')::OBJECT AS terms,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'LS2',
    'OTHER',
    'DUCK-1',
    'on_sale',
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    12.0::DECIMAL(5, 2),
    TRUE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'LS3',
    'MKT',
    'DUCK-2',
    'out_of_stock',
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'LS4',
    'MKT',
    'DUCK-9',
    'published',
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'LS5',
    'MKT',
    'DUCK-3',
    'live',
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'LS6',
    'MKT',
    'DUCK-4',
    'pending_review',
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'LS7',
    'MKT',
    'DUCK-5',
    'live',
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'LS8',
    'OTHER',
    'DUCK-6',
    'live',
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    TRUE,
    NULL,
    NULL,
    NULL
),

__ref__int_product_catalogue AS (
  SELECT
    'DUCK-1' AS sku,
    NULL AS product_id,
    NULL AS sku_family,
    'Mallard Classic Duck' AS title,
    NULL AS variant_label,
    NULL AS brand_code,
    'Mallard & Co.' AS brand_name,
    NULL AS is_private_label,
    NULL AS category_id,
    NULL AS category_slug_path,
    NULL AS category_level_1,
    NULL AS material,
    NULL AS weight_kg,
    NULL AS primary_image_url,
    NULL AS image_count,
    TRUE AS is_active,
    NULL AS launched_on,
    NULL AS is_bundle_component
  UNION ALL
  SELECT
    'DUCK-2',
    NULL,
    NULL,
    'Pintail Mug',
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
    TRUE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'DUCK-3',
    NULL,
    NULL,
    'Retired Eider Decoy',
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
    FALSE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'DUCK-4',
    NULL,
    NULL,
    'Merganser Teapot',
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
    TRUE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'DUCK-5',
    NULL,
    NULL,
    'Teal Pond Pump',
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
    TRUE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'DUCK-6',
    NULL,
    NULL,
    'Paddling Six Bundle',
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
    TRUE,
    NULL,
    NULL
),

__ref__int_reservations_open AS (
  SELECT
    'DUCK-1|W1' AS stock_key,
    'DUCK-1' AS sku,
    'W1' AS warehouse_code,
    NULL AS open_reservations,
    NULL AS reserved_qty,
    NULL AS backordered_qty,
    NULL AS on_hand_qty,
    5 AS available_to_promise,
    NULL AS oldest_reserved_at
  UNION ALL
  SELECT
    'DUCK-1|W2',
    'DUCK-1',
    'W2',
    NULL,
    NULL,
    NULL,
    NULL,
    -3,
    NULL
),

__ref__int_price_history AS (
  SELECT
    'P1' AS price_list_id,
    'DUCK-1' AS sku,
    'USD' AS currency_code,
    2999 AS list_amount_minor,
    '2026-01-01 00:00:00 +00:00'::TIMESTAMPTZ AS valid_from,
    NULL AS effective_valid_to,
    NULL AS previous_amount_minor,
    NULL AS change_pct,
    NULL AS is_markdown,
    NULL AS price_version,
    NULL AS days_at_price,
    NULL AS lowest_price_30d_minor
  UNION ALL
  SELECT
    'P2',
    'DUCK-1',
    'EUR',
    2799,
    '2026-02-01 00:00:00 +00:00'::TIMESTAMPTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'P0',
    'DUCK-1',
    'USD',
    3199,
    '2025-01-01 00:00:00 +00:00'::TIMESTAMPTZ,
    '2026-01-01 00:00:00 +00:00'::TIMESTAMPTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'P3',
    'DUCK-5',
    'EUR',
    4500,
    '2026-01-01 00:00:00 +00:00'::TIMESTAMPTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_partner_orders_unified AS (
  SELECT
    'PK1' AS partner_order_key,
    NULL AS source_relation,
    NULL AS payload_version,
    'MKT' AS partner_code,
    NULL AS external_order_id,
    NULL AS currency_code,
    NULL AS placed_at_utc,
    '2026-03-20'::DATE AS placed_date,
    NULL AS order_total_minor,
    NULL AS order_total_usd,
    NULL AS line_count,
    NULL AS units,
    NULL AS lines_total_minor,
    NULL AS lines_match_total,
    NULL AS customer_id,
    NULL AS is_known_customer,
    NULL AS order_rank_for_partner
  UNION ALL
  SELECT
    'PK2',
    NULL,
    NULL,
    'MKT',
    NULL,
    NULL,
    NULL,
    '2026-02-15'::DATE,
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
    'PK3',
    NULL,
    NULL,
    'OTHER',
    NULL,
    NULL,
    NULL,
    '2026-03-30'::DATE,
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

__ref__stg_partner_order_lines AS (
  SELECT
    'PK1#1' AS partner_order_line_key,
    'PK1' AS partner_order_key,
    NULL AS payload_version,
    'DUCK-1' AS sku,
    3 AS quantity,
    2999::DECIMAL(38, 0) AS unit_amount_minor
  UNION ALL
  SELECT
    'PK2#1',
    'PK2',
    NULL,
    'DUCK-1',
    10,
    2999::DECIMAL(38, 0)
  UNION ALL
  SELECT
    'PK3#1',
    'PK3',
    NULL,
    'DUCK-1',
    1,
    2999::DECIMAL(38, 0)
),

__expected__int_partner_listing_status AS (
  SELECT
    'LS1' AS listing_id,
    'live' AS listing_state,
    30 AS days_listed,
    2999 AS current_list_price_minor,
    'USD' AS list_price_currency_code,
    5 AS available_to_promise,
    'home_delivery' AS fulfilment_method,
    3 AS units_sold_30d,
    2 AS partners_listing_sku,
    'healthy' AS listing_health
  UNION ALL
  SELECT
    'LS2' AS listing_id,
    'live' AS listing_state,
    30 AS days_listed,
    2999 AS current_list_price_minor,
    'USD' AS list_price_currency_code,
    5 AS available_to_promise,
    'partner' AS fulfilment_method,
    1 AS units_sold_30d,
    2 AS partners_listing_sku,
    'healthy' AS listing_health
  UNION ALL
  SELECT
    'LS3' AS listing_id,
    'paused' AS listing_state,
    30 AS days_listed,
    CAST(NULL AS INT) AS current_list_price_minor,
    CAST(NULL AS VARCHAR) AS list_price_currency_code,
    0 AS available_to_promise,
    'home_delivery' AS fulfilment_method,
    0 AS units_sold_30d,
    1 AS partners_listing_sku,
    'not_live' AS listing_health
  UNION ALL
  SELECT
    'LS4' AS listing_id,
    'live' AS listing_state,
    30 AS days_listed,
    CAST(NULL AS INT) AS current_list_price_minor,
    CAST(NULL AS VARCHAR) AS list_price_currency_code,
    0 AS available_to_promise,
    'home_delivery' AS fulfilment_method,
    0 AS units_sold_30d,
    1 AS partners_listing_sku,
    'unknown_sku' AS listing_health
  UNION ALL
  SELECT
    'LS5' AS listing_id,
    'live' AS listing_state,
    30 AS days_listed,
    CAST(NULL AS INT) AS current_list_price_minor,
    CAST(NULL AS VARCHAR) AS list_price_currency_code,
    0 AS available_to_promise,
    'home_delivery' AS fulfilment_method,
    0 AS units_sold_30d,
    1 AS partners_listing_sku,
    'discontinued' AS listing_health
  UNION ALL
  SELECT
    'LS6' AS listing_id,
    'draft' AS listing_state,
    30 AS days_listed,
    CAST(NULL AS INT) AS current_list_price_minor,
    CAST(NULL AS VARCHAR) AS list_price_currency_code,
    0 AS available_to_promise,
    'home_delivery' AS fulfilment_method,
    0 AS units_sold_30d,
    1 AS partners_listing_sku,
    'not_live' AS listing_health
  UNION ALL
  SELECT
    'LS7' AS listing_id,
    'live' AS listing_state,
    30 AS days_listed,
    4500 AS current_list_price_minor,
    'EUR' AS list_price_currency_code,
    0 AS available_to_promise,
    'home_delivery' AS fulfilment_method,
    0 AS units_sold_30d,
    1 AS partners_listing_sku,
    'unfulfillable' AS listing_health
  UNION ALL
  SELECT
    'LS8' AS listing_id,
    'live' AS listing_state,
    30 AS days_listed,
    CAST(NULL AS INT) AS current_list_price_minor,
    CAST(NULL AS VARCHAR) AS list_price_currency_code,
    0 AS available_to_promise,
    'partner' AS fulfilment_method,
    0 AS units_sold_30d,
    1 AS partners_listing_sku,
    'unpriced' AS listing_health
),

__assert__term_keys_list_object_keys AS (
  SELECT l.listing_id
  FROM __ref("int_partner_listing_status") AS l
  WHERE ARRAY_TO_STRING(l.term_keys, ',') <> IFF(l.listing_id = 'LS1', 'returns,shipping', '')
)
