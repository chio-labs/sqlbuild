TEST (name "rpt_campaign_roas_monthly__matches_lowercase_utm_campaigns_to_channel_spend");

WITH __ref__fct_campaign_spend AS (
  SELECT
    'SP1' AS spend_id,
    'CMP1' AS campaign_id,
    'social' AS channel,
    '2026-03-01'::DATE AS spend_date,
    NULL AS currency_code,
    100.0::NUMBER(18, 2) AS spend_usd,
    NULL AS impressions,
    50 AS clicks,
    NULL AS conversions,
    NULL AS cost_per_click_usd,
    NULL AS is_in_flight,
    NULL AS has_unknown_metrics
  UNION ALL
  SELECT
    'SP2',
    'CMP1',
    'social',
    '2026-03-20'::DATE,
    NULL,
    50.0::NUMBER(18, 2),
    NULL,
    10,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'SP3',
    'CMP2',
    'email',
    '2026-03-05'::DATE,
    NULL,
    0.0::NUMBER(18, 2),
    NULL,
    5,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'SP4',
    'CMP1',
    'social',
    '2026-04-01'::DATE,
    NULL,
    20.0::NUMBER(18, 2),
    NULL,
    1,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__fct_orders AS (
  SELECT
    'O1' AS order_id,
    NULL AS customer_id,
    NULL AS region_code,
    NULL AS placed_at,
    '2026-03-10'::DATE AS placed_date_local,
    NULL AS order_status,
    NULL AS sales_channel,
    NULL AS units,
    NULL AS currency_code,
    NULL AS amount,
    300.0::NUMBER(18, 2) AS amount_usd,
    NULL AS rate_to_usd,
    NULL AS rate_date,
    NULL AS gross_amount_usd,
    NULL AS discount_amount_usd,
    NULL AS tax_amount_usd,
    NULL AS promo_code,
    NULL AS utm_source,
    NULL AS utm_medium,
    'cmp1' AS utm_campaign,
    NULL AS basket_size,
    NULL AS order_number,
    NULL AS is_first_order,
    NULL AS first_paid_at,
    NULL AS first_delivered_at,
    NULL AS hours_paid_to_shipped,
    NULL AS captured_minor,
    NULL AS refunded_minor,
    NULL AS net_collected_minor,
    NULL AS is_fully_refunded
  UNION ALL
  SELECT
    'O2',
    NULL,
    NULL,
    NULL,
    '2026-04-02'::DATE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    10.0::NUMBER(18, 2),
    NULL,
    NULL,
    NULL,
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
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'O3',
    NULL,
    NULL,
    NULL,
    '2026-03-11'::DATE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    99.0::NUMBER(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'CMP1',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'O4',
    NULL,
    NULL,
    NULL,
    '2026-03-12'::DATE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    40.0::NUMBER(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'cmp2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__dim_campaigns AS (
  SELECT
    'CMP1' AS campaign_id,
    'Spring Splash' AS campaign_name,
    'social' AS channel,
    NULL AS objective,
    NULL AS starts_on,
    NULL AS ends_on,
    NULL AS flight_days,
    NULL AS campaign_state,
    NULL AS target_age_range,
    NULL AS target_regions,
    NULL AS budget_usd,
    NULL AS spend_usd,
    NULL AS return_on_ad_spend,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'CMP2',
    'Pond Week',
    'email',
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
    NULL
),

__expected__rpt_campaign_roas_monthly AS (
  SELECT
    '2026-03:social' AS roas_key,
    150.0::DECIMAL(18, 2) AS spend_usd,
    60 AS clicks,
    1 AS attributed_orders,
    300.0::DECIMAL(18, 2) AS attributed_revenue_usd,
    2.0::DECIMAL(12, 4) AS return_on_ad_spend
  UNION ALL
  SELECT
    '2026-03:email' AS roas_key,
    0.0::DECIMAL(18, 2) AS spend_usd,
    5 AS clicks,
    1 AS attributed_orders,
    40.0::DECIMAL(18, 2) AS attributed_revenue_usd,
    CAST(NULL AS DECIMAL(12, 4)) AS return_on_ad_spend
  UNION ALL
  SELECT
    '2026-04:social' AS roas_key,
    20.0::DECIMAL(18, 2) AS spend_usd,
    1 AS clicks,
    1 AS attributed_orders,
    10.0::DECIMAL(18, 2) AS attributed_revenue_usd,
    0.5::DECIMAL(12, 4) AS return_on_ad_spend
),

__assert__roas_key_is_unique_and_present AS (
  SELECT t.roas_key
  FROM __ref("rpt_campaign_roas_monthly") AS t
  GROUP BY
    t.roas_key
  HAVING
    COUNT(*) > 1
    OR t.roas_key IS NULL
)
