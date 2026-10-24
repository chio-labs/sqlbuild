TEST (name "stg_settlement_reports__keeps_only_parseable_object_reports");

WITH __source__finance__settlement_reports AS (
  SELECT
    'R1' AS report_id,
    'payco' AS provider_code,
    '2026-03-10'::DATE AS report_date,
    '{}' AS report_body,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'R1',
    'payco',
    '2026-03-10'::DATE,
    '{"summary": {"currency": "eur", "gross_minor": 9700, "fees_minor": 300}, "lines": [{}, {}]}',
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'R2',
    'payco',
    '2026-03-10'::DATE,
    'not json',
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'R3',
    'payco',
    '2026-03-10'::DATE,
    '[1, 2]',
    '2026-03-10 11:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'R4',
    'payco',
    '2026-03-11'::DATE,
    '{"summary": {}}',
    '2026-03-11 11:00:00'::TIMESTAMP_NTZ
),

__expected__stg_settlement_reports AS (
  SELECT
    'R1' AS report_id,
    'PAYCO' AS provider_code,
    'EUR' AS currency_code,
    9700 AS gross_minor,
    300 AS fees_minor,
    2 AS line_count
  UNION ALL
  SELECT
    'R4' AS report_id,
    'PAYCO' AS provider_code,
    CAST(NULL AS VARCHAR) AS currency_code,
    CAST(NULL AS INT) AS gross_minor,
    CAST(NULL AS INT) AS fees_minor,
    CAST(NULL AS INT) AS line_count
)
