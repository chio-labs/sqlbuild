TEST (name "stg_agent_shifts__totals_breaks_and_scheduled_minutes");

WITH __source__support__agent_shifts AS (
  SELECT
    'SH1' AS shift_id,
    'A1' AS agent_id,
    '2026-03-10 22:00:00'::TIMESTAMP_NTZ AS shift_start_local,
    '2026-03-11 05:00:00'::TIMESTAMP_NTZ AS shift_end_local,
    'Europe/Berlin' AS iana_timezone,
    NULL AS breaks,
    'I' AS _op,
    1 AS _seq,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ AS _loaded_at
  UNION ALL
  SELECT
    'SH1',
    'A1',
    '2026-03-10 22:00:00'::TIMESTAMP_NTZ,
    '2026-03-11 06:00:00'::TIMESTAMP_NTZ,
    'Europe/Berlin',
    PARSE_JSON('[{"minutes": 30}, {"minutes": 15}, {"type": "handover"}]')::VARIANT,
    'U',
    2,
    '2026-01-02 10:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'SH2',
    'A2',
    '2026-03-11 09:00:00'::TIMESTAMP_NTZ,
    '2026-03-11 13:00:00'::TIMESTAMP_NTZ,
    'Europe/London',
    NULL,
    'I',
    3,
    '2026-01-01 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_agent_shifts AS (
  SELECT
    'SH1' AS shift_id,
    480 AS scheduled_minutes,
    45 AS break_minutes,
    2 AS source_seq
  UNION ALL
  SELECT
    'SH2' AS shift_id,
    240 AS scheduled_minutes,
    0 AS break_minutes,
    3 AS source_seq
)
