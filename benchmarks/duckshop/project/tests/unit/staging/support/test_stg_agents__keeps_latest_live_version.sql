TEST (name "stg_agents__keeps_latest_live_version");

WITH __source__support__agents AS (
  SELECT
    'K1' AS agent_id,
    NULL AS display_name,
    NULL AS email,
    NULL AS team_code,
    NULL AS iana_timezone,
    NULL AS hired_on,
    NULL AS skills,
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
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_agents AS (
  SELECT
    'K1' AS agent_id,
    2 AS source_seq
)
