TEST (name "rpt_influencer_leaderboard__ranks_creators_within_their_main_platform");

WITH __ref__int_influencer_promo_orders AS (
  SELECT
    'IP1' AS post_id,
    '@wren_waddles' AS creator_handle,
    'short_video' AS platform,
    NULL AS posted_at,
    NULL AS promo_code,
    1000 AS impressions,
    100 AS engagements,
    NULL AS saves,
    NULL AS has_tracking_link,
    2 AS credited_orders,
    NULL AS credited_customers,
    50.0::DECIMAL(18, 2) AS credited_revenue_usd,
    5.0::DECIMAL(18, 2) AS discount_given_usd,
    NULL AS first_order_hours_after_post,
    NULL AS orders_per_thousand_impressions
  UNION ALL
  SELECT
    'IP2',
    '@wren_waddles',
    'short_video',
    NULL,
    NULL,
    2000,
    200,
    NULL,
    NULL,
    3,
    NULL,
    70.0::DECIMAL(18, 2),
    7.0::DECIMAL(18, 2),
    NULL,
    NULL
  UNION ALL
  SELECT
    'IP3',
    '@wren_waddles',
    'photo_feed',
    NULL,
    NULL,
    500,
    50,
    NULL,
    NULL,
    0,
    NULL,
    0.0::DECIMAL(18, 2),
    0.0::DECIMAL(18, 2),
    NULL,
    NULL
  UNION ALL
  SELECT
    'IP4',
    '@reedbed_rae',
    'short_video',
    NULL,
    NULL,
    800,
    80,
    NULL,
    NULL,
    4,
    NULL,
    200.0::DECIMAL(18, 2),
    20.0::DECIMAL(18, 2),
    NULL,
    NULL
  UNION ALL
  SELECT
    'IP5',
    '@teal_tom',
    'photo_feed',
    NULL,
    NULL,
    300,
    30,
    NULL,
    NULL,
    1,
    NULL,
    25.0::DECIMAL(18, 2),
    2.5::DECIMAL(18, 2),
    NULL,
    NULL
),

__expected__rpt_influencer_leaderboard AS (
  SELECT
    '@wren_waddles' AS creator_handle,
    'short_video' AS primary_platform,
    3 AS posts,
    3500 AS impressions,
    350 AS engagements,
    5 AS credited_orders,
    120.0::DECIMAL(18, 2) AS credited_revenue_usd,
    12.0::DECIMAL(18, 2) AS discount_given_usd,
    2 AS revenue_rank
  UNION ALL
  SELECT
    '@reedbed_rae' AS creator_handle,
    'short_video' AS primary_platform,
    1 AS posts,
    800 AS impressions,
    80 AS engagements,
    4 AS credited_orders,
    200.0::DECIMAL(18, 2) AS credited_revenue_usd,
    20.0::DECIMAL(18, 2) AS discount_given_usd,
    1 AS revenue_rank
  UNION ALL
  SELECT
    '@teal_tom' AS creator_handle,
    'photo_feed' AS primary_platform,
    1 AS posts,
    300 AS impressions,
    30 AS engagements,
    1 AS credited_orders,
    25.0::DECIMAL(18, 2) AS credited_revenue_usd,
    2.5::DECIMAL(18, 2) AS discount_given_usd,
    1 AS revenue_rank
),

__assert__creator_handle_is_unique_and_present AS (
  SELECT t.creator_handle
  FROM __ref("rpt_influencer_leaderboard") AS t
  GROUP BY
    t.creator_handle
  HAVING
    COUNT(*) > 1
    OR t.creator_handle IS NULL
)
