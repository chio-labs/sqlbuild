TEST (name "int_ticket_first_response__finds_first_public_agent_reply_and_burst");

WITH __ref__stg_tickets AS (
  SELECT
    'T1' AS ticket_id,
    NULL AS customer_email,
    NULL AS channel,
    NULL AS priority,
    NULL AS ticket_status,
    '2026-03-10 10:00:00 +01:00'::TIMESTAMP_LTZ AS created_at,
    NULL AS solved_at,
    NULL AS order_id,
    NULL AS contact_reason,
    NULL AS tag_list,
    NULL AS is_vip,
    NULL AS custom_fields,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'T2',
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_LTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T3',
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-03-11 08:00:00 +00:00'::TIMESTAMP_LTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__stg_ticket_comments AS (
  SELECT
    'c1' AS comment_id,
    'T1' AS ticket_id,
    'system' AS author_type,
    NULL AS author_id,
    TRUE AS is_public,
    '2026-03-10 09:00:30 +00:00'::TIMESTAMP_TZ AS created_at,
    NULL AS body_word_count,
    FALSE AS contains_order_reference,
    0 AS attachment_count,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'c2',
    'T1',
    'agent',
    'A1',
    FALSE,
    '2026-03-10 09:10:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE,
    0,
    NULL,
    NULL
  UNION ALL
  SELECT
    'c3',
    'T1',
    'agent',
    'A2',
    TRUE,
    '2026-03-10 09:20:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE,
    0,
    NULL,
    NULL
  UNION ALL
  SELECT
    'c4',
    'T1',
    'agent',
    'A2',
    TRUE,
    '2026-03-10 09:25:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE,
    0,
    NULL,
    NULL
  UNION ALL
  SELECT
    'c5',
    'T1',
    'customer',
    'C1',
    TRUE,
    '2026-03-10 09:40:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE,
    0,
    NULL,
    NULL
  UNION ALL
  SELECT
    'c6',
    'T1',
    'agent',
    'A1',
    TRUE,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE,
    0,
    NULL,
    NULL
  UNION ALL
  SELECT
    'c7',
    'T3',
    'customer',
    'C2',
    TRUE,
    '2026-03-11 08:05:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE,
    0,
    NULL,
    NULL
  UNION ALL
  SELECT
    'c8',
    'T3',
    'agent',
    'A3',
    TRUE,
    '2026-03-11 08:30:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE,
    0,
    NULL,
    NULL
),

__expected__int_ticket_first_response AS (
  SELECT
    'T1' AS ticket_id,
    '2026-03-10 09:00:00'::TIMESTAMPNTZ AS created_at_utc,
    '2026-03-10 09:20:00'::TIMESTAMPNTZ AS first_response_at_utc,
    'A1' AS first_responder_id,
    20 AS minutes_to_first_response,
    '2026-03-10 09:40:00'::TIMESTAMPNTZ AS first_customer_reply_at_utc,
    3 AS agent_responses_before_customer_reply,
    TRUE AS has_auto_reply
  UNION ALL
  SELECT
    'T2' AS ticket_id,
    '2026-03-10 10:00:00'::TIMESTAMPNTZ AS created_at_utc,
    CAST(NULL AS TIMESTAMPNTZ) AS first_response_at_utc,
    CAST(NULL AS VARCHAR) AS first_responder_id,
    CAST(NULL AS INT) AS minutes_to_first_response,
    CAST(NULL AS TIMESTAMPNTZ) AS first_customer_reply_at_utc,
    0 AS agent_responses_before_customer_reply,
    FALSE AS has_auto_reply
  UNION ALL
  SELECT
    'T3' AS ticket_id,
    '2026-03-11 08:00:00'::TIMESTAMPNTZ AS created_at_utc,
    '2026-03-11 08:30:00'::TIMESTAMPNTZ AS first_response_at_utc,
    'A3' AS first_responder_id,
    30 AS minutes_to_first_response,
    CAST(NULL AS TIMESTAMPNTZ) AS first_customer_reply_at_utc,
    1 AS agent_responses_before_customer_reply,
    FALSE AS has_auto_reply
)
