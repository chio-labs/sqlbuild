TEST (name "stg_survey_responses__keeps_latest_live_version");

WITH __source__growth__survey_responses AS (
  SELECT
    'K1' AS response_id,
    NULL AS survey_code,
    NULL AS customer_id,
    NULL AS submitted_at,
    NULL AS answers,
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
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_survey_responses AS (
  SELECT
    'K1' AS response_id,
    2 AS source_seq
)
