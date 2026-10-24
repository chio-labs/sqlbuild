TEST (name "int_ticket_sla_breaches__uses_business_minutes_only_when_policy_requires");

WITH __ref__stg_tickets AS (
  SELECT
    'T1' AS ticket_id,
    NULL AS customer_email,
    'email' AS channel,
    1 AS priority,
    NULL AS ticket_status,
    NULL AS created_at,
    '2026-03-02 10:00:00 +00:00'::TIMESTAMP_TZ AS solved_at,
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
    'chat',
    2,
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
  UNION ALL
  SELECT
    'T3',
    NULL,
    'phone',
    3,
    NULL,
    NULL,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T4',
    NULL,
    'email',
    1,
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

__ref__stg_sla_policies AS (
  SELECT
    'P1' AS policy_id,
    1 AS priority,
    'email' AS channel,
    60 AS first_response_minutes,
    1440 AS resolution_minutes,
    TRUE AS business_hours_only,
    NULL AS calendar_region_code,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'P2',
    2,
    'chat',
    10,
    600,
    FALSE,
    NULL,
    NULL,
    NULL
),

__ref__int_ticket_first_response AS (
  SELECT
    'T1' AS ticket_id,
    '2026-03-01 09:00:00'::TIMESTAMPNTZ AS created_at_utc,
    NULL AS first_response_at_utc,
    NULL AS first_responder_id,
    300 AS minutes_to_first_response,
    NULL AS first_customer_reply_at_utc,
    NULL AS agent_responses_before_customer_reply,
    NULL AS has_auto_reply
  UNION ALL
  SELECT
    'T2',
    '2026-03-01 09:00:00'::TIMESTAMPNTZ,
    NULL,
    NULL,
    15,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T3',
    '2026-03-01 09:00:00'::TIMESTAMPNTZ,
    NULL,
    NULL,
    5,
    NULL,
    NULL,
    NULL
),

__ref__int_ticket_business_hours AS (
  SELECT
    'T1' AS ticket_id,
    NULL AS created_at_support_local,
    NULL AS first_response_at_support_local,
    NULL AS calendar_minutes_to_response,
    45 AS business_minutes_to_response,
    NULL AS created_outside_hours
  UNION ALL
  SELECT
    'T2',
    NULL,
    NULL,
    NULL,
    5,
    NULL
),

__expected__int_ticket_sla_breaches AS (
  SELECT
    'T1' AS ticket_id,
    'P1' AS policy_id,
    60 AS first_response_target_minutes,
    45 AS first_response_minutes_used,
    FALSE AS is_first_response_breached,
    1440 AS resolution_target_minutes,
    1500 AS resolution_minutes_used,
    TRUE AS is_resolution_breached,
    1 AS breach_count
  UNION ALL
  SELECT
    'T2' AS ticket_id,
    'P2' AS policy_id,
    10 AS first_response_target_minutes,
    15 AS first_response_minutes_used,
    TRUE AS is_first_response_breached,
    600 AS resolution_target_minutes,
    CAST(NULL AS INT) AS resolution_minutes_used,
    FALSE AS is_resolution_breached,
    1 AS breach_count
  UNION ALL
  SELECT
    'T3' AS ticket_id,
    CAST(NULL AS VARCHAR) AS policy_id,
    CAST(NULL AS INT) AS first_response_target_minutes,
    5 AS first_response_minutes_used,
    FALSE AS is_first_response_breached,
    CAST(NULL AS INT) AS resolution_target_minutes,
    60 AS resolution_minutes_used,
    FALSE AS is_resolution_breached,
    0 AS breach_count
),

__assert__only_open_tickets_have_an_age AS (
  SELECT b.ticket_id
  FROM __ref("int_ticket_sla_breaches") AS b
  WHERE
    (
      b.ticket_id = 'T2'
    ) <> COALESCE(b.open_minutes_now > 0, FALSE)
)
