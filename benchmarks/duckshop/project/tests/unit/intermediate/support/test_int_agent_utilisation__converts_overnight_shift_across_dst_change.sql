TEST (name "int_agent_utilisation__converts_overnight_shift_across_dst_change");

WITH __ref__stg_agent_shifts AS (
  SELECT
    'SH1' AS shift_id,
    'A1' AS agent_id,
    '2026-03-07 22:00:00'::TIMESTAMP_NTZ AS shift_start_local,
    '2026-03-08 06:00:00'::TIMESTAMP_NTZ AS shift_end_local,
    'America/New_York' AS iana_timezone,
    480 AS scheduled_minutes,
    30 AS break_minutes,
    NULL AS breaks,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'SH2',
    'A2',
    '2026-03-09 09:00:00'::TIMESTAMP_NTZ,
    '2026-03-09 17:00:00'::TIMESTAMP_NTZ,
    'Europe/London',
    480,
    60,
    NULL,
    NULL,
    NULL
),

__ref__stg_agents AS (
  SELECT
    'A1' AS agent_id,
    NULL AS display_name,
    NULL AS email,
    'NIGHT' AS team_code,
    NULL AS iana_timezone,
    NULL AS hired_on,
    NULL AS skills,
    NULL AS speaks_german,
    NULL AS source_seq,
    NULL AS source_loaded_at
),

__ref__stg_call_records AS (
  SELECT
    'C1' AS call_id,
    NULL AS ticket_id,
    'A1' AS agent_id,
    NULL AS caller_phone,
    NULL AS caller_country_prefix,
    '2026-03-08 04:00:00 +00:00'::TIMESTAMP_TZ AS started_at,
    600 AS duration_seconds,
    NULL AS ivr_path,
    NULL AS ivr_depth,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'C2',
    NULL,
    'A1',
    NULL,
    NULL,
    '2026-03-08 09:30:00 +00:00'::TIMESTAMP_TZ,
    300,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'C3',
    NULL,
    'A1',
    NULL,
    NULL,
    '2026-03-08 11:00:00 +00:00'::TIMESTAMP_TZ,
    900,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_ticket_first_response AS (
  SELECT
    'T1' AS ticket_id,
    NULL AS created_at_utc,
    '2026-03-08 05:00:00'::TIMESTAMPNTZ AS first_response_at_utc,
    'A1' AS first_responder_id,
    NULL AS minutes_to_first_response,
    NULL AS first_customer_reply_at_utc,
    NULL AS agent_responses_before_customer_reply,
    NULL AS has_auto_reply
  UNION ALL
  SELECT
    'T2',
    NULL,
    '2026-03-08 10:00:00'::TIMESTAMPNTZ,
    'A1',
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__int_agent_utilisation AS (
  SELECT
    'SH1' AS shift_id,
    'NIGHT' AS team_code,
    '2026-03-08 03:00:00'::TIMESTAMPNTZ AS shift_start_utc,
    '2026-03-08 10:00:00'::TIMESTAMPNTZ AS shift_end_utc,
    450 AS productive_minutes,
    15.0::DECIMAL(10, 2) AS call_minutes,
    2 AS calls_handled,
    1 AS tickets_first_responded,
    0.0467::DECIMAL(9, 4) AS utilisation,
    TRUE AS is_overnight
  UNION ALL
  SELECT
    'SH2' AS shift_id,
    CAST(NULL AS VARCHAR) AS team_code,
    '2026-03-09 09:00:00'::TIMESTAMPNTZ AS shift_start_utc,
    '2026-03-09 17:00:00'::TIMESTAMPNTZ AS shift_end_utc,
    420 AS productive_minutes,
    0.0::DECIMAL(10, 2) AS call_minutes,
    0 AS calls_handled,
    0 AS tickets_first_responded,
    0.0::DECIMAL(9, 4) AS utilisation,
    FALSE AS is_overnight
)
