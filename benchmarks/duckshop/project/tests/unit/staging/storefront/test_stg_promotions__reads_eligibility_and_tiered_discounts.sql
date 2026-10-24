TEST (name "stg_promotions__reads_eligibility_and_tiered_discounts");

WITH __source__storefront__promotions AS (
  SELECT
    'spring10 ' AS promo_code,
    'Spring Splash' AS promo_name,
    '2026-03-01 00:00:00 +00:00'::TIMESTAMP_TZ AS starts_at,
    NULL AS ends_at,
    NULL AS is_stackable,
    OBJECT_CONSTRUCT(
      'eligibility',
      OBJECT_CONSTRUCT(
        'min_order_minor',
        2000,
        'regions',
        ARRAY_CONSTRUCT('EU', 'US')
      ),
      'tiers',
      ARRAY_CONSTRUCT(
        OBJECT_CONSTRUCT('pct', 5),
        OBJECT_CONSTRUCT('pct', 12.5)
      )
    )::VARIANT AS rules,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'pond5',
    'Pond Week',
    '2026-04-01 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    TRUE,
    PARSE_JSON('{}')::VARIANT,
    'I',
    2,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'old',
    'Old',
    '2025-01-01 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    PARSE_JSON('{}')::VARIANT,
    'I',
    3,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'old',
    'Old',
    '2025-01-01 00:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    PARSE_JSON('{}')::VARIANT,
    'D',
    4,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_promotions AS (
  SELECT
    'SPRING10' AS promo_code,
    FALSE AS is_stackable,
    2000 AS min_order_minor,
    2 AS tier_count,
    12.5::DECIMAL(5, 2) AS max_discount_pct,
    1 AS source_seq
  UNION ALL
  SELECT
    'POND5' AS promo_code,
    TRUE AS is_stackable,
    0 AS min_order_minor,
    0 AS tier_count,
    CAST(NULL AS DECIMAL(5, 2)) AS max_discount_pct,
    2 AS source_seq
)
