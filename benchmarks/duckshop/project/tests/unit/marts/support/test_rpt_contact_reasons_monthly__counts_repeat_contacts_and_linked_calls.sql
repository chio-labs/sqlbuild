TEST (name "rpt_contact_reasons_monthly__counts_repeat_contacts_and_linked_calls");

WITH __ref__fct_support_tickets AS (
  SELECT
    'T1' AS ticket_id,
    NULL AS customer_id,
    'email' AS channel,
    NULL AS priority,
    NULL AS ticket_status,
    'damaged_item' AS contact_reason,
    '2026-02-10 10:00:00'::TIMESTAMPNTZ AS created_at_utc,
    NULL AS solved_at,
    NULL AS minutes_to_first_response,
    NULL AS business_minutes_to_response,
    FALSE AS is_first_response_breached,
    FALSE AS is_resolution_breached,
    NULL AS comment_count,
    NULL AS handoff_count,
    NULL AS sentiment_label,
    NULL AS ticket_number_for_customer,
    FALSE AS is_repeat_contact_7d,
    NULL AS csat_score,
    NULL AS source_loaded_at
  UNION ALL
  SELECT
    'T2',
    NULL,
    'email',
    NULL,
    NULL,
    'damaged_item',
    '2026-03-05 10:00:00'::TIMESTAMPNTZ,
    NULL,
    NULL,
    NULL,
    FALSE,
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T3',
    NULL,
    'email',
    NULL,
    NULL,
    'damaged_item',
    '2026-03-06 10:00:00'::TIMESTAMPNTZ,
    NULL,
    NULL,
    NULL,
    FALSE,
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T4',
    NULL,
    'email',
    NULL,
    NULL,
    NULL,
    '2026-03-07 10:00:00'::TIMESTAMPNTZ,
    NULL,
    NULL,
    NULL,
    FALSE,
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T5',
    NULL,
    'email',
    NULL,
    NULL,
    'damaged_item',
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL
),

__ref__int_call_ivr_paths AS (
  SELECT
    'CL1' AS call_id,
    'T2' AS ticket_id,
    NULL AS agent_id,
    NULL AS first_menu_choice,
    NULL AS final_menu_node,
    NULL AS menu_steps,
    NULL AS repeated_menu_visits,
    FALSE AS abandoned_in_ivr,
    NULL AS caller_region,
    NULL AS duration_bucket
  UNION ALL
  SELECT
    'CL2',
    'T2',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'CL3',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
    NULL,
    NULL
),

__expected__rpt_contact_reasons_monthly AS (
  SELECT
    '2026-02:damaged_item' AS reason_month_key,
    1 AS tickets,
    0 AS repeat_contacts,
    0.0::DECIMAL(9, 4) AS repeat_rate,
    0 AS calls,
    0 AS abandoned_in_ivr,
    CAST(NULL AS INT) AS month_over_month_change
  UNION ALL
  SELECT
    '2026-03:damaged_item' AS reason_month_key,
    2 AS tickets,
    1 AS repeat_contacts,
    0.5::DECIMAL(9, 4) AS repeat_rate,
    2 AS calls,
    1 AS abandoned_in_ivr,
    1 AS month_over_month_change
  UNION ALL
  SELECT
    '2026-03:unspecified' AS reason_month_key,
    1 AS tickets,
    0 AS repeat_contacts,
    0.0::DECIMAL(9, 4) AS repeat_rate,
    0 AS calls,
    0 AS abandoned_in_ivr,
    CAST(NULL AS INT) AS month_over_month_change
),

__assert__reason_month_key_is_unique_and_present AS (
  SELECT t.reason_month_key
  FROM __ref("rpt_contact_reasons_monthly") AS t
  GROUP BY
    t.reason_month_key
  HAVING
    COUNT(*) > 1
    OR t.reason_month_key IS NULL
)
