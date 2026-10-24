TEST (name "fct_support_tickets__joins_ticket_measures_and_keeps_the_most_negative_chat");

WITH __ref__stg_tickets AS (
  SELECT
    'T1' AS ticket_id,
    NULL AS customer_email,
    'email' AS channel,
    NULL AS priority,
    'solved' AS ticket_status,
    NULL AS created_at,
    NULL AS solved_at,
    NULL AS order_id,
    'damaged_item' AS contact_reason,
    NULL AS tag_list,
    NULL AS is_vip,
    NULL AS custom_fields,
    NULL AS source_seq,
    '2026-03-10 10:00:00'::TIMESTAMP_NTZ AS source_loaded_at
  UNION ALL
  SELECT
    'T2',
    NULL,
    'chat',
    NULL,
    'open',
    NULL,
    NULL,
    NULL,
    'where_is_my_order',
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-03-10 12:00:00'::TIMESTAMP_NTZ
  UNION ALL
  SELECT
    'T3',
    NULL,
    'phone',
    NULL,
    'new',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    '2026-03-11 09:00:00'::TIMESTAMP_NTZ
),

__ref__int_ticket_first_response AS (
  SELECT
    'T1' AS ticket_id,
    '2026-03-10 09:00:00'::TIMESTAMPNTZ AS created_at_utc,
    NULL AS first_response_at_utc,
    NULL AS first_responder_id,
    30 AS minutes_to_first_response,
    NULL AS first_customer_reply_at_utc,
    NULL AS agent_responses_before_customer_reply,
    NULL AS has_auto_reply
),

__ref__int_ticket_business_hours AS (
  SELECT
    'T1' AS ticket_id,
    NULL AS created_at_support_local,
    NULL AS first_response_at_support_local,
    NULL AS calendar_minutes_to_response,
    20 AS business_minutes_to_response,
    NULL AS created_outside_hours
),

__ref__int_ticket_sla_breaches AS (
  SELECT
    'T1' AS ticket_id,
    2 AS priority,
    NULL AS channel,
    NULL AS policy_id,
    NULL AS first_response_target_minutes,
    NULL AS first_response_minutes_used,
    TRUE AS is_first_response_breached,
    NULL AS resolution_target_minutes,
    NULL AS resolution_minutes_used,
    FALSE AS is_resolution_breached,
    NULL AS breach_count,
    NULL AS open_minutes_now
),

__ref__int_ticket_threads AS (
  SELECT
    'T1' AS ticket_id,
    4 AS comment_count,
    NULL AS public_comment_count,
    NULL AS agent_participants,
    NULL AS author_sequence,
    1 AS handoff_count,
    NULL AS author_breakdown,
    NULL AS total_attachments,
    NULL AS last_comment_at,
    NULL AS last_author_type,
    NULL AS mentions_order
),

__ref__int_chat_sentiment AS (
  SELECT
    'CH1' AS chat_id,
    'T1' AS ticket_id,
    NULL AS customer_message_count,
    NULL AS agent_message_count,
    2 AS sentiment_score,
    'positive' AS sentiment_label,
    NULL AS median_agent_reply_seconds,
    NULL AS ends_with_thanks,
    NULL AS chat_minutes
  UNION ALL
  SELECT
    'CH2',
    'T1',
    NULL,
    NULL,
    -1,
    'negative',
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'CH3',
    NULL,
    NULL,
    NULL,
    -5,
    'negative',
    NULL,
    NULL,
    NULL
),

__ref__int_customer_support_history AS (
  SELECT
    'T1' AS ticket_id,
    'C1' AS customer_id,
    2 AS ticket_number_for_customer,
    NULL AS days_since_previous_ticket,
    4 AS csat_score,
    NULL AS rolling_csat_avg,
    TRUE AS is_repeat_contact_7d,
    NULL AS contact_reason
  UNION ALL
  SELECT
    'T2',
    'C2',
    1,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__fct_support_tickets AS (
  SELECT
    'T1' AS ticket_id,
    'C1' AS customer_id,
    2 AS priority,
    30 AS minutes_to_first_response,
    20 AS business_minutes_to_response,
    TRUE AS is_first_response_breached,
    FALSE AS is_resolution_breached,
    4 AS comment_count,
    1 AS handoff_count,
    'negative' AS sentiment_label,
    2 AS ticket_number_for_customer,
    TRUE AS is_repeat_contact_7d,
    4 AS csat_score
  UNION ALL
  SELECT
    'T2' AS ticket_id,
    'C2' AS customer_id,
    CAST(NULL AS INT) AS priority,
    CAST(NULL AS INT) AS minutes_to_first_response,
    CAST(NULL AS INT) AS business_minutes_to_response,
    FALSE AS is_first_response_breached,
    FALSE AS is_resolution_breached,
    0 AS comment_count,
    0 AS handoff_count,
    CAST(NULL AS VARCHAR) AS sentiment_label,
    1 AS ticket_number_for_customer,
    FALSE AS is_repeat_contact_7d,
    CAST(NULL AS INT) AS csat_score
  UNION ALL
  SELECT
    'T3' AS ticket_id,
    CAST(NULL AS VARCHAR) AS customer_id,
    CAST(NULL AS INT) AS priority,
    CAST(NULL AS INT) AS minutes_to_first_response,
    CAST(NULL AS INT) AS business_minutes_to_response,
    FALSE AS is_first_response_breached,
    FALSE AS is_resolution_breached,
    0 AS comment_count,
    0 AS handoff_count,
    CAST(NULL AS VARCHAR) AS sentiment_label,
    CAST(NULL AS INT) AS ticket_number_for_customer,
    FALSE AS is_repeat_contact_7d,
    CAST(NULL AS INT) AS csat_score
),

__assert__ticket_id_is_unique_and_present AS (
  SELECT t.ticket_id
  FROM __ref("fct_support_tickets") AS t
  GROUP BY
    t.ticket_id
  HAVING
    COUNT(*) > 1
    OR t.ticket_id IS NULL
)
