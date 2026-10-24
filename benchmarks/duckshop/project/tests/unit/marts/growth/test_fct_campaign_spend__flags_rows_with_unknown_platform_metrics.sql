TEST (name "fct_campaign_spend__flags_rows_with_unknown_platform_metrics");

WITH __ref__int_campaign_spend_usd AS (
  SELECT
    'SP1' AS spend_id,
    'CMP1' AS campaign_id,
    NULL AS campaign_name,
    'social' AS channel,
    NULL AS platform_account_id,
    '2026-03-01'::DATE AS spend_date,
    NULL AS currency_code,
    NULL AS spend_amount,
    100.0::DECIMAL(18, 2) AS spend_usd,
    NULL AS impressions,
    NULL AS clicks,
    NULL AS conversions,
    NULL AS click_through_rate,
    NULL AS cost_per_click_usd,
    NULL AS metric_count,
    PARSE_JSON('[]')::ARRAY AS unknown_metrics,
    NULL AS is_in_flight
  UNION ALL
  SELECT
    'SP2',
    'CMP1',
    NULL,
    'social',
    NULL,
    '2026-03-02'::DATE,
    NULL,
    NULL,
    80.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    PARSE_JSON('["saves"]')::ARRAY,
    NULL
  UNION ALL
  SELECT
    'SP3',
    'CMP2',
    NULL,
    'email',
    NULL,
    '2026-03-02'::DATE,
    NULL,
    NULL,
    0.0::DECIMAL(18, 2),
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__fct_campaign_spend AS (
  SELECT
    'SP1' AS spend_id,
    100.0::NUMBER(18, 2) AS spend_usd,
    FALSE AS has_unknown_metrics
  UNION ALL
  SELECT
    'SP2' AS spend_id,
    80.0::NUMBER(18, 2) AS spend_usd,
    TRUE AS has_unknown_metrics
  UNION ALL
  SELECT
    'SP3' AS spend_id,
    0.0::NUMBER(18, 2) AS spend_usd,
    CAST(NULL AS BOOLEAN) AS has_unknown_metrics
),

__assert__spend_id_is_unique_and_present AS (
  SELECT t.spend_id
  FROM __ref("fct_campaign_spend") AS t
  GROUP BY
    t.spend_id
  HAVING
    COUNT(*) > 1
    OR t.spend_id IS NULL
)
