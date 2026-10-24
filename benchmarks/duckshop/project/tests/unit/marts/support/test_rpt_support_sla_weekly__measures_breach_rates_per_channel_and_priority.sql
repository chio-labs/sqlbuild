TEST (name "rpt_support_sla_weekly__measures_breach_rates_per_channel_and_priority");

WITH __ref__fct_support_tickets AS (
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
    FALSE,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T3',
    NULL,
    'email',
    1,
    NULL,
    'damaged_item',
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
    NULL,
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
    'email',
    1,
    NULL,
    NULL,
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

__assert__sla_week_key_is_unique_and_present AS (
  SELECT t.sla_week_key
  FROM __ref("rpt_support_sla_weekly") AS t
  GROUP BY
    t.sla_week_key
  HAVING
    COUNT(*) > 1
    OR t.sla_week_key IS NULL
)
