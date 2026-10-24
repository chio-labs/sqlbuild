SCENARIO (
  description """
    Ticket facts feed weekly SLA breach rates and monthly contact-reason volumes with IVR calls
  """,
  tags ["support", "sla"],
);

WITH weekly_ticket_total AS (
  SELECT SUM(s.tickets) AS tickets
  FROM __ref("rpt_support_sla_weekly") AS s
),

monthly_ticket_total AS (
  SELECT SUM(r.tickets) AS tickets
  FROM __ref("rpt_contact_reasons_monthly") AS r
),

__ref__fct_support_tickets AS (
  SELECT
    'T1' AS ticket_id,
    NULL AS customer_id,
    'email' AS channel,
    1 AS priority,
    NULL AS ticket_status,
    'damaged_item' AS contact_reason,
    '2026-03-09 10:00:00'::TIMESTAMPNTZ AS created_at_utc,
    NULL AS solved_at,
    30 AS minutes_to_first_response,
    20 AS business_minutes_to_response,
    TRUE AS is_first_response_breached,
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
    1,
    NULL,
    'damaged_item',
    '2026-03-10 10:00:00'::TIMESTAMPNTZ,
    NULL,
    50,
    40,
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
    1,
    NULL,
    NULL,
    '2026-03-11 10:00:00'::TIMESTAMPNTZ,
    NULL,
    10,
    100,
    FALSE,
    TRUE,
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
    'chat',
    NULL,
    NULL,
    'where_is_my_order',
    '2026-03-12 10:00:00'::TIMESTAMPNTZ,
    NULL,
    5,
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
    'phone',
    1,
    NULL,
    'damaged_item',
    NULL,
    NULL,
    NULL,
    NULL,
    TRUE,
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE,
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

__expected__rpt_support_sla_weekly AS (
  SELECT
    '2026-03-09:email:1' AS sla_week_key,
    3 AS tickets,
    0.3333::DECIMAL(9, 4) AS first_response_breach_rate,
    0.3333::DECIMAL(9, 4) AS resolution_breach_rate,
    30.0::DECIMAL(10, 2) AS p50_minutes_to_first_response,
    88.0::DECIMAL(10, 2) AS p90_business_minutes_to_response
  UNION ALL
  SELECT
    '2026-03-09:chat:?' AS sla_week_key,
    1 AS tickets,
    0.0::DECIMAL(9, 4) AS first_response_breach_rate,
    0.0::DECIMAL(9, 4) AS resolution_breach_rate,
    5.0::DECIMAL(10, 2) AS p50_minutes_to_first_response,
    CAST(NULL AS DECIMAL(10, 2)) AS p90_business_minutes_to_response
),

__expected__rpt_contact_reasons_monthly AS (
  SELECT
    '2026-03:damaged_item' AS reason_month_key,
    2 AS tickets,
    1 AS repeat_contacts,
    0.5::DECIMAL(9, 4) AS repeat_rate,
    2 AS calls,
    1 AS abandoned_in_ivr
  UNION ALL
  SELECT
    '2026-03:unspecified' AS reason_month_key,
    1 AS tickets,
    0 AS repeat_contacts,
    0.0::DECIMAL(9, 4) AS repeat_rate,
    0 AS calls,
    0 AS abandoned_in_ivr
  UNION ALL
  SELECT
    '2026-03:where_is_my_order' AS reason_month_key,
    1 AS tickets,
    0 AS repeat_contacts,
    0.0::DECIMAL(9, 4) AS repeat_rate,
    0 AS calls,
    0 AS abandoned_in_ivr
),

__assert__weekly_and_monthly_ticket_totals_agree AS (
  SELECT w.tickets
  FROM weekly_ticket_total AS w
  CROSS JOIN monthly_ticket_total AS m
  WHERE w.tickets IS DISTINCT FROM m.tickets
)
