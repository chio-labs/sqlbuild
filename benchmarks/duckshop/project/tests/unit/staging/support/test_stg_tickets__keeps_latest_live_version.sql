TEST (name "stg_tickets__keeps_latest_live_version");

WITH __source__support__tickets AS (
  SELECT
    'K1' AS ticket_id,
    NULL AS customer_email,
    NULL AS channel,
    NULL AS priority,
    NULL AS ticket_status,
    NULL AS created_at,
    NULL AS solved_at,
    NULL AS custom_fields,
    NULL AS tags,
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

__expected__stg_tickets AS (
  SELECT
    'K1' AS ticket_id,
    2 AS source_seq
)
