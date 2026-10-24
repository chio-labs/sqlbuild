TEST (name "int_ticket_business_hours__counts_support_hours_across_holidays_and_dst");

WITH __ref__int_ticket_first_response AS (
  SELECT
    'T1' AS ticket_id,
    '2026-04-02 17:00:00'::TIMESTAMPNTZ AS created_at_utc,
    '2026-04-07 07:30:00'::TIMESTAMPNTZ AS first_response_at_utc,
    NULL AS first_responder_id,
    NULL AS minutes_to_first_response,
    NULL AS first_customer_reply_at_utc,
    NULL AS agent_responses_before_customer_reply,
    NULL AS has_auto_reply
  UNION ALL
  SELECT
    'T2',
    '2026-04-11 10:00:00'::TIMESTAMPNTZ,
    '2026-04-11 10:05:00'::TIMESTAMPNTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T3',
    '2026-04-08 04:00:00'::TIMESTAMPNTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
  UNION ALL
  SELECT
    'T4',
    '2026-03-27 18:30:00'::TIMESTAMPNTZ,
    '2026-03-30 06:30:00'::TIMESTAMPNTZ,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL
),

__seed__holiday_calendar AS (
  SELECT
    'EU' AS region_code,
    '2026-04-03'::DATE AS holiday_date,
    'Good Friday' AS holiday_name
  UNION ALL
  SELECT
    'EU',
    '2026-04-06'::DATE,
    'Easter Monday'
  UNION ALL
  SELECT
    'US',
    '2026-04-07'::DATE,
    'Synthetic holiday'
),

__expected__int_ticket_business_hours AS (
  SELECT
    'T1' AS ticket_id,
    '2026-04-02 19:00:00'::TIMESTAMPNTZ AS created_at_support_local,
    '2026-04-07 09:30:00'::TIMESTAMPNTZ AS first_response_at_support_local,
    6630 AS calendar_minutes_to_response,
    150 AS business_minutes_to_response,
    FALSE AS created_outside_hours
  UNION ALL
  SELECT
    'T2' AS ticket_id,
    '2026-04-11 12:00:00'::TIMESTAMPNTZ AS created_at_support_local,
    '2026-04-11 12:05:00'::TIMESTAMPNTZ AS first_response_at_support_local,
    5 AS calendar_minutes_to_response,
    0 AS business_minutes_to_response,
    TRUE AS created_outside_hours
  UNION ALL
  SELECT
    'T3' AS ticket_id,
    '2026-04-08 06:00:00'::TIMESTAMPNTZ AS created_at_support_local,
    CAST(NULL AS TIMESTAMPNTZ) AS first_response_at_support_local,
    CAST(NULL AS INT) AS calendar_minutes_to_response,
    0 AS business_minutes_to_response,
    TRUE AS created_outside_hours
  UNION ALL
  SELECT
    'T4' AS ticket_id,
    '2026-03-27 19:30:00'::TIMESTAMPNTZ AS created_at_support_local,
    '2026-03-30 08:30:00'::TIMESTAMPNTZ AS first_response_at_support_local,
    3660 AS calendar_minutes_to_response,
    60 AS business_minutes_to_response,
    FALSE AS created_outside_hours
)
