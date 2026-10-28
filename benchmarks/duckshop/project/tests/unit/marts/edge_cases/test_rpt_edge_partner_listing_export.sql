TEST (name "rpt_edge_partner_listing_export__writes_the_feed_in_quoted_camel_case");

WITH __ref__dim_edge_partner_listings AS (
  SELECT
    v.listing_id,
    v.unit_price_minor::NUMBER(38, 0) AS unit_price_minor,
    v.listing_status
  FROM VALUES
    ('LS-MALLARD-01', 1299, 'live'),
    ('LS-TEAL-02', 899, 'out_of_stock'),
    ('LS-EIDER-03', 5, NULL) AS v(listing_id, unit_price_minor, listing_status)
),

__expected__rpt_edge_partner_listing_export AS (
  SELECT
    v.listing_id AS "listingId",
    v.unit_price AS "unitPrice",
    v.is_live AS "isLive"
  FROM VALUES
    ('LS-MALLARD-01', 12.99, TRUE),
    ('LS-TEAL-02', 8.99, FALSE),
    ('LS-EIDER-03', 0.05, NULL) AS v(listing_id, unit_price, is_live)
)
