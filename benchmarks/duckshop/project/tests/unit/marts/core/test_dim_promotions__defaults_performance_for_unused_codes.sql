TEST (name "dim_promotions__defaults_performance_for_unused_codes");

WITH __ref__stg_promotions AS (
  SELECT
    'SPRING10' AS promo_code,
    'Spring Splash' AS promo_name,
    NULL AS starts_at,
    NULL AS ends_at,
    FALSE AS is_stackable,
    NULL AS rules,
    2000 AS min_order_minor,
    NULL AS eligible_regions,
    NULL AS tier_count,
    NULL AS max_discount_pct,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'POND5',
    'Pond Week',
    NULL,
    NULL,
    TRUE,
    NULL,
    0,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_promotion_performance AS (
  SELECT
    'SPRING10' AS promo_code,
    NULL AS promo_name,
    TRUE AS is_active_now,
    3 AS redemption_count,
    NULL AS redeeming_customers,
    120.5::DECIMAL(18, 2) AS revenue_usd,
    NULL AS discount_usd,
    0.1::DECIMAL(9, 6) AS discount_rate,
    NULL AS avg_order_usd,
    NULL AS baseline_avg_order_usd,
    12.5::DECIMAL(9, 2) AS basket_uplift_pct,
    NULL AS top_tier_threshold_minor,
    NULL AS eligible_region_count
),

__expected__dim_promotions AS (
  SELECT
    'SPRING10' AS promo_code,
    TRUE AS is_active_now,
    3 AS redemption_count,
    120.5::DECIMAL(18, 2) AS revenue_usd,
    0.1::DECIMAL(9, 6) AS discount_rate,
    12.5::DECIMAL(9, 2) AS basket_uplift_pct,
    2000 AS min_order_minor
  UNION ALL
  SELECT
    'POND5' AS promo_code,
    FALSE AS is_active_now,
    0 AS redemption_count,
    0.0::DECIMAL(18, 2) AS revenue_usd,
    CAST(NULL AS DECIMAL(9, 6)) AS discount_rate,
    CAST(NULL AS DECIMAL(9, 2)) AS basket_uplift_pct,
    0 AS min_order_minor
),

__assert__promo_code_is_unique_and_present AS (
  SELECT t.promo_code
  FROM __ref("dim_promotions") AS t
  GROUP BY
    t.promo_code
  HAVING
    COUNT(*) > 1
    OR t.promo_code IS NULL
)
