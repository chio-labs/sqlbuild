TEST (name "stg_campaign_spend__unpivots_metrics_and_parses_formatted_numbers");

WITH __source__growth__campaign_spend AS (
  SELECT
    'SP1' AS spend_id,
    '2026-03-10'::DATE AS spend_date,
    'social' AS channel,
    'CMP1' AS campaign_id,
    'usd' AS currency_code,
    OBJECT_CONSTRUCT(
      'account',
      OBJECT_CONSTRUCT('id', 'ACC1'),
      'metrics',
      ARRAY_CONSTRUCT(
        OBJECT_CONSTRUCT(
          'name',
          'spend',
          'value',
          '1,234.50'
        ),
        OBJECT_CONSTRUCT('name', 'linkClicks', 'value', 20),
        OBJECT_CONSTRUCT('name', 'impressions', 'value', 1000)
      )
    )::VARIANT AS report,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'SP2',
    '2026-03-10'::DATE,
    'social',
    'CMP1',
    'usd',
    OBJECT_CONSTRUCT(
      'account',
      OBJECT_CONSTRUCT('id', 'ACC1'),
      'metrics',
      ARRAY_CONSTRUCT(
        OBJECT_CONSTRUCT(
          'name',
          'spend',
          'value',
          '1,234.50'
        ),
        OBJECT_CONSTRUCT('name', 'linkClicks', 'value', 20),
        OBJECT_CONSTRUCT('name', 'impressions', 'value', 1000)
      )
    )::VARIANT,
    'I',
    2,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'SP2',
    '2026-03-10'::DATE,
    'social',
    'CMP1',
    'usd',
    OBJECT_CONSTRUCT(
      'account',
      OBJECT_CONSTRUCT('id', 'ACC1'),
      'metrics',
      ARRAY_CONSTRUCT(
        OBJECT_CONSTRUCT(
          'name',
          'spend',
          'value',
          '1,234.50'
        ),
        OBJECT_CONSTRUCT('name', 'linkClicks', 'value', 20),
        OBJECT_CONSTRUCT('name', 'impressions', 'value', 1000)
      )
    )::VARIANT,
    'D',
    3,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_campaign_spend AS (
  SELECT
    'SP1:spend' AS spend_metric_key,
    'SOCIAL' AS channel,
    'USD' AS currency_code,
    'spend' AS metric_name,
    1234.5::DECIMAL(38, 6) AS metric_value,
    'ACC1' AS platform_account_id
  UNION ALL
  SELECT
    'SP1:linkclicks' AS spend_metric_key,
    'SOCIAL' AS channel,
    'USD' AS currency_code,
    'link_clicks' AS metric_name,
    20.0::DECIMAL(38, 6) AS metric_value,
    'ACC1' AS platform_account_id
  UNION ALL
  SELECT
    'SP1:impressions' AS spend_metric_key,
    'SOCIAL' AS channel,
    'USD' AS currency_code,
    'impressions' AS metric_name,
    1000.0::DECIMAL(38, 6) AS metric_value,
    'ACC1' AS platform_account_id
)
