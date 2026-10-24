TEST (name "stg_campaigns__keeps_latest_live_version");

WITH __source__growth__campaigns AS (
  SELECT
    'K1' AS campaign_id,
    NULL AS campaign_name,
    NULL AS channel,
    NULL AS objective,
    NULL AS starts_on,
    NULL AS ends_on,
    NULL AS budget_minor,
    NULL AS currency_code,
    NULL AS targeting,
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
    NULL,
    NULL,
    NULL,
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_campaigns AS (
  SELECT
    'K1' AS campaign_id,
    2 AS source_seq
)
