SCENARIO (
  description """
    Partner listings are published under a lower-case contract through a star, whose columns
    Snowflake names in upper case, and written back out in the partner's quoted camelCase
  """,
  tags ["edge_case"],
);

WITH __ref__stg_edge_partner_listings AS (
  SELECT
    v.listing_id,
    v.unit_price_minor::NUMBER(38, 0) AS unit_price_minor,
    v.listing_status
  FROM VALUES
    ('LS-MALLARD-01', 1299, 'live'),
    ('LS-TEAL-02', 899, 'out_of_stock'),
    ('ls-teal-02', 905, NULL) AS v(listing_id, unit_price_minor, listing_status)
),

__expected__dim_edge_partner_listings AS (
  SELECT
    v.listing_id,
    v.unit_price_minor::NUMBER(38, 0) AS unit_price_minor,
    v.listing_status
  FROM VALUES
    ('LS-MALLARD-01', 1299, 'live'),
    ('LS-TEAL-02', 899, 'out_of_stock'),
    ('ls-teal-02', 905, NULL) AS v(listing_id, unit_price_minor, listing_status)
),

__expected__rpt_edge_partner_listing_export AS (
  SELECT
    v.listing_id AS "listingId",
    v.unit_price::NUMBER(18, 2) AS "unitPrice",
    v.is_live AS "isLive"
  FROM VALUES
    ('LS-MALLARD-01', 12.99, TRUE),
    ('LS-TEAL-02', 8.99, FALSE),
    ('ls-teal-02', 9.05, NULL) AS v(listing_id, unit_price, is_live)
)
