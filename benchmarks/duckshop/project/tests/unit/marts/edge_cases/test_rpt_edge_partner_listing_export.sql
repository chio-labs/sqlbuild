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
    'LS-EIDER-03' AS "listingId",
    0.05::NUMBER(18, 2) AS "unitPrice",
    CAST(NULL AS BOOLEAN) AS "isLive"
  UNION ALL
  SELECT
    'LS-MALLARD-01' AS "listingId",
    12.99::NUMBER(18, 2) AS "unitPrice",
    TRUE AS "isLive"
  UNION ALL
  SELECT
    'LS-TEAL-02' AS "listingId",
    8.99::NUMBER(18, 2) AS "unitPrice",
    FALSE AS "isLive"
)
