TEST (name "stg_ticket_comments__keeps_latest_live_version");

WITH __source__support__ticket_comments AS (
  SELECT
    'K1' AS comment_id,
    NULL AS ticket_id,
    NULL AS author_type,
    NULL AS author_id,
    NULL AS body,
    NULL AS is_public,
    NULL AS created_at,
    NULL AS attachments,
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
    'D',
    4,
    '2026-01-03 10:00:00'::TIMESTAMP_NTZ
),

__expected__stg_ticket_comments AS (
  SELECT
    'K1' AS comment_id,
    2 AS source_seq
)
