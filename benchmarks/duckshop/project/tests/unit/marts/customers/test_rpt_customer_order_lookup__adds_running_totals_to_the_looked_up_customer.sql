TEST (name "rpt_customer_order_lookup__adds_running_totals_to_the_looked_up_customer");

WITH __ref__dim_customers AS (
  SELECT
    'C000001' AS customer_id,
    NULL AS city,
    NULL AS postcode_canonical,
    NULL AS country_code,
    NULL AS region_code,
    NULL AS email_domain,
    NULL AS full_name,
    NULL AS storefront_code,
    NULL AS preferred_language,
    NULL AS created_at,
    NULL AS age_band,
    NULL AS order_count,
    100.0::DECIMAL(18, 2) AS lifetime_revenue_usd,
    NULL AS days_since_last_order,
    'loyal' AS rfm_segment,
    NULL AS is_vip,
    NULL AS email_marketing,
    NULL AS sms_marketing,
    'GOLDEN_DUCK' AS loyalty_tier_code,
    NULL AS is_multi_device,
    NULL AS possible_duplicate_of,
    NULL AS is_marketing_holdout
  UNION ALL
  SELECT
    'C000002',
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
    900.0::DECIMAL(18, 2),
    NULL,
    'champion',
    NULL,
    NULL,
    NULL,
    'PLATINUM_DUCK',
    NULL,
    NULL,
    NULL
),

__table_fn__table_fn__customer_orders AS (
  SELECT
    'O1' AS order_id,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ AS placed_at,
    'DELIVERED' AS order_status,
    40.00::NUMBER(18, 2) AS amount_usd,
    1 AS order_number,
    TRUE AS is_first_order
  UNION ALL
  SELECT
    'O2',
    '2026-03-15 10:00:00 +00:00'::TIMESTAMP_TZ,
    'SHIPPED',
    60.00::NUMBER(18, 2),
    2,
    FALSE
),

__expected__rpt_customer_order_lookup AS (
  SELECT
    'O1' AS order_id,
    'C000001' AS customer_id,
    'loyal' AS rfm_segment,
    'GOLDEN_DUCK' AS loyalty_tier_code,
    40.0::DECIMAL(18, 2) AS running_total_usd,
    0.4::DECIMAL(9, 6) AS share_of_lifetime_revenue
  UNION ALL
  SELECT
    'O2' AS order_id,
    'C000001' AS customer_id,
    'loyal' AS rfm_segment,
    'GOLDEN_DUCK' AS loyalty_tier_code,
    100.0::DECIMAL(18, 2) AS running_total_usd,
    0.6::DECIMAL(9, 6) AS share_of_lifetime_revenue
),

__assert__order_id_is_unique_and_present AS (
  SELECT t.order_id
  FROM __ref("rpt_customer_order_lookup") AS t
  GROUP BY
    t.order_id
  HAVING
    COUNT(*) > 1
    OR t.order_id IS NULL
)
