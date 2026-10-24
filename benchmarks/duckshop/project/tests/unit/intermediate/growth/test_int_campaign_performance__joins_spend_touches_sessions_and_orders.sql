TEST (name "int_campaign_performance__joins_spend_touches_sessions_and_orders");

WITH __ref__stg_campaigns AS (
  SELECT
    'CMP1' AS campaign_id,
    'Spring' AS campaign_name,
    'paid_social' AS channel,
    'sales' AS objective,
    '2026-03-01'::DATE AS starts_on,
    NULL AS ends_on,
    100000 AS budget_minor,
    'EUR' AS currency_code,
    PARSE_JSON('["EU", "LATAM", "US"]')::ARRAY AS target_regions,
    NULL AS target_age_min,
    NULL AS target_age_max,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'CMP2',
    'Mail',
    'email',
    'retention',
    '2026-03-01'::DATE,
    NULL,
    50000,
    'USD',
    PARSE_JSON('[]')::ARRAY,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_campaign_spend_usd AS (
  SELECT
    'SP1' AS spend_id,
    'CMP1' AS campaign_id,
    NULL AS campaign_name,
    NULL AS channel,
    NULL AS platform_account_id,
    NULL AS spend_date,
    NULL AS currency_code,
    NULL AS spend_amount,
    300.0::DECIMAL(18, 2) AS spend_usd,
    NULL AS impressions,
    40 AS clicks,
    NULL AS conversions,
    NULL AS click_through_rate,
    NULL AS cost_per_click_usd,
    NULL AS metric_count,
    NULL AS unknown_metrics,
    NULL AS is_in_flight
  UNION ALL
  SELECT
    'SP2',
    'CMP1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    250.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_email_engagement AS (
  SELECT
    'M1' AS message_id,
    'CMP2' AS campaign_id,
    NULL AS recipient_email,
    NULL AS sent_at,
    NULL AS is_delivered,
    NULL AS bounce_type,
    NULL AS human_open_count,
    3 AS click_count,
    NULL AS clicked_domains,
    NULL AS unsubscribed,
    NULL AS complained,
    NULL AS minutes_to_first_click,
    NULL AS customer_id,
    NULL AS campaign_channel,
    NULL AS is_campaign_in_flight
  UNION ALL
  SELECT
    'M2',
    'CMP2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    0,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'M3',
    'CMP1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    2,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_session_attribution AS (
  SELECT
    'S1' AS session_id,
    NULL AS anonymous_id,
    NULL AS customer_id,
    NULL AS session_start_utc,
    NULL AS utm_source,
    NULL AS utm_medium,
    'cmp1' AS utm_campaign,
    NULL AS channel_code,
    NULL AS is_paid,
    NULL AS first_touch_channel,
    NULL AS last_touch_channel,
    NULL AS touch_number
  UNION ALL
  SELECT
    'S2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'cmp1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'S3',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'other',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_orders_usd AS (
  SELECT
    'O1' AS order_id,
    NULL AS customer_id,
    NULL AS region_code,
    NULL AS currency_code,
    NULL AS placed_at,
    NULL AS placed_date_local,
    'DELIVERED' AS order_status,
    NULL AS sales_channel,
    NULL AS units,
    NULL AS amount,
    100.0::DECIMAL(18, 2) AS amount_usd,
    NULL AS gross_amount_usd,
    NULL AS discount_amount_usd,
    NULL AS tax_amount_usd,
    NULL AS rate_to_usd,
    NULL AS rate_date,
    NULL AS rate_age_days,
    NULL AS is_rate_stale,
    NULL AS promo_code,
    NULL AS utm_source,
    NULL AS utm_medium,
    'cmp1' AS utm_campaign,
    NULL AS basket_size
  UNION ALL
  SELECT
    'O2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'CANCELLED',
    NULL,
    NULL,
    NULL,
    50.0::DECIMAL(18, 2),
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
    'cmp1',
    NULL
  UNION ALL
  SELECT
    'O3',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'PENDING',
    NULL,
    NULL,
    NULL,
    70.0::DECIMAL(18, 2),
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
    'cmp2',
    NULL
  UNION ALL
  SELECT
    'O4',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'SHIPPED',
    NULL,
    NULL,
    NULL,
    40.0::DECIMAL(18, 2),
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
    'cmp2',
    NULL
),

__ref__stg_fx_rates AS (
  SELECT
    'EUR' AS currency_code,
    '2026-02-28'::DATE AS rate_date,
    1.1::NUMBER(18, 8) AS rate_to_usd,
    NULL AS usd_to_rate,
    NULL AS next_rate_date
  UNION ALL
  SELECT
    'USD',
    '2026-02-01'::DATE,
    1.0::NUMBER(18, 8),
    NULL,
    NULL
),

__seed__currencies AS (
  SELECT
    'EUR' AS currency_code,
    NULL AS currency_name,
    2 AS minor_unit_exponent,
    NULL AS symbol
  UNION ALL
  SELECT
    'USD',
    NULL,
    2,
    NULL
),

__expected__int_campaign_performance AS (
  SELECT
    'CMP1' AS campaign_id,
    1100.0::DECIMAL(18, 2) AS budget_usd,
    550.0::DECIMAL(18, 2) AS spend_usd,
    50.0::DECIMAL(9, 2) AS budget_used_pct,
    40 AS paid_clicks,
    2 AS email_clicks,
    2 AS attributed_sessions,
    1 AS attributed_orders,
    100.0::DECIMAL(18, 2) AS attributed_revenue_usd,
    0.1818::DECIMAL(12, 4) AS return_on_ad_spend,
    3 AS target_region_count,
    1 AS spend_rank_in_channel
  UNION ALL
  SELECT
    'CMP2' AS campaign_id,
    500.0::DECIMAL(18, 2) AS budget_usd,
    0.0::DECIMAL(18, 2) AS spend_usd,
    0.0::DECIMAL(9, 2) AS budget_used_pct,
    0 AS paid_clicks,
    3 AS email_clicks,
    0 AS attributed_sessions,
    1 AS attributed_orders,
    40.0::DECIMAL(18, 2) AS attributed_revenue_usd,
    CAST(NULL AS DECIMAL(12, 4)) AS return_on_ad_spend,
    0 AS target_region_count,
    1 AS spend_rank_in_channel
),

__assert__unsupported_regions_are_listed AS (
  SELECT c.campaign_id
  FROM __ref("int_campaign_performance") AS c
  WHERE
    ARRAY_TO_STRING(c.unsupported_target_regions, ',') <> IFF(c.campaign_id = 'CMP1', 'LATAM', '')
)
