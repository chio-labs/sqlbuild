TEST (name "dim_edge_partner_listings__publishes_a_star_under_a_lower_case_contract");

WITH __ref__stg_edge_partner_listings AS (
  SELECT
    v.listing_id,
    v.unit_price_minor::NUMBER(38, 0) AS unit_price_minor,
    v.listing_status
  FROM VALUES
    ('LS-MALLARD-01', 1299, 'live'),
    ('LS-TEAL-02', 899, 'out_of_stock') AS v(listing_id, unit_price_minor, listing_status)
),

__expected__dim_edge_partner_listings AS (
  SELECT
    'LS-MALLARD-01' AS listing_id,
    1299 AS unit_price_minor,
    'live' AS listing_status
  UNION ALL
  SELECT
    'LS-TEAL-02' AS listing_id,
    899 AS unit_price_minor,
    'out_of_stock' AS listing_status
)
