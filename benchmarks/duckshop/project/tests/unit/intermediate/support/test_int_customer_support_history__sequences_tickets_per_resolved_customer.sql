TEST (name "int_customer_support_history__sequences_tickets_per_resolved_customer");

WITH __ref__stg_tickets AS (
  SELECT
    'T1' AS ticket_id,
    'a@example.com' AS customer_email,
    NULL AS channel,
    NULL AS priority,
    NULL AS ticket_status,
    '2026-03-01 10:00:00 +00:00'::TIMESTAMP_LTZ AS created_at,
    NULL AS solved_at,
    NULL AS order_id,
    'delivery' AS contact_reason,
    NULL AS tag_list,
    NULL AS is_vip,
    NULL AS custom_fields,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'T2',
    'a@example.com',
    NULL,
    NULL,
    NULL,
    '2026-03-05 10:00:00 +00:00'::TIMESTAMP_LTZ,
    NULL,
    NULL,
    'delivery',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T3',
    'a@example.com',
    NULL,
    NULL,
    NULL,
    '2026-03-20 10:00:00 +00:00'::TIMESTAMP_LTZ,
    NULL,
    NULL,
    'delivery',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T4',
    'a@example.com',
    NULL,
    NULL,
    NULL,
    '2026-03-21 10:00:00 +00:00'::TIMESTAMP_LTZ,
    NULL,
    NULL,
    'delivery',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T5',
    'unknown@example.com',
    NULL,
    NULL,
    NULL,
    '2026-03-01 12:00:00 +00:00'::TIMESTAMP_LTZ,
    NULL,
    NULL,
    'delivery',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T6',
    'other@example.com',
    NULL,
    NULL,
    NULL,
    '2026-03-02 12:00:00 +00:00'::TIMESTAMP_LTZ,
    NULL,
    NULL,
    'delivery',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__ref__int_customer_identity AS (
  SELECT
    'C2' AS customer_id,
    'a@example.com' AS email_normalised,
    NULL AS email_domain,
    NULL AS email_dedupe_key,
    NULL AS phone_normalised,
    NULL AS full_name,
    NULL AS anonymous_ids,
    NULL AS anonymous_id_count,
    NULL AS newsletter_lists,
    NULL AS ticket_count,
    NULL AS duplicate_candidate_id,
    NULL AS duplicate_name_similarity,
    NULL AS accounts_sharing_email
  UNION ALL
  SELECT
    'C1',
    'a@example.com',
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
  UNION ALL
  SELECT
    'C3',
    'b@example.com',
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

__ref__stg_csat_responses AS (
  SELECT
    'R1' AS response_id,
    'T1' AS ticket_id,
    2 AS score,
    NULL AS is_satisfied,
    NULL AS comment_text,
    '2026-03-02 10:00:00 +00:00'::TIMESTAMP_TZ AS responded_at,
    NULL AS effort_score,
    NULL AS answers,
    NULL AS source_seq,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'R2',
    'T1',
    4,
    NULL,
    NULL,
    '2026-03-03 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'R3',
    'T2',
    5,
    NULL,
    NULL,
    '2026-03-06 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'R4',
    'T4',
    3,
    NULL,
    NULL,
    '2026-03-22 10:00:00 +00:00'::TIMESTAMP_TZ,
    NULL,
    NULL,
    NULL,
    NULL
),

__expected__int_customer_support_history AS (
  SELECT
    'T1' AS ticket_id,
    'C1' AS customer_id,
    1 AS ticket_number_for_customer,
    CAST(NULL AS INT) AS days_since_previous_ticket,
    4 AS csat_score,
    4.0::DECIMAL(6, 3) AS rolling_csat_avg,
    FALSE AS is_repeat_contact_7d
  UNION ALL
  SELECT
    'T2' AS ticket_id,
    'C1' AS customer_id,
    2 AS ticket_number_for_customer,
    4 AS days_since_previous_ticket,
    5 AS csat_score,
    4.5::DECIMAL(6, 3) AS rolling_csat_avg,
    TRUE AS is_repeat_contact_7d
  UNION ALL
  SELECT
    'T3' AS ticket_id,
    'C1' AS customer_id,
    3 AS ticket_number_for_customer,
    15 AS days_since_previous_ticket,
    CAST(NULL AS INT) AS csat_score,
    4.5::DECIMAL(6, 3) AS rolling_csat_avg,
    FALSE AS is_repeat_contact_7d
  UNION ALL
  SELECT
    'T4' AS ticket_id,
    'C1' AS customer_id,
    4 AS ticket_number_for_customer,
    1 AS days_since_previous_ticket,
    3 AS csat_score,
    4.0::DECIMAL(6, 3) AS rolling_csat_avg,
    TRUE AS is_repeat_contact_7d
  UNION ALL
  SELECT
    'T5' AS ticket_id,
    CAST(NULL AS VARCHAR) AS customer_id,
    CAST(NULL AS INT) AS ticket_number_for_customer,
    CAST(NULL AS INT) AS days_since_previous_ticket,
    CAST(NULL AS INT) AS csat_score,
    CAST(NULL AS DECIMAL(6, 3)) AS rolling_csat_avg,
    FALSE AS is_repeat_contact_7d
  UNION ALL
  SELECT
    'T6' AS ticket_id,
    CAST(NULL AS VARCHAR) AS customer_id,
    CAST(NULL AS INT) AS ticket_number_for_customer,
    1 AS days_since_previous_ticket,
    CAST(NULL AS INT) AS csat_score,
    CAST(NULL AS DECIMAL(6, 3)) AS rolling_csat_avg,
    TRUE AS is_repeat_contact_7d
)
