TEST (name "dim_campaigns__derives_flight_state_and_age_range");

WITH __ref__stg_campaigns AS (
  SELECT
    'CMP1' AS campaign_id,
    'Spring Splash' AS campaign_name,
    'social' AS channel,
    NULL AS objective,
    '2026-03-01'::DATE AS starts_on,
    NULL AS ends_on,
    NULL AS budget_minor,
    NULL AS currency_code,
    NULL AS target_regions,
    NULL AS target_age_min,
    NULL AS target_age_max,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'CMP2',
    'Pond Week',
    'email',
    NULL,
    '2026-04-15'::DATE,
    '2026-04-30'::DATE,
    NULL,
    NULL,
    NULL,
    18,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'CMP3',
    'Golden Duck Winter',
    'search',
    NULL,
    '2026-01-01'::DATE,
    '2026-02-28'::DATE,
    NULL,
    NULL,
    NULL,
    25,
    54,
    NULL,
    NULL
),

__ref__int_campaign_performance AS (
  SELECT
    'CMP1' AS campaign_id,
    NULL AS campaign_name,
    NULL AS channel,
    NULL AS objective,
    NULL AS starts_on,
    NULL AS ends_on,
    1100.0::DECIMAL(18, 2) AS budget_usd,
    550.0::DECIMAL(18, 2) AS spend_usd,
    NULL AS budget_used_pct,
    NULL AS paid_clicks,
    NULL AS email_clicks,
    NULL AS attributed_sessions,
    NULL AS attributed_orders,
    NULL AS attributed_revenue_usd,
    0.1818::DECIMAL(12, 4) AS return_on_ad_spend,
    NULL AS target_region_count,
    NULL AS unsupported_target_regions,
    NULL AS spend_rank_in_channel
),

__expected__dim_campaigns AS (
  SELECT
    'CMP1' AS campaign_id,
    31 AS flight_days,
    'live' AS campaign_state,
    'all' AS target_age_range,
    1100.0::DECIMAL(18, 2) AS budget_usd,
    550.0::DECIMAL(18, 2) AS spend_usd,
    0.1818::DECIMAL(12, 4) AS return_on_ad_spend
  UNION ALL
  SELECT
    'CMP2' AS campaign_id,
    16 AS flight_days,
    'scheduled' AS campaign_state,
    '18-' AS target_age_range,
    CAST(NULL AS DECIMAL(18, 2)) AS budget_usd,
    CAST(NULL AS DECIMAL(18, 2)) AS spend_usd,
    CAST(NULL AS DECIMAL(12, 4)) AS return_on_ad_spend
  UNION ALL
  SELECT
    'CMP3' AS campaign_id,
    59 AS flight_days,
    'ended' AS campaign_state,
    '25-54' AS target_age_range,
    CAST(NULL AS DECIMAL(18, 2)) AS budget_usd,
    CAST(NULL AS DECIMAL(18, 2)) AS spend_usd,
    CAST(NULL AS DECIMAL(12, 4)) AS return_on_ad_spend
),

__assert__campaign_id_is_unique_and_present AS (
  SELECT t.campaign_id
  FROM __ref("dim_campaigns") AS t
  GROUP BY
    t.campaign_id
  HAVING
    COUNT(*) > 1
    OR t.campaign_id IS NULL
)
