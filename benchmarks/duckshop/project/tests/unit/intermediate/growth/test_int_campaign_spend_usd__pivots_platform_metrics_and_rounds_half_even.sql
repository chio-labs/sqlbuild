TEST (name "int_campaign_spend_usd__pivots_platform_metrics_and_rounds_half_even");

WITH __ref__stg_campaign_spend AS (
  SELECT
    'SP1:spend' AS spend_metric_key,
    'SP1' AS spend_id,
    '2026-03-10'::DATE AS spend_date,
    NULL AS channel,
    'CMP1' AS campaign_id,
    'USD' AS currency_code,
    'spend' AS metric_name,
    10.125::DECIMAL(38, 6) AS metric_value,
    'ACC1' AS platform_account_id
  UNION ALL
  SELECT
    'SP1:impressions',
    'SP1',
    '2026-03-10'::DATE,
    NULL,
    'CMP1',
    'USD',
    'impressions',
    1000::DECIMAL(38, 6),
    'ACC1'
  UNION ALL
  SELECT
    'SP1:link_clicks',
    'SP1',
    '2026-03-10'::DATE,
    NULL,
    'CMP1',
    'USD',
    'link_clicks',
    20::DECIMAL(38, 6),
    'ACC1'
  UNION ALL
  SELECT
    'SP1:purchases_7d',
    'SP1',
    '2026-03-10'::DATE,
    NULL,
    'CMP1',
    'USD',
    'purchases_7d',
    2::DECIMAL(38, 6),
    'ACC1'
  UNION ALL
  SELECT
    'SP1:video_views',
    'SP1',
    '2026-03-10'::DATE,
    NULL,
    'CMP1',
    'USD',
    'video_views',
    500::DECIMAL(38, 6),
    'ACC1'
  UNION ALL
  SELECT
    'SP2:spend',
    'SP2',
    '2026-02-10'::DATE,
    'search',
    'CMP9',
    'GBP',
    'spend',
    7.5::DECIMAL(38, 6),
    'ACC1'
  UNION ALL
  SELECT
    'SP2:impressions',
    'SP2',
    '2026-02-10'::DATE,
    'search',
    'CMP9',
    'GBP',
    'impressions',
    0::DECIMAL(38, 6),
    'ACC1'
),

__ref__stg_campaigns AS (
  SELECT
    'CMP1' AS campaign_id,
    'Spring' AS campaign_name,
    'paid_social' AS channel,
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
),

__ref__stg_fx_rates AS (
  SELECT
    'USD' AS currency_code,
    '2026-01-01'::DATE AS rate_date,
    1.0::NUMBER(18, 8) AS rate_to_usd,
    NULL AS usd_to_rate,
    NULL AS next_rate_date
  UNION ALL
  SELECT
    'GBP',
    '2026-02-01'::DATE,
    1.26::NUMBER(18, 8),
    NULL,
    NULL
),

__expected__int_campaign_spend_usd AS (
  SELECT
    'SP1' AS spend_id,
    'Spring' AS campaign_name,
    'paid_social' AS channel,
    10.125::DECIMAL(38, 6) AS spend_amount,
    10.12::DECIMAL(18, 2) AS spend_usd,
    1000 AS impressions,
    20 AS clicks,
    2 AS conversions,
    0.02::DECIMAL(9, 6) AS click_through_rate,
    0.5063::DECIMAL(18, 4) AS cost_per_click_usd,
    5 AS metric_count,
    TRUE AS is_in_flight
  UNION ALL
  SELECT
    'SP2' AS spend_id,
    CAST(NULL AS VARCHAR) AS campaign_name,
    'search' AS channel,
    7.5::DECIMAL(38, 6) AS spend_amount,
    9.45::DECIMAL(18, 2) AS spend_usd,
    0 AS impressions,
    CAST(NULL AS INT) AS clicks,
    CAST(NULL AS INT) AS conversions,
    CAST(NULL AS DECIMAL(9, 6)) AS click_through_rate,
    CAST(NULL AS DECIMAL(18, 4)) AS cost_per_click_usd,
    2 AS metric_count,
    FALSE AS is_in_flight
),

__assert__unknown_metrics_are_listed AS (
  SELECT s.spend_id
  FROM __ref("int_campaign_spend_usd") AS s
  WHERE ARRAY_TO_STRING(s.unknown_metrics, ',') <> IFF(s.spend_id = 'SP1', 'video_views', '')
)
