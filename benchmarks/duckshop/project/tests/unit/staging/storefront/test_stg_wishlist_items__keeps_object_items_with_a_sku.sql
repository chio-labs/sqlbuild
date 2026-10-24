TEST (name "stg_wishlist_items__keeps_object_items_with_a_sku");

WITH __ref__stg_wishlists AS (
  SELECT
    'W1' AS wishlist_id,
    'C1' AS customer_id,
    NULL AS created_at,
    NULL AS is_public,
    NULL AS item_count,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT(
        'sku',
        'duck_mal 01',
        'added_at',
        '2026-03-01 10:00:00 +00:00'
      ),
      'DUCK-LEGACY',
      OBJECT_CONSTRUCT('added_at', '2026-03-02'),
      OBJECT_CONSTRUCT('sku', 'pond-pump')
    )::ARRAY AS items,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__expected__stg_wishlist_items AS (
  SELECT
    'W1:0' AS wishlist_item_key,
    'C1' AS customer_id,
    'DUCK-MAL01' AS sku,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMPTZ AS added_at,
    0 AS item_position
  UNION ALL
  SELECT
    'W1:3' AS wishlist_item_key,
    'C1' AS customer_id,
    'POND-PUMP' AS sku,
    CAST(NULL AS TIMESTAMPTZ) AS added_at,
    3 AS item_position
)
