TEST (name "stg_influencer_posts__keeps_latest_live_version");

WITH __source__growth__influencer_posts AS (
  SELECT
    'K1' AS post_id,
    NULL AS creator_handle,
    NULL AS platform,
    NULL AS posted_at,
    NULL AS promo_code,
    NULL AS metrics,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'K1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'U',
    2,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'I',
    3,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'K2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_influencer_posts AS (
  SELECT
    'K1' AS post_id,
    2 AS source_seq
)
