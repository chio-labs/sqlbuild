TEST (name "stg_wishlist_items__uses_the_mocked_sku_normaliser");

WITH __macro__normalise_sku AS (
  SELECT '''MOCKED-SKU''' AS normalised_sku
),

__ref__stg_wishlists AS (
  SELECT
    'W1' AS wishlist_id,
    'C1' AS customer_id,
    NULL AS created_at,
    NULL AS is_public,
    NULL AS item_count,
    ARRAY_CONSTRUCT(
      OBJECT_CONSTRUCT('sku', 'duck_mal 01'),
      OBJECT_CONSTRUCT('sku', 'pond-pump')
    )::ARRAY AS items,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__expected__stg_wishlist_items AS (
  SELECT
    'W1:0' AS wishlist_item_key,
    'MOCKED-SKU' AS sku
  UNION ALL
  SELECT
    'W1:1' AS wishlist_item_key,
    'MOCKED-SKU' AS sku
)
