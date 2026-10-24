TEST (name "int_product_view_affinity__scores_co_views_within_an_hour");

WITH __ref__stg_web_product_views AS (
  SELECT
    'V1' AS anonymous_id,
    NULL AS customer_id,
    'V1:DUCK-1:2026-03-10 10:00:00' AS product_view_key,
    'DUCK-1' AS sku,
    '2026-03-10 10:00:00'::TIMESTAMPNTZ AS viewed_minute_utc,
    NULL AS list_name,
    NULL AS list_position
  UNION ALL
  SELECT
    'V1',
    NULL,
    'V1:DUCK-2:2026-03-10 10:30:00',
    'DUCK-2',
    '2026-03-10 10:30:00'::TIMESTAMPNTZ,
    NULL,
    NULL
  UNION ALL
  SELECT
    'V1',
    NULL,
    'V1:DUCK-3:2026-03-10 11:30:00',
    'DUCK-3',
    '2026-03-10 11:30:00'::TIMESTAMPNTZ,
    NULL,
    NULL
  UNION ALL
  SELECT
    'V2',
    NULL,
    'V2:DUCK-1:2026-03-10 09:00:00',
    'DUCK-1',
    '2026-03-10 09:00:00'::TIMESTAMPNTZ,
    NULL,
    NULL
  UNION ALL
  SELECT
    'V2',
    NULL,
    'V2:DUCK-2:2026-03-10 09:10:00',
    'DUCK-2',
    '2026-03-10 09:10:00'::TIMESTAMPNTZ,
    NULL,
    NULL
  UNION ALL
  SELECT
    'V2',
    NULL,
    'V2:DUCK-3:2026-03-10 09:50:00',
    'DUCK-3',
    '2026-03-10 09:50:00'::TIMESTAMPNTZ,
    NULL,
    NULL
  UNION ALL
  SELECT
    'V3',
    NULL,
    'V3:DUCK-2:2026-03-10 12:00:00',
    'DUCK-2',
    '2026-03-10 12:00:00'::TIMESTAMPNTZ,
    NULL,
    NULL
),

__expected__int_product_view_affinity AS (
  SELECT
    'DUCK-1>DUCK-2' AS sku_pair_key,
    2 AS co_viewers,
    2 AS sku_viewers,
    1.0::DECIMAL(9, 6) AS co_view_rate,
    1.0::DECIMAL(12, 4) AS lift,
    1 AS pair_rank
  UNION ALL
  SELECT
    'DUCK-1>DUCK-3' AS sku_pair_key,
    1 AS co_viewers,
    2 AS sku_viewers,
    0.5::DECIMAL(9, 6) AS co_view_rate,
    0.75::DECIMAL(12, 4) AS lift,
    2 AS pair_rank
  UNION ALL
  SELECT
    'DUCK-2>DUCK-3' AS sku_pair_key,
    2 AS co_viewers,
    3 AS sku_viewers,
    0.666667::DECIMAL(9, 6) AS co_view_rate,
    1.0::DECIMAL(12, 4) AS lift,
    1 AS pair_rank
)
