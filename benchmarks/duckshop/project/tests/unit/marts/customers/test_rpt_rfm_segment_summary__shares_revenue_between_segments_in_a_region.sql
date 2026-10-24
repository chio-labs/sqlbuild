TEST (name "rpt_rfm_segment_summary__shares_revenue_between_segments_in_a_region");

WITH __ref__dim_customers AS (
  SELECT
    'C1' AS customer_id,
    NULL AS city,
    NULL AS postcode_canonical,
    NULL AS country_code,
    'EU' AS region_code,
    NULL AS email_domain,
    NULL AS full_name,
    NULL AS storefront_code,
    NULL AS preferred_language,
    NULL AS created_at,
    NULL AS age_band,
    NULL AS order_count,
    300.0::DECIMAL(18, 2) AS lifetime_revenue_usd,
    5 AS days_since_last_order,
    'champion' AS rfm_segment,
    TRUE AS is_vip,
    NULL AS email_marketing,
    NULL AS sms_marketing,
    NULL AS loyalty_tier_code,
    NULL AS is_multi_device,
    NULL AS possible_duplicate_of,
    NULL AS is_marketing_holdout
  UNION ALL
  SELECT
    'C2',
    NULL,
    NULL,
    NULL,
    'EU',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    100.0::DECIMAL(18, 2),
    15,
    'champion',
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'C3',
    NULL,
    NULL,
    NULL,
    'EU',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    100.0::DECIMAL(18, 2),
    200,
    'at_risk',
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'C4',
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
    0.0::DECIMAL(18, 2),
    NULL,
    'prospect',
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__rpt_rfm_segment_summary AS (
  SELECT
    'EU:champion' AS segment_key,
    2 AS customers,
    1 AS vip_customers,
    400.0::DECIMAL(18, 2) AS lifetime_revenue_usd,
    0.8::DECIMAL(9, 4) AS revenue_share_in_region,
    10.0::DECIMAL(10, 2) AS median_days_since_last_order
  UNION ALL
  SELECT
    'EU:at_risk' AS segment_key,
    1 AS customers,
    0 AS vip_customers,
    100.0::DECIMAL(18, 2) AS lifetime_revenue_usd,
    0.2::DECIMAL(9, 4) AS revenue_share_in_region,
    200.0::DECIMAL(10, 2) AS median_days_since_last_order
  UNION ALL
  SELECT
    'UNKNOWN:prospect' AS segment_key,
    1 AS customers,
    0 AS vip_customers,
    0.0::DECIMAL(18, 2) AS lifetime_revenue_usd,
    CAST(NULL AS DECIMAL(9, 4)) AS revenue_share_in_region,
    CAST(NULL AS DECIMAL(10, 2)) AS median_days_since_last_order
),

__assert__segment_key_is_unique_and_present AS (
  SELECT t.segment_key
  FROM __ref("rpt_rfm_segment_summary") AS t
  GROUP BY
    t.segment_key
  HAVING
    COUNT(*) > 1
    OR t.segment_key IS NULL
)
