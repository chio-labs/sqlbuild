TEST (name "rpt_partner_listing_health__shares_listings_by_health_within_a_partner");

WITH __ref__int_partner_listing_status AS (
  SELECT
    'L1' AS listing_id,
    'MKT' AS partner_code,
    'DUCK-L1' AS sku,
    NULL AS listing_state,
    NULL AS listed_at,
    NULL AS days_listed,
    NULL AS product_title,
    NULL AS brand_name,
    NULL AS is_catalogue_active,
    NULL AS current_list_price_minor,
    NULL AS list_price_currency_code,
    NULL AS available_to_promise,
    12.0::NUMBER(5, 2) AS commission_pct,
    TRUE AS fulfilled_by_partner,
    NULL AS fulfilment_method,
    NULL AS term_keys,
    10 AS units_sold_30d,
    NULL AS partners_listing_sku,
    'healthy' AS listing_health
  UNION ALL
  SELECT
    'L2',
    'MKT',
    'DUCK-L2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    15.0::NUMBER(5, 2),
    FALSE,
    NULL,
    NULL,
    5,
    NULL,
    'healthy'
  UNION ALL
  SELECT
    'L3',
    'MKT',
    'DUCK-L3',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    12.0::NUMBER(5, 2),
    FALSE,
    NULL,
    NULL,
    0,
    NULL,
    'out_of_stock'
  UNION ALL
  SELECT
    'L4',
    'MKT',
    'DUCK-L4',
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
    NULL,
    NULL,
    NULL,
    'suppressed'
),

__expected__rpt_partner_listing_health AS (
  SELECT
    'MKT:healthy' AS listing_health_key,
    2 AS listings,
    1 AS partner_fulfilled,
    15 AS units_sold_30d,
    13.5::DECIMAL(5, 2) AS average_commission_pct,
    0.5::DECIMAL(9, 4) AS share_of_partner_listings
  UNION ALL
  SELECT
    'MKT:out_of_stock' AS listing_health_key,
    1 AS listings,
    0 AS partner_fulfilled,
    0 AS units_sold_30d,
    12.0::DECIMAL(5, 2) AS average_commission_pct,
    0.25::DECIMAL(9, 4) AS share_of_partner_listings
  UNION ALL
  SELECT
    'MKT:suppressed' AS listing_health_key,
    1 AS listings,
    1 AS partner_fulfilled,
    CAST(NULL AS INT) AS units_sold_30d,
    CAST(NULL AS DECIMAL(5, 2)) AS average_commission_pct,
    0.25::DECIMAL(9, 4) AS share_of_partner_listings
),

__assert__listing_health_key_is_unique_and_present AS (
  SELECT t.listing_health_key
  FROM __ref("rpt_partner_listing_health") AS t
  GROUP BY
    t.listing_health_key
  HAVING
    COUNT(*) > 1
    OR t.listing_health_key IS NULL
)
