TEST (name "int_ticket_threads__summarises_authors_and_handoffs");

WITH __ref__stg_ticket_comments AS (
  SELECT
    'c1' AS comment_id,
    'T1' AS ticket_id,
    'customer' AS author_type,
    'C1' AS author_id,
    TRUE AS is_public,
    '2026-03-10 10:00:00 +00:00'::TIMESTAMP_TZ AS created_at,
    NULL AS body_word_count,
    TRUE AS contains_order_reference,
    1 AS attachment_count,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'c2',
    'T1',
    'agent',
    'A2',
    TRUE,
    '2026-03-10 10:05:00 +00:00'::TIMESTAMP_TZ,
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
    'A1',
    FALSE,
    '2026-03-10 10:10:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE,
    0,
    NULL,
    NULL
  UNION ALL
  SELECT
    'c4',
    'T1',
    'customer',
    'C1',
    TRUE,
    '2026-03-10 10:20:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE,
    2,
    NULL,
    NULL
  UNION ALL
  SELECT
    'c5',
    'T1',
    'system',
    NULL,
    TRUE,
    '2026-03-10 10:21:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    FALSE,
    0,
    NULL,
    NULL
),

__ref__stg_tickets AS (
  SELECT
    'T1' AS ticket_id,
    NULL AS customer_email,
    NULL AS channel,
    NULL AS priority,
    NULL AS ticket_status,
    NULL AS created_at,
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
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__int_ticket_threads AS (
  SELECT
    'T1' AS ticket_id,
    5 AS comment_count,
    4 AS public_comment_count,
    3 AS handoff_count,
    3 AS total_attachments,
    '2026-03-10 10:21:00 +00:00'::TIMESTAMP_TZ AS last_comment_at,
    'system' AS last_author_type,
    TRUE AS mentions_order
  UNION ALL
  SELECT
    'T2' AS ticket_id,
    0 AS comment_count,
    0 AS public_comment_count,
    0 AS handoff_count,
    0 AS total_attachments,
    CAST(NULL AS TIMESTAMP_TZ) AS last_comment_at,
    CAST(NULL AS VARCHAR) AS last_author_type,
    FALSE AS mentions_order
),

__assert__author_sequence_is_chronological AS (
  SELECT t.ticket_id
  FROM __ref("int_ticket_threads") AS t
  WHERE
    t.ticket_id = 'T1'
    AND ARRAY_TO_STRING(t.author_sequence, '>') <> 'customer>agent>agent>customer>system'
),

__assert__agent_participants_skip_non_agents AS (
  SELECT t.ticket_id
  FROM __ref("int_ticket_threads") AS t
  WHERE ARRAY_TO_STRING(t.agent_participants, ',') <> IFF(t.ticket_id = 'T1', 'A1,A2', '')
),

__assert__empty_thread_breakdown_holds_json_nulls AS (
  SELECT t.ticket_id
  FROM __ref("int_ticket_threads") AS t
  WHERE
    t.ticket_id = 'T2'
    AND NOT IS_NULL_VALUE(t.author_breakdown:agent)
)
