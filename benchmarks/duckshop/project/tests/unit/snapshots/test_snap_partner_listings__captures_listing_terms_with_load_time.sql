TEST (name "snap_partner_listings__captures_listing_terms_with_load_time");

WITH __ref__stg_partner_listings AS (
  SELECT
    'L1' AS listing_id,
    'MKT' AS partner_code,
    'DUCK-MAL-01' AS sku,
    'active' AS listing_status,
    NULL AS listed_at,
    12.5::DECIMAL(5, 2) AS commission_pct,
    FALSE AS fulfilled_by_partner,
    NULL AS terms,
    NULL AS source_seq,
    '2026-03-01 10:00:00'::TIMESTAMP_NTZ AS source_loaded_at
),

__expected__snap_partner_listings AS (
  SELECT
    'L1' AS listing_id,
    'DUCK-MAL-01' AS sku,
    'active' AS listing_status,
    12.5::DECIMAL(5, 2) AS commission_pct,
    FALSE AS fulfilled_by_partner,
    '2026-03-01 10:00:00'::TIMESTAMPNTZ AS source_loaded_at
),

__assert__listing_id_is_unique_and_present AS (
  SELECT t.listing_id
  FROM __ref("snap_partner_listings") AS t
  GROUP BY
    t.listing_id
  HAVING
    COUNT(*) > 1
    OR t.listing_id IS NULL
)
